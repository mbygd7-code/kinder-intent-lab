"""오프라인 mock provider — 결정론적 응답·임베딩. 테스트 전체가 오프라인 실행되게 한다.

토큰 수는 길이 기반 추정, 비용은 cost_per_1k_tokens로 산출(기본 0).
실제 벤더 호출은 없다.
"""
from __future__ import annotations

import hashlib
import math

from app.llm.base import (
    CompletionRequest,
    CompletionResult,
    EmbeddingRequest,
    EmbeddingResult,
    LLMProvider,
    Usage,
)

DEFAULT_EMBED_DIM = 1536  # DB의 vector(1536)와 일치


def estimate_tokens(text: str) -> int:
    """대략 4자 = 1토큰 (offline 추정, 벤더 무관)."""
    return max(1, math.ceil(len(text) / 4))


def _deterministic_vector(text: str, dim: int) -> list[float]:
    """텍스트 해시로 시드한 결정론적 단위 벡터."""
    vec: list[float] = []
    counter = 0
    while len(vec) < dim:
        digest = hashlib.sha256(f"{text}#{counter}".encode()).digest()
        for i in range(0, len(digest), 4):
            if len(vec) >= dim:
                break
            n = int.from_bytes(digest[i : i + 4], "big")
            vec.append((n / 2**32) * 2 - 1)  # [-1, 1)
        counter += 1
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


class MockProvider(LLMProvider):
    name = "mock"

    def __init__(
        self,
        embed_dim: int = DEFAULT_EMBED_DIM,
        cost_per_1k_tokens: float = 0.0,
        canned: dict[str, str] | None = None,
    ) -> None:
        self._embed_dim = embed_dim
        self._cost_per_1k = cost_per_1k_tokens
        self._canned = canned or {}

    def _cost(self, usage: Usage) -> float:
        return usage.total_tokens / 1000 * self._cost_per_1k

    def complete(self, request: CompletionRequest) -> CompletionResult:
        text = self._canned.get(request.prompt, f"[mock:{request.model}] {request.prompt}")
        usage = Usage(
            prompt_tokens=estimate_tokens(request.prompt),
            completion_tokens=estimate_tokens(text),
        )
        return CompletionResult(
            text=text, model=request.model, provider=self.name,
            usage=usage, cost_usd=self._cost(usage),
        )

    def embed(self, request: EmbeddingRequest) -> EmbeddingResult:
        vectors = [_deterministic_vector(t, self._embed_dim) for t in request.inputs]
        usage = Usage(
            prompt_tokens=sum(estimate_tokens(t) for t in request.inputs),
            completion_tokens=0,
        )
        return EmbeddingResult(
            vectors=vectors, model=request.model, provider=self.name,
            usage=usage, cost_usd=self._cost(usage),
        )
