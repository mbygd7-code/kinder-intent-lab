"""brain_node.schema.json 파생 (§5).

노드 자동 생성 금지(절대 규칙 4) · performance.heldout_accuracy는 Arena만 갱신(절대 규칙 3).
"""
from typing import ClassVar, Literal

from pydantic import Field

from app.contracts.base import Contract, Domain


class Exemplars(Contract):
    _reject_explicit_null: ClassVar[tuple[str, ...]] = ("count", "index", "diversity")

    count: int | None = None
    index: str | None = None
    diversity: float | None = None


class CounterExemplar(Contract):
    against: str
    count: int


class EvidenceStats(Contract):
    _reject_explicit_null: ClassVar[tuple[str, ...]] = (
        "synthetic", "weak_behavioral", "human_confirmed", "gold", "expert",
    )

    synthetic: int | None = None
    weak_behavioral: int | None = None
    human_confirmed: int | None = None
    gold: int | None = None
    expert: int | None = None


class NodePerformance(Contract):
    heldout_accuracy: float | None = None
    calibration_ece: float | None = None
    last_arena_run: str | None = None


class NodeCoverage(Contract):
    _reject_explicit_null: ClassVar[tuple[str, ...]] = (
        "scenario_coverage", "persona_entropy", "atlas_ambiguity",
    )

    scenario_coverage: float | None = None
    persona_entropy: float | None = None
    atlas_ambiguity: Literal["LOW", "MED", "HIGH"] | None = None


class BrainNode(Contract):
    # performance 내부 필드들은 스키마상 nullable — NodePerformance는 목록 불필요
    _reject_explicit_null: ClassVar[tuple[str, ...]] = (
        "exemplars", "counter_exemplars", "evidence_stats", "performance", "coverage",
    )

    node_id: str = Field(pattern=r"^N_")
    intent_id: str
    region: Domain
    definition_ref: str
    exemplars: Exemplars | None = None
    counter_exemplars: list[CounterExemplar] | None = None
    evidence_stats: EvidenceStats | None = None
    performance: NodePerformance | None = None
    coverage: NodeCoverage | None = None
    pending_evaluation: bool = False
