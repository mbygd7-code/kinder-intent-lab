"""LLM 계약 타입 + provider 추상 인터페이스 + 예외 계층.

client.py(래퍼)와 provider 구현(mock.py 등)이 공통으로 의존한다.
"""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

# --- 예외 계층 ---


class LLMError(Exception):
    """LLM 호출 계열 최상위 예외."""


class LLMTransientError(LLMError):
    """일시적 오류(429/5xx 등) — 재시도 대상."""


class LLMTimeoutError(LLMError):
    """호출이 timeout_s를 초과 — 재시도 대상."""


class LLMPermanentError(LLMError):
    """복구 불가 오류(잘못된 요청 등) — 재시도하지 않는다."""


# --- 요청·응답 타입 ---


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


@dataclass(frozen=True)
class CompletionRequest:
    prompt: str
    model: str
    system: str | None = None
    max_tokens: int | None = None
    temperature: float | None = None


@dataclass(frozen=True)
class CompletionResult:
    text: str
    model: str
    provider: str
    usage: Usage
    cost_usd: float


@dataclass(frozen=True)
class EmbeddingRequest:
    inputs: list[str]
    model: str


@dataclass(frozen=True)
class EmbeddingResult:
    vectors: list[list[float]]
    model: str
    provider: str
    usage: Usage
    cost_usd: float


@dataclass(frozen=True)
class LLMCallRecord:
    """호출 1건의 관측 기록 (토큰·비용·지연·재시도·성패)."""

    provider: str
    model: str
    operation: str  # "complete" | "embed"
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    cost_usd: float
    latency_ms: int
    attempts: int
    ok: bool
    error: str | None = None


# --- provider 추상 인터페이스 ---


class LLMProvider(ABC):
    """벤더별 원시 호출만 구현한다. 재시도·타임아웃·로깅은 LLMClient가 담당."""

    name: str

    @abstractmethod
    def complete(self, request: CompletionRequest) -> CompletionResult: ...

    @abstractmethod
    def embed(self, request: EmbeddingRequest) -> EmbeddingResult: ...
