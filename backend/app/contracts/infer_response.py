"""infer_response.schema.json 파생 (runtime §3-1). is_multi_intent ↔ intent_plan 일관성 강제."""
from typing import Any, ClassVar, Literal

from pydantic import Field, model_validator

from app.contracts.base import Contract, Domain


class CandidateEvidence(Contract):
    signal: str
    detail: str


class ProposedAction(Contract):
    _reject_explicit_null: ClassVar[tuple[str, ...]] = (
        "target_objects", "params", "preview_available", "undoable",
    )

    action_type: str
    target_objects: list[str] | None = None
    params: dict[str, Any] | None = None
    preview_available: bool | None = None
    undoable: bool | None = None


class IntentCandidate(Contract):
    _reject_explicit_null: ClassVar[tuple[str, ...]] = ("evidence", "proposed_action")

    intent_id: str
    domain: Domain
    score: float = Field(ge=0, le=1)
    risk_tier: Literal["LOW", "MED", "HIGH", "CRITICAL"]
    requires_confirmation: bool
    evidence: list[CandidateEvidence] | None = None
    proposed_action: ProposedAction | None = None


class IntentPlan(Contract):
    _reject_explicit_null: ClassVar[tuple[str, ...]] = ("execution_order",)

    intents: list[str] = Field(min_length=2)
    relation: Literal["sequential", "parallel", "alternative"]
    execution_order: list[str] | None = None


class ClarificationOption(Contract):
    label: str
    intent_id: str


class Clarification(Contract):
    _reject_explicit_null: ClassVar[tuple[str, ...]] = ("question", "options")

    question: str | None = None
    options: list[ClarificationOption] | None = Field(default=None, min_length=2, max_length=2)


class InferResponse(Contract):
    # intent_plan·clarification·abstain_reason·compute_elapsed_ms·remaining_budget_ms는
    # 스키마상 nullable — 목록에서 제외
    _reject_explicit_null: ClassVar[tuple[str, ...]] = (
        "latency_ms", "persona_snapshot_hash", "fallback_used",
    )

    request_id: str
    schema_version: str
    model_version: str
    ontology_version: str
    latency_ms: int | None = None
    intent_candidates: list[IntentCandidate] = Field(max_length=5)
    top_intent: str
    confidence: float = Field(ge=0, le=1)
    margin: float = Field(ge=0, le=1)
    is_multi_intent: bool
    intent_plan: IntentPlan | None = None
    decision: Literal["execute", "suggest", "clarify", "abstain"]
    clarification: Clarification | None = None
    abstain_reason: Literal["LOW_CONFIDENCE", "OOD", "DEADLINE_RISK"] | None = None
    compute_elapsed_ms: int | None = None
    remaining_budget_ms: int | None = None
    persona_state_version: str
    persona_snapshot_hash: str | None = None
    fallback_used: bool | None = None
    # --- 투트랙 채택 D (2026-07-17 사용자 승인) — 킨더버스 연결 계약 3필드 ---
    # top_intent의 평가 위험 등급(리스크 모델 rm-1.x 파생 — 온톨로지 밖 평가 정책).
    # 후보가 없으면 null. 후보가 있으면 최상위 후보의 risk_tier와 일치해야 한다(아래 validator).
    risk_level: Literal["LOW", "MED", "HIGH", "CRITICAL"] | None = None
    # 예약 필드 — 슬롯 추출은 트랙2(킨더버스 연결) 소관. 구현 전까지 항상 null(지어내지 않는다).
    required_slots: list[str] | None = None
    # 추론이 실제 소비한 문맥 블록 에코(예: utterance·workspace_context·recent_actions·
    # teacher_context·persona_prior) — 빈 블록은 넣지 않는다(정직성).
    context_used: list[str] | None = None

    @model_validator(mode="after")
    def _multi_intent_consistency(self) -> "InferResponse":
        if self.is_multi_intent and self.intent_plan is None:
            raise ValueError("is_multi_intent=true ⇒ intent_plan 필수")
        if not self.is_multi_intent and self.intent_plan is not None:
            raise ValueError("is_multi_intent=false ⇒ intent_plan은 null")
        return self

    @model_validator(mode="after")
    def _risk_level_consistency(self) -> "InferResponse":
        """top-level risk_level은 편의 필드다 — 최상위 후보의 risk_tier와 어긋나면 계약 위반."""
        if self.risk_level is not None and self.intent_candidates:
            top = self.intent_candidates[0].risk_tier
            if self.risk_level != top:
                raise ValueError(f"risk_level({self.risk_level}) ≠ 최상위 후보 risk_tier({top})")
        return self
