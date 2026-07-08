"""실 Claude(Anthropic) completion provider (벤더 어댑터).

SDK 없이 오프라인 실행되도록 client·errors를 주입해 매핑·비용·예외변환·거부처리를 검증한다.
실 벤더 호출은 없다.
"""
import types

import pytest

from app.llm.anthropic_provider import (
    DEFAULT_MODEL,
    AnthropicProvider,
    compute_cost_usd,
)
from app.llm.base import (
    CompletionRequest,
    EmbeddingRequest,
    LLMPermanentError,
    LLMTimeoutError,
    LLMTransientError,
)
from app.llm.client import build_provider

# --- SDK 응답/클라이언트/예외 페이크 ---


class _Block:
    def __init__(self, type_: str, text: str = "") -> None:
        self.type = type_
        self.text = text


class _Usage:
    def __init__(self, i: int, o: int) -> None:
        self.input_tokens = i
        self.output_tokens = o


class _Resp:
    def __init__(self, content, model="claude-opus-4-8", usage=(3, 5),
                 stop_reason="end_turn", stop_details=None) -> None:
        self.content = content
        self.model = model
        self.usage = _Usage(*usage)
        self.stop_reason = stop_reason
        self.stop_details = stop_details


class _Messages:
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
        self.messages = _Messages(**kw)


# SDK 예외 계층을 모사 (APITimeoutError ⊂ APIConnectionError, RateLimitError ⊂ APIStatusError)
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
    return AnthropicProvider(
        client=_Client(resp=resp, raise_exc=raise_exc, record=record),
        errors=FAKE_ERRORS, **kw,
    )


# --- 요청/응답 매핑 ---


def test_complete_maps_response() -> None:
    resp = _Resp([_Block("text", "안녕"), _Block("text", " 반가워")], usage=(7, 11))
    p = _provider(resp=resp, model="claude-opus-4-8")
    out = p.complete(CompletionRequest(prompt="발화 생성", model="batch"))
    assert out.text == "안녕 반가워"
    assert out.provider == "anthropic"
    assert out.model == "claude-opus-4-8"
    assert out.usage.prompt_tokens == 7 and out.usage.completion_tokens == 11


def test_request_uses_configured_model_and_max_tokens() -> None:
    rec: dict = {}
    p = _provider(resp=_Resp([_Block("text", "x")]), record=rec,
                  model="claude-haiku-4-5", max_tokens=222)
    p.complete(CompletionRequest(prompt="p", model="internal-label"))
    assert rec["model"] == "claude-haiku-4-5"   # 내부 라벨이 아니라 실제 모델
    assert rec["max_tokens"] == 222
    assert rec["messages"] == [{"role": "user", "content": "p"}]


def test_model_and_max_tokens_from_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_MODEL", "claude-sonnet-5")
    monkeypatch.setenv("LLM_MAX_TOKENS", "1234")
    rec: dict = {}
    p = _provider(resp=_Resp([_Block("text", "x")], model="claude-sonnet-5"), record=rec)
    p.complete(CompletionRequest(prompt="p", model="lbl"))
    assert rec["model"] == "claude-sonnet-5"
    assert rec["max_tokens"] == 1234


def test_default_model_when_env_unset(monkeypatch) -> None:
    monkeypatch.delenv("LLM_MODEL", raising=False)
    p = _provider(resp=_Resp([_Block("text", "x")]))
    assert p._model == DEFAULT_MODEL  # noqa: SLF001


def test_system_prompt_forwarded_only_when_present() -> None:
    rec: dict = {}
    p = _provider(resp=_Resp([_Block("text", "x")]), record=rec)
    p.complete(CompletionRequest(prompt="p", model="m", system="너는 조력자다"))
    assert rec["system"] == "너는 조력자다"
    p.complete(CompletionRequest(prompt="p", model="m"))
    assert "system" not in rec


def test_sampling_params_not_forwarded() -> None:
    """adaptive-thinking 모델은 temperature/top_p를 거부(400) — 전달하지 않는다."""
    rec: dict = {}
    p = _provider(resp=_Resp([_Block("text", "x")]), record=rec)
    p.complete(CompletionRequest(prompt="p", model="m", temperature=0.7))
    assert "temperature" not in rec and "top_p" not in rec


def test_non_text_blocks_ignored() -> None:
    resp = _Resp([_Block("thinking", "속엣말"), _Block("text", "답")])
    p = _provider(resp=resp)
    assert p.complete(CompletionRequest(prompt="p", model="m")).text == "답"


# --- 비용 ---


def test_compute_cost_from_pricing() -> None:
    # opus-4-8: $5 in / $25 out per 1M
    assert compute_cost_usd("claude-opus-4-8", 1_000_000, 1_000_000) == pytest.approx(30.0)
    assert compute_cost_usd("claude-opus-4-8", 1000, 0) == pytest.approx(0.005)


def test_unknown_model_cost_zero() -> None:
    assert compute_cost_usd("mystery-model", 1000, 1000) == 0.0


def test_cost_flows_through_complete() -> None:
    resp = _Resp([_Block("text", "x")], model="claude-opus-4-8", usage=(1_000_000, 1_000_000))
    out = _provider(resp=resp).complete(CompletionRequest(prompt="p", model="m"))
    assert out.cost_usd == pytest.approx(30.0)


# --- 거부(refusal) ---


def test_refusal_raises_permanent() -> None:
    resp = _Resp([], stop_reason="refusal", stop_details={"category": "cyber"})
    with pytest.raises(LLMPermanentError, match="refusal"):
        _provider(resp=resp).complete(CompletionRequest(prompt="p", model="m"))


# --- 예외 변환 (LLMClient 재시도 정책이 이 계층을 본다) ---


@pytest.mark.parametrize(
    "exc, expected",
    [
        (_APITimeoutError("t"), LLMTimeoutError),
        (_APIConnectionError("c"), LLMTransientError),
        (_RateLimitError("r"), LLMTransientError),
        (_APIStatusError("s5", status_code=503), LLMTransientError),
        (_APIStatusError("s4", status_code=400), LLMPermanentError),
    ],
)
def test_exception_translation(exc, expected) -> None:
    p = _provider(raise_exc=exc)
    with pytest.raises(expected):
        p.complete(CompletionRequest(prompt="p", model="m"))


# --- 임베딩 미지원 ---


def test_embed_raises_not_implemented() -> None:
    with pytest.raises(NotImplementedError, match="임베딩"):
        _provider().embed(EmbeddingRequest(inputs=["a"], model="e"))


# --- 등록 (env 주입 seam) ---


def test_anthropic_registered(monkeypatch) -> None:
    """LLM_PROVIDER=anthropic로 build 가능(등록됨). SDK/키 부재로만 실패해야 하고,
    '알 수 없는 provider'로 실패하면 안 된다."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(Exception) as ei:  # noqa: PT011 - ImportError 또는 ValueError 둘 다 허용
        build_provider("anthropic")
    assert "알 수 없는" not in str(ei.value)
