"""T1.6 AC: LLM 클라이언트 추상화.

- mock provider로 전체 테스트가 오프라인 실행 가능
- 호출별 토큰·비용 로깅
- 재시도·타임아웃 동작
- provider는 env(LLM_PROVIDER)로 주입 — 벤더 하드코딩 금지 (CLAUDE.md 기술 스택)
"""
import time

import pytest

from app.llm.client import (
    CompletionRequest,
    EmbeddingRequest,
    LLMClient,
    LLMConfig,
    LLMPermanentError,
    LLMProvider,
    LLMTimeoutError,
    LLMTransientError,
    build_provider,
    get_llm_client,
    register_provider,
)
from app.llm.mock import MockProvider

FAST = LLMConfig(max_retries=3, timeout_s=1.0, retry_backoff_s=0.0)


# --- 오프라인 mock 동작 ---


def test_mock_complete_offline() -> None:
    client = LLMClient(MockProvider(), FAST)
    result = client.complete(CompletionRequest(prompt="다음엔 뭘 해줄까?", model="mock-1"))
    assert isinstance(result.text, str) and result.text
    assert result.provider == "mock"
    assert result.usage.total_tokens > 0


def test_mock_complete_is_deterministic() -> None:
    client = LLMClient(MockProvider(), FAST)
    req = CompletionRequest(prompt="같은 입력", model="mock-1")
    assert client.complete(req).text == client.complete(req).text


def test_mock_embed_dimension_matches_db_vector() -> None:
    client = LLMClient(MockProvider(embed_dim=1536), FAST)
    result = client.embed(EmbeddingRequest(inputs=["a", "b"], model="embed-1"))
    assert len(result.vectors) == 2
    assert all(len(v) == 1536 for v in result.vectors)


def test_mock_embed_is_deterministic() -> None:
    client = LLMClient(MockProvider(), FAST)
    req = EmbeddingRequest(inputs=["나뭇잎 분류"], model="embed-1")
    assert client.embed(req).vectors == client.embed(req).vectors


# --- 토큰·비용 로깅 ---


def test_every_call_is_logged() -> None:
    records = []
    client = LLMClient(MockProvider(), FAST, recorder=records.append)
    client.complete(CompletionRequest(prompt="안녕", model="mock-1"))
    client.embed(EmbeddingRequest(inputs=["안녕"], model="embed-1"))
    assert [r.operation for r in records] == ["complete", "embed"]
    assert all(r.ok and r.total_tokens > 0 for r in records)


def test_cost_is_logged_from_provider_pricing() -> None:
    records = []
    client = LLMClient(MockProvider(cost_per_1k_tokens=2.0), FAST, recorder=records.append)
    client.complete(CompletionRequest(prompt="비용 계산 대상 발화", model="mock-1"))
    rec = records[0]
    assert rec.cost_usd == pytest.approx(rec.total_tokens / 1000 * 2.0)
    assert rec.cost_usd > 0


def test_failure_is_logged_with_ok_false() -> None:
    records = []
    provider = _ScriptedProvider(fail_times=99, error=LLMTransientError)
    client = LLMClient(provider, LLMConfig(max_retries=1, timeout_s=1.0, retry_backoff_s=0.0),
                       recorder=records.append)
    with pytest.raises(LLMTransientError):
        client.complete(CompletionRequest(prompt="x", model="m"))
    assert records[-1].ok is False
    assert records[-1].attempts == 2  # 최초 1 + 재시도 1


# --- 재시도 ---


def test_retry_then_succeed() -> None:
    records = []
    provider = _ScriptedProvider(fail_times=2, error=LLMTransientError)
    client = LLMClient(provider, FAST, recorder=records.append)
    result = client.complete(CompletionRequest(prompt="x", model="m"))
    assert result.text
    assert records[-1].ok and records[-1].attempts == 3


def test_retry_exhausted_raises() -> None:
    provider = _ScriptedProvider(fail_times=99, error=LLMTransientError)
    client = LLMClient(provider, LLMConfig(max_retries=2, timeout_s=1.0, retry_backoff_s=0.0))
    with pytest.raises(LLMTransientError):
        client.complete(CompletionRequest(prompt="x", model="m"))
    assert provider.calls == 3  # 1 + 2 재시도


def test_permanent_error_not_retried() -> None:
    provider = _ScriptedProvider(fail_times=99, error=LLMPermanentError)
    client = LLMClient(provider, FAST)
    with pytest.raises(LLMPermanentError):
        client.complete(CompletionRequest(prompt="x", model="m"))
    assert provider.calls == 1  # 재시도 없음


# --- 타임아웃 ---


def test_timeout_raises() -> None:
    provider = _ScriptedProvider(delay_s=0.5)
    client = LLMClient(provider, LLMConfig(max_retries=0, timeout_s=0.05, retry_backoff_s=0.0))
    with pytest.raises(LLMTimeoutError):
        client.complete(CompletionRequest(prompt="x", model="m"))


def test_timeout_is_retried() -> None:
    # 첫 호출은 느려서 타임아웃, 재시도는 빠르게 성공
    provider = _ScriptedProvider(slow_first=True, delay_s=0.3)
    client = LLMClient(provider, LLMConfig(max_retries=2, timeout_s=0.1, retry_backoff_s=0.0))
    result = client.complete(CompletionRequest(prompt="x", model="m"))
    assert result.text


def test_negative_retry_config_rejected() -> None:
    """음수 재시도/타임아웃/백오프는 구성 시점에 거부 (AssertionError 마스킹 방지)."""
    from pydantic import ValidationError

    for kwargs in (
        {"max_retries": -1, "timeout_s": 1.0, "retry_backoff_s": 0.0},
        {"max_retries": 1, "timeout_s": -1.0, "retry_backoff_s": 0.0},
        {"max_retries": 1, "timeout_s": 1.0, "retry_backoff_s": -0.5},
    ):
        with pytest.raises(ValidationError):
            LLMConfig(**kwargs)


# --- provider 주입 (env) ---


def test_get_llm_client_defaults_to_mock(monkeypatch) -> None:
    monkeypatch.delenv("LLM_PROVIDER", raising=False)
    client = get_llm_client()
    assert client.provider_name == "mock"
    # 오프라인 실행 가능
    assert client.complete(CompletionRequest(prompt="x", model="mock-1")).text


def test_provider_injected_by_env(monkeypatch) -> None:
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    assert build_provider("mock").name == "mock"


def test_unknown_provider_raises() -> None:
    with pytest.raises(ValueError, match="알 수 없는"):
        build_provider("definitely-not-registered")


def test_register_custom_provider() -> None:
    register_provider("scripted-test", lambda: _ScriptedProvider())
    assert build_provider("scripted-test").name == "scripted"


# --- 테스트용 스크립트 provider (재시도·타임아웃 유발) ---


class _ScriptedProvider(LLMProvider):
    name = "scripted"

    def __init__(self, *, fail_times: int = 0, error=LLMTransientError,
                 delay_s: float = 0.0, slow_first: bool = False) -> None:
        self._fail_times = fail_times
        self._error = error
        self._delay_s = delay_s
        self._slow_first = slow_first
        self.calls = 0

    def _maybe_fail(self) -> None:
        self.calls += 1
        if self._slow_first and self.calls == 1:
            time.sleep(self._delay_s)
        elif self._delay_s and not self._slow_first:
            time.sleep(self._delay_s)
        if self.calls <= self._fail_times:
            raise self._error("scripted failure")

    def complete(self, request: CompletionRequest):
        self._maybe_fail()
        return MockProvider().complete(request)

    def embed(self, request: EmbeddingRequest):
        self._maybe_fail()
        return MockProvider().embed(request)
