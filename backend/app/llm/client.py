"""LLM 재시도·타임아웃·비용 로깅 래퍼 + provider 주입 (CLAUDE.md 기술 스택).

원칙:
- provider는 env(LLM_PROVIDER / EMBEDDING_PROVIDER)로 주입한다. 특정 벤더 하드코딩 금지.
- 모든 호출은 토큰·비용을 로깅한다 (성공·실패 모두).
- 숫자 임계값(재시도·타임아웃·백오프)은 config.llm에만 존재한다 (절대 규칙 1).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from collections.abc import Callable

from app.core.config import LLMConfig, get_config
from app.llm.base import (
    CompletionRequest,
    CompletionResult,
    EmbeddingRequest,
    EmbeddingResult,
    LLMCallRecord,
    LLMError,
    LLMPermanentError,
    LLMProvider,
    LLMTimeoutError,
    LLMTransientError,
    Usage,
)

logger = logging.getLogger("app.llm")

_RETRYABLE = (LLMTransientError, LLMTimeoutError)

Recorder = Callable[[LLMCallRecord], None]


def _default_recorder(record: LLMCallRecord) -> None:
    logger.info(
        "llm_call provider=%s model=%s op=%s tokens=%d cost_usd=%.6f "
        "latency_ms=%d attempts=%d ok=%s%s",
        record.provider, record.model, record.operation, record.total_tokens,
        record.cost_usd, record.latency_ms, record.attempts, record.ok,
        f" error={record.error}" if record.error else "",
    )


class LLMClient:
    """provider를 감싸 재시도·타임아웃·비용 로깅을 제공하는 공개 인터페이스."""

    def __init__(
        self,
        provider: LLMProvider,
        config: LLMConfig,
        recorder: Recorder | None = None,
    ) -> None:
        self._provider = provider
        self._config = config
        self._recorder = recorder or _default_recorder

    @property
    def provider_name(self) -> str:
        return self._provider.name

    def complete(self, request: CompletionRequest) -> CompletionResult:
        return self._call("complete", request.model, lambda: self._provider.complete(request))

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        return self._call("embed", request.model, lambda: self._provider.embed(request))

    def _call(self, operation: str, model: str, fn: Callable[[], object]) -> object:
        start = time.monotonic()
        attempts = 0
        last_exc: Exception | None = None

        for attempt in range(1, self._config.max_retries + 2):
            attempts = attempt
            try:
                result = self._run_with_timeout(fn)
            except Exception as exc:  # noqa: BLE001 — 기록 후 재던짐
                last_exc = exc
                retryable = isinstance(exc, _RETRYABLE) and attempt <= self._config.max_retries
                if retryable:
                    if self._config.retry_backoff_s:
                        time.sleep(self._config.retry_backoff_s * attempt)
                    continue
                self._emit(operation, model, None, start, attempts, ok=False, error=repr(exc))
                raise
            else:
                self._emit(operation, model, result, start, attempts, ok=True)
                return result

        assert last_exc is not None  # 루프는 반환 또는 raise로만 빠져나온다
        raise last_exc

    def _run_with_timeout(self, fn: Callable[[], object]) -> object:
        timeout_s = self._config.timeout_s
        if not timeout_s or timeout_s <= 0:
            return fn()
        box: dict[str, object] = {}

        def runner() -> None:
            try:
                box["result"] = fn()
            except Exception as exc:  # noqa: BLE001 — 호출 스레드에서 재던짐
                box["error"] = exc

        # daemon 스레드: 타임아웃으로 버려진 호출이 인터프리터 종료를 막지 않는다
        thread = threading.Thread(target=runner, name="llm-call", daemon=True)
        thread.start()
        thread.join(timeout_s)
        if thread.is_alive():
            raise LLMTimeoutError(f"호출이 {timeout_s}s를 초과")
        error = box.get("error")
        if error is not None:
            raise error  # type: ignore[misc]
        return box.get("result")

    def _emit(
        self,
        operation: str,
        model: str,
        result: object | None,
        start: float,
        attempts: int,
        *,
        ok: bool,
        error: str | None = None,
    ) -> None:
        latency_ms = int((time.monotonic() - start) * 1000)
        usage: Usage | None = getattr(result, "usage", None)
        cost = float(getattr(result, "cost_usd", 0.0) or 0.0)
        self._recorder(
            LLMCallRecord(
                provider=self._provider.name,
                model=model,
                operation=operation,
                prompt_tokens=usage.prompt_tokens if usage else 0,
                completion_tokens=usage.completion_tokens if usage else 0,
                total_tokens=usage.total_tokens if usage else 0,
                cost_usd=cost,
                latency_ms=latency_ms,
                attempts=attempts,
                ok=ok,
                error=error,
            )
        )


# --- provider 레지스트리 + env 주입 ---

_PROVIDERS: dict[str, Callable[[], LLMProvider]] = {}


def register_provider(name: str, factory: Callable[[], LLMProvider]) -> None:
    _PROVIDERS[name] = factory


def build_provider(name: str) -> LLMProvider:
    factory = _PROVIDERS.get(name)
    if factory is None:
        raise ValueError(f"알 수 없는 LLM provider: {name!r} (등록: {sorted(_PROVIDERS)})")
    return factory()


def _provider_from_env(env_var: str, default: str = "mock") -> LLMProvider:
    return build_provider(os.environ.get(env_var) or default)


def get_llm_client(recorder: Recorder | None = None) -> LLMClient:
    """LLM_PROVIDER env로 주입된 completion provider 클라이언트."""
    return LLMClient(_provider_from_env("LLM_PROVIDER"), get_config().llm, recorder)


def get_embedding_client(recorder: Recorder | None = None) -> LLMClient:
    """EMBEDDING_PROVIDER env로 주입된 embedding provider 클라이언트."""
    return LLMClient(_provider_from_env("EMBEDDING_PROVIDER"), get_config().llm, recorder)


def embed_fn_from_env(mock_dim: int = 1536):
    """env 기반 임베딩 함수 — run_backfill·검수 후 자동 backfill이 공유하는 단일 조립점.

    mock이면 DB vector(1536)와 차원을 맞춘 MockProvider(오프라인). 실 provider면
    EMBEDDING_MODEL(기본 text-embedding-3-small 계열)을 쓴다. 반환: texts → vectors.
    """
    provider = (os.environ.get("EMBEDDING_PROVIDER") or "mock").lower()
    if provider in ("", "mock"):
        from app.llm.mock import MockProvider

        p = MockProvider(embed_dim=mock_dim)
        return lambda texts: p.embed(EmbeddingRequest(inputs=texts, model="embed")).vectors
    client = get_embedding_client()
    model = os.environ.get("EMBEDDING_MODEL", "embed")
    return lambda texts: client.embed(EmbeddingRequest(inputs=texts, model=model)).vectors


# mock provider 등록 (import 시점). 실제 provider는 각 모듈이 register_provider로 등록.
from app.llm.mock import MockProvider  # noqa: E402

register_provider("mock", MockProvider)

__all__ = [
    "CompletionRequest",
    "CompletionResult",
    "EmbeddingRequest",
    "EmbeddingResult",
    "LLMCallRecord",
    "LLMClient",
    "LLMConfig",
    "LLMError",
    "LLMPermanentError",
    "LLMProvider",
    "LLMTimeoutError",
    "LLMTransientError",
    "Usage",
    "build_provider",
    "embed_fn_from_env",
    "get_embedding_client",
    "get_llm_client",
    "register_provider",
]
