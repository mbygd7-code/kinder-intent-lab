"""observatory_brain.schema.json 파생 — 3D Brain 렌더 상태 계약.

원칙 8(절대 규칙 3): brightness 계열(heldout_accuracy·calibration_ece·last_arena_run,
region reliability, ktib_global)의 원천은 Arena뿐. Arena 미실행이면 null — 지어내지 않는다.
성장 스테이지(§7-6)도 전부 Arena 산출에서 유도된다.
"""
from pydantic import Field

from app.contracts.base import Contract, Domain


class ObservatoryRegion(Contract):
    region: Domain
    reliability: float | None = Field(ge=0, le=1)  # Arena heldout 집계 — 미실행 null
    node_count: int = Field(ge=0)
    gold_evidence: int = Field(ge=0)
    synthetic_evidence: int = Field(ge=0)
    stage: int = Field(ge=0, le=5)      # §7-6 — 0 Dormant … 3 Region Online (4는 미구현)
    stage_name: str
    measured_count: int = Field(ge=0)   # heldout이 측정된 노드 수 (미측정 ≠ 0%)


class ObservatoryNode(Contract):
    node_id: str
    intent_id: str
    region: Domain
    evidence_total: int = Field(ge=0)          # §7-5 Size ← Training Volume
    evidence_diversity: float = Field(ge=0, le=1)  # §7-5 Density ← Evidence Diversity
    gold_count: int = Field(ge=0)
    exemplar_count: int = Field(ge=0)
    heldout_accuracy: float | None = Field(default=None, ge=0, le=1)  # §7-5 Brightness — Arena만
    calibration_ece: float | None = None
    last_arena_run: str | None = None
    pending_evaluation: bool                    # §7-5 Pending Ring
    # §3-1 evidence 버킷별 개수(synthetic/weak_behavioral/human_confirmed/gold/expert).
    # 3D evidence 파티클의 원천(gold+expert = 스파크). 옵셔널 — 구 fixture 호환.
    evidence_buckets: dict[str, int] | None = None


class ObservatoryBrain(Contract):
    brain_version: str
    ontology_version: str
    ktib_global: float | None = Field(ge=0, le=1)  # §7-1 중앙 수치 — 마지막 brain arena run만
    brain_stage: int = Field(ge=0, le=5)           # §7-6 — 5 = KTIB 목표 도달
    brain_stage_name: str
    regions: list[ObservatoryRegion]
    nodes: list[ObservatoryNode]
