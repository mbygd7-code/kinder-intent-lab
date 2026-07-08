"""evidence.schema.json 파생 (§3-1). actor_type은 명시 — evidence에서 역추론 금지 (절대 규칙 9)."""
from typing import ClassVar, Literal

from pydantic import Field

from app.contracts.base import Contract

EvidenceType = Literal[
    "SYNTHETIC_CONSENSUS", "WEAK_BEHAVIORAL", "DOMAIN_RULE",
    "HUMAN_CORRECTION", "HUMAN_CONFIRMATION", "EXPERT_REVIEW",
]
ActorType = Literal[
    "LLM_ANALYST", "DOMAIN_EXPERT", "TEACHER_TRAINER",
    "STAFF_TRAINER", "BEHAVIOR_SIGNAL", "RULE_ENGINE",
]


class Actor(Contract):
    actor_type: ActorType
    trainer_ref: str | None = None
    reliability: float | None = Field(default=None, ge=0, le=1)


class EvidenceContext(Contract):
    gym_mode: str | None = None
    challenge_pack: str | None = None
    adversarial: bool = False  # 절대 규칙 6: true는 자연 분포 학습·집계에서 분리
    source: str | None = None


class Evidence(Contract):
    _reject_explicit_null: ClassVar[tuple[str, ...]] = ("context",)

    evidence_id: str = Field(pattern=r"^EV_")
    episode_id: str = Field(pattern=r"^EP_")
    intent_id: str
    polarity: Literal["supports", "refutes"]
    strength: float = Field(ge=0, le=1)
    evidence_type: EvidenceType
    actor: Actor
    context: EvidenceContext | None = None
    created_at: int
