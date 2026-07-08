"""실 Claude(Anthropic) completion provider — 벤더 어댑터.

LLMClient(추상 인터페이스)가 재시도·타임아웃·토큰/비용 로깅을 담당하므로 여기서는 벤더 원시
호출만 한다. provider는 env(LLM_PROVIDER)로 주입되며(CLAUDE.md 기술 스택), 이 모듈만이
Anthropic SDK를 안다 — 파이프라인/러너 코드에 벤더 하드코딩은 없다.

임베딩은 담당하지 않는다 — Anthropic은 임베딩 API가 없다. 임베딩은 별도 EMBEDDING_PROVIDER.

주의:
- SDK import는 지연(생성 시점) — mock 전용 오프라인 환경은 anthropic 패키지가 없어도 된다.
- 재시도는 LLMClient가 하므로 SDK 자체 재시도는 끈다(max_retries=0) — 이중 재시도 방지.
- adaptive-thinking 계열(Opus 4.8/4.7·Sonnet 5·Fable 5)은 temperature/top_p를 거부(400)하므로
  샘플링 파라미터를 전달하지 않는다. thinking도 생략(구조화 JSON 추출엔 불필요).
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

# 완성 모델·응답 상한은 벤더 운영 파라미터 — env로 주입(experiments.yaml의 실험 임계값 아님).
DEFAULT_MODEL = "claude-opus-4-8"
DEFAULT_MAX_TOKENS = 4096


@dataclass(frozen=True)
class _Rate:
    input_per_mtok: float
    output_per_mtok: float


# 벤더 공표 단가(USD / 100만 토큰) — 실험 임계값이 아니라 벤더 사실. 가격 변동 시 이 표만 갱신.
# (캐시 read/creation 토큰은 별도 단가지만 여기선 input/output만 반영 — 보수적 상한.)
PRICING: dict[str, _Rate] = {
    "claude-fable-5": _Rate(10.0, 50.0),
    "claude-opus-4-8": _Rate(5.0, 25.0),
    "claude-opus-4-7": _Rate(5.0, 25.0),
    "claude-opus-4-6": _Rate(5.0, 25.0),
    "claude-sonnet-5": _Rate(3.0, 15.0),
    "claude-sonnet-4-6": _Rate(3.0, 15.0),
    "claude-haiku-4-5": _Rate(1.0, 5.0),
}


def compute_cost_usd(model: str, input_tokens: int, output_tokens: int) -> float:
    """모델별 단가로 비용 산출. 미등록 모델은 0.0(가격 미상 — 날조하지 않는다)."""
    rate = PRICING.get(model)
    if rate is None:
        return 0.0
    return (input_tokens * rate.input_per_mtok + output_tokens * rate.output_per_mtok) / 1_000_000


class AnthropicProvider(LLMProvider):
    """Anthropic Messages API completion provider.

    테스트/DI를 위해 client·errors를 주입할 수 있다. 미주입 시 env(LLM_API_KEY)로 실 SDK를 만든다.
    """

    name = "anthropic"

    def __init__(
        self,
        *,
        client: object | None = None,
        errors: object | None = None,
        api_key: str | None = None,
        model: str | None = None,
        max_tokens: int | None = None,
    ) -> None:
        if client is None:
            try:
                import anthropic
            except ImportError as exc:  # pragma: no cover - 환경 의존
                raise ImportError(
                    "anthropic 패키지가 필요합니다: pip install 'kinder-intent-backend[anthropic]'"
                ) from exc
            # LLM_API_KEY(프로젝트 표준) 우선, 없으면 ANTHROPIC_API_KEY(SDK 표준)로 폴백.
            key = api_key or os.environ.get("LLM_API_KEY") or os.environ.get("ANTHROPIC_API_KEY")
            if not key:
                raise ValueError(
                    "API 키가 없습니다 — LLM_API_KEY 또는 ANTHROPIC_API_KEY를 설정하라 "
                    "(anthropic provider)"
                )
            # 재시도는 LLMClient가 담당 — SDK 자체 재시도는 끈다(이중 재시도 방지)
            client = anthropic.Anthropic(api_key=key, max_retries=0)
            errors = anthropic
        self._client = client
        self._errors = errors
        self._model = model or os.environ.get("LLM_MODEL", DEFAULT_MODEL)
        self._max_tokens = max_tokens or int(
            os.environ.get("LLM_MAX_TOKENS", str(DEFAULT_MAX_TOKENS))
        )

    def _translate(self, exc: Exception) -> Exception:
        """SDK 예외를 프로젝트 예외 계층으로 변환(LLMClient 재시도 정책이 이걸 본다)."""
        e = self._errors
        if e is not None:
            # 순서 중요: APITimeoutError ⊂ APIConnectionError, RateLimitError ⊂ APIStatusError
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

    def complete(self, request: CompletionRequest) -> CompletionResult:
        kwargs: dict = {
            "model": self._model,
            "max_tokens": request.max_tokens or self._max_tokens,
            "messages": [{"role": "user", "content": request.prompt}],
        }
        if request.system:
            kwargs["system"] = request.system
        # temperature/top_p는 의도적으로 미전달(adaptive-thinking 모델 400 방지).
        try:
            resp = self._client.messages.create(**kwargs)  # type: ignore[attr-defined]
        except Exception as exc:  # noqa: BLE001 — 변환 후 재던짐(LLMClient가 재시도 판단)
            raise self._translate(exc) from exc

        if getattr(resp, "stop_reason", None) == "refusal":
            # 안전 분류기 거부 — 재시도 불가(같은 요청은 다시 거부). 러너가 실패로 격리.
            raise LLMPermanentError(f"모델 거부(refusal): {getattr(resp, 'stop_details', None)}")

        text = "".join(
            getattr(b, "text", "") for b in resp.content if getattr(b, "type", None) == "text"
        )
        usage = Usage(
            prompt_tokens=int(resp.usage.input_tokens),
            completion_tokens=int(resp.usage.output_tokens),
        )
        model_id = getattr(resp, "model", self._model)
        return CompletionResult(
            text=text,
            model=model_id,
            provider=self.name,
            usage=usage,
            cost_usd=compute_cost_usd(model_id, usage.prompt_tokens, usage.completion_tokens),
        )

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        raise NotImplementedError(
            "Anthropic은 임베딩 API가 없다 — EMBEDDING_PROVIDER로 별도 임베딩 provider를 주입하라 "
            "(DB는 vector(1536)이므로 1536차원 모델 필요)."
        )
