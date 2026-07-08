"""실 OpenAI 임베딩 provider (벤더 어댑터, 임베딩 전용).

SDK 없이 오프라인 실행되도록 client·errors를 주입해 매핑·차원·비용·예외변환을 검증한다.
실 벤더 호출은 없다.
"""
import types

import pytest

from app.llm.base import (
    CompletionRequest,
    EmbeddingRequest,
    LLMPermanentError,
    LLMTimeoutError,
    LLMTransientError,
)
from app.llm.client import build_provider
from app.llm.openai_embedding_provider import (
    DEFAULT_DIM,
    OpenAIEmbeddingProvider,
    compute_cost_usd,
)


class _Datum:
    def __init__(self, emb) -> None:
        self.embedding = emb


class _EmbUsage:
    def __init__(self, prompt_tokens) -> None:
        self.prompt_tokens = prompt_tokens
        self.total_tokens = prompt_tokens


class _EmbResp:
    def __init__(self, data, model="text-embedding-3-small", prompt_tokens=9) -> None:
        self.data = data
        self.model = model
        self.usage = _EmbUsage(prompt_tokens)


class _Embeddings:
    def __init__(self, resp=None, raise_exc=None, record=None) -> None:
        self._resp = resp
        self._raise = raise_exc
        self._record = record

    def create(self, **kwargs):
        if self._record is not None:
            self._record.clear()
            self._record.update(kwargs)
        if self._raise is not None:
            raise self._raise
        return self._resp


class _Client:
    def __init__(self, **kw) -> None:
        self.embeddings = _Embeddings(**kw)


class _APIStatusError(Exception):
    def __init__(self, msg="", status_code=400) -> None:
        super().__init__(msg)
        self.status_code = status_code


class _APIConnectionError(Exception):
    pass


class _APITimeoutError(_APIConnectionError):
    pass


class _RateLimitError(_APIStatusError):
    def __init__(self, msg="") -> None:
        super().__init__(msg, status_code=429)


FAKE_ERRORS = types.SimpleNamespace(
    APITimeoutError=_APITimeoutError,
    APIConnectionError=_APIConnectionError,
    RateLimitError=_RateLimitError,
    APIStatusError=_APIStatusError,
)


def _provider(resp=None, raise_exc=None, record=None, **kw):
    return OpenAIEmbeddingProvider(
        client=_Client(resp=resp, raise_exc=raise_exc, record=record),
        errors=FAKE_ERRORS, **kw,
    )


# --- 매핑·차원 ---


def test_embed_maps_vectors_and_usage() -> None:
    resp = _EmbResp([_Datum([0.1, 0.2, 0.3]), _Datum([0.4, 0.5, 0.6])], prompt_tokens=12)
    out = _provider(resp=resp).embed(EmbeddingRequest(inputs=["a", "b"], model="e"))
    assert out.provider == "openai"
    assert out.vectors == [[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]]
    assert out.usage.prompt_tokens == 12 and out.usage.completion_tokens == 0


def test_dimensions_forced_to_db_vector() -> None:
    """DB vector(1536)에 맞춰 create에 dimensions를 강제한다."""
    rec: dict = {}
    p = _provider(resp=_EmbResp([_Datum([0.0])]), record=rec)
    p.embed(EmbeddingRequest(inputs=["x"], model="e"))
    assert rec["dimensions"] == DEFAULT_DIM == 1536
    assert rec["model"] == "text-embedding-3-small"
    assert rec["input"] == ["x"]


def test_dim_and_model_from_env(monkeypatch) -> None:
    monkeypatch.setenv("EMBEDDING_MODEL", "text-embedding-3-large")
    monkeypatch.setenv("EMBEDDING_DIM", "1536")
    rec: dict = {}
    p = _provider(resp=_EmbResp([_Datum([0.0])], model="text-embedding-3-large"), record=rec)
    p.embed(EmbeddingRequest(inputs=["x"], model="e"))
    assert rec["model"] == "text-embedding-3-large"
    assert rec["dimensions"] == 1536  # 3-large도 1536으로 축소해 DB와 맞춤


# --- 비용 ---


def test_cost_from_pricing() -> None:
    assert compute_cost_usd("text-embedding-3-small", 1_000_000) == pytest.approx(0.02)
    assert compute_cost_usd("unknown", 1_000_000) == 0.0


def test_cost_flows_through_embed() -> None:
    resp = _EmbResp([_Datum([0.0])], model="text-embedding-3-small", prompt_tokens=1_000_000)
    out = _provider(resp=resp).embed(EmbeddingRequest(inputs=["x"], model="e"))
    assert out.cost_usd == pytest.approx(0.02)


# --- 예외 변환 ---


@pytest.mark.parametrize(
    "exc, expected",
    [
        (_APITimeoutError("t"), LLMTimeoutError),
        (_APIConnectionError("c"), LLMTransientError),
        (_RateLimitError("r"), LLMTransientError),
        (_APIStatusError("s5", status_code=503), LLMTransientError),
        (_APIStatusError("s4", status_code=401), LLMPermanentError),
    ],
)
def test_exception_translation(exc, expected) -> None:
    with pytest.raises(expected):
        _provider(raise_exc=exc).embed(EmbeddingRequest(inputs=["x"], model="e"))


# --- completion 미지원 ---


def test_complete_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="completion"):
        _provider().complete(CompletionRequest(prompt="p", model="m"))


# --- 등록 (EMBEDDING_PROVIDER 주입 seam) ---


def test_openai_registered(monkeypatch) -> None:
    monkeypatch.delenv("EMBEDDING_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(Exception) as ei:  # noqa: PT011 - ImportError/ValueError 둘 다 허용
        build_provider("openai")
    assert "알 수 없는" not in str(ei.value)
