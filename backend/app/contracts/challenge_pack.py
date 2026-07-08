"""challenge_pack.schema.json 파생 (§6-4)."""
from typing import Any, ClassVar, Literal

from pydantic import Field

from app.contracts.base import Contract

PackTrigger = Literal["observatory_click", "scheduled", "version_gate_campaign"]
Diagnosis = Literal[
    "COVERAGE_LOW", "GOLD_LOW", "CONFUSION_HIGH",
    "PERSONA_DIVERSITY_LOW", "AMBIGUOUS_LANGUAGE_HIGH", "PERFORMANCE_DROP",
]
Strategy = Literal["A_DATA_COVERAGE", "B_HUMAN_EVIDENCE", "C_CONFUSION", "D_MODEL"]
DifficultyCurve = Literal["easy", "medium", "medium_to_hard", "hard", "adversarial"]
DeliveryMode = Literal[
    "guess_my_intent", "choose_right_meaning", "screen_context_challenge",
    "correction_drill", "persona_contrast", "break_the_brain",
]


class PackOrigin(Contract):
    _reject_explicit_null: ClassVar[tuple[str, ...]] = ("diagnosis",)  # node·region은 nullable

    trigger: PackTrigger
    node: str | None = None
    region: str | None = None
    diagnosis: list[Diagnosis] | None = None


class TargetEdge(Contract):
    from_true: str
    to_predicted: str


class ChallengePack(Contract):
    _reject_explicit_null: ClassVar[tuple[str, ...]] = (
        "target_edges", "difficulty_curve", "persona_mix", "expected_yield",
    )

    pack_id: str = Field(pattern=r"^CP_")
    origin: PackOrigin
    strategy: list[Strategy] = Field(min_length=1)
    target_edges: list[TargetEdge] | None = None
    items: int = Field(ge=1)
    difficulty_curve: DifficultyCurve | None = None
    persona_mix: list[str] | None = None
    delivery_modes: list[DeliveryMode]
    expected_yield: dict[str, Any] | None = None
