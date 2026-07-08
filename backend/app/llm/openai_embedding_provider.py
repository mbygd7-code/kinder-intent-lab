"""실 OpenAI 임베딩 provider — 벤더 어댑터 (EMBEDDING_PROVIDER=openai).

DB는 vector(1536)이므로 `dimensions`를 EMBEDDING_DIM(기본 1536)으로 고정해 차원을 맞춘다
(text-embedding-3-* 는 dimensions 파라미터로 축소 가능 — 3-small 기본이 1536).

completion은 담당하지 않는다(임베딩 전용). completion은 LLM_PROVIDER(anthropic 등).
재시도·타임아웃·토큰/비용 로깅은 LLMClient가 담당 — 여기선 벤더 원시 호출 + 예외 변환만.
SDK import는 지연(생성 시점) — mock 전용 오프라인 환경은 openai 패키지가 없어도 된다.
"""
from __future__ import annotations

import os
from dataclasses import dataclass

from app.llm.base import (
    CompletionRequest,
    CompletionResult,
    EmbeddingRequest,
    EmbeddingResult,
    LLMPermanentError,
    LLMProvider,
    LLMTimeoutError,
    LLMTransientError,
    Usage,
)

DEFAULT_MODEL = "text-embedding-3-small"  # 1536차원 — DB vector(1536)와 일치
DEFAULT_DIM = 1536


@dataclass(frozen=True)
class _Rate:
    input_per_mtok: float


# 벤더 공표 단가(USD / 100만 입력 토큰) — 실험 임계값 아님. 가격 변동 시 이 표만 갱신.
PRICING: dict[str, _Rate] = {
    "text-embedding-3-small": _Rate(0.02),
    "text-embedding-3-large": _Rate(0.13),
    "text-embedding-ada-002": _Rate(0.10),
}


def compute_cost_usd(model: str, input_tokens: int) -> float:
    rate = PRICING.get(model)
    if rate is None:
        return 0.0
    return input_tokens * rate.input_per_mtok / 1_000_000


class OpenAIEmbeddingProvider(LLMProvider):
    """OpenAI Embeddings API provider (임베딩 전용)."""

    name = "openai"

    def __init__(
        self,
        *,
        client: object | None = None,
        errors: object | None = None,
        api_key: str | None = None,
        model: str | None = None,
        dimensions: int | None = None,
    ) -> None:
        if client is None:
            try:
                import openai
            except ImportError as exc:  # pragma: no cover - 환경 의존
                raise ImportError(
                    "openai 패키지가 필요합니다: pip install 'kinder-intent-backend[openai]'"
                ) from exc
            # EMBEDDING_API_KEY(프로젝트 표준) 우선, 없으면 OPENAI_API_KEY(SDK 표준)로 폴백.
            key = api_key or os.environ.get("EMBEDDING_API_KEY") or os.environ.get("OPENAI_API_KEY")
            if not key:
                raise ValueError(
                    "API 키가 없습니다 — EMBEDDING_API_KEY 또는 OPENAI_API_KEY를 설정하라 "
                    "(openai embedding provider)"
                )
            client = openai.OpenAI(api_key=key, max_retries=0)  # 재시도는 LLMClient가 담당
            errors = openai
        self._client = client
        self._errors = errors
        self._model = model or os.environ.get("EMBEDDING_MODEL", DEFAULT_MODEL)
        self._dim = dimensions or int(os.environ.get("EMBEDDING_DIM", str(DEFAULT_DIM)))

    def _translate(self, exc: Exception) -> Exception:
        e = self._errors
        if e is not None:
            if isinstance(exc, getattr(e, "APITimeoutError", ())):
                return LLMTimeoutError(str(exc))
            if isinstance(exc, getattr(e, "APIConnectionError", ())):
                return LLMTransientError(str(exc))
            if isinstance(exc, getattr(e, "RateLimitError", ())):
                return LLMTransientError(str(exc))
            if isinstance(exc, getattr(e, "APIStatusError", ())):
                status = int(getattr(exc, "status_code", 500) or 500)
                if status >= 500:
                    return LLMTransientError(str(exc))
                return LLMPermanentError(str(exc))
        return LLMPermanentError(str(exc))

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        try:
            resp = self._client.embeddings.create(  # type: ignore[attr-defined]
                model=self._model, input=list(request.inputs), dimensions=self._dim
            )
        except Exception as exc:  # noqa: BLE001 — 변환 후 재던짐(LLMClient 재시도 판단)
            raise self._translate(exc) from exc

        vectors = [list(d.embedding) for d in resp.data]
        usage = resp.usage
        input_tokens = int(
            getattr(usage, "prompt_tokens", None) or getattr(usage, "total_tokens", 0)
        )
        model_id = getattr(resp, "model", self._model)
        return EmbeddingResult(
            vectors=vectors,
            model=model_id,
            provider=self.name,
            usage=Usage(prompt_tokens=input_tokens, completion_tokens=0),
            cost_usd=compute_cost_usd(model_id, input_tokens),
        )

    def complete(self, request: CompletionRequest) -> CompletionResult:
        raise NotImplementedError(
            "openai embedding provider는 completion을 지원하지 않는다 — LLM_PROVIDER로 completion "
            "provider(anthropic 등)를 주입하라."
        )
