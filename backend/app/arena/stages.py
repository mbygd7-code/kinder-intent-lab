"""§7-6 성장 스테이지 — 판정 기준은 전부 Arena 산출 (T5.4).

저장하지 않고 매번 재계산한다. 저장된 스테이지가 실제 밝기와 어긋난 상태를 만들지 않기 위해서다.

문서 §7-6 표를 그대로 옮길 수 없는 지점이 두 곳 있어 좁게 해석했다 (docs/05-arena §6에 기록):

1. Stage 1~3 기준이 서로 배타적이지 않다(측정비율 40% + reliability 60%는 어느 줄에도 없다)
   → **높은 단계부터 검사해 처음 만족하는 값**을 쓴다(단조 사다리).
2. Stage 4(Cross-Region Flow)는 "인접 region"이 설계 어디에도 정의돼 있지 않아 **판정하지 않는다**.
   인접성을 임의로 만들지 않는다. 따라서 전역 스테이지는 3에서 5로 건너뛴다.

이 모듈은 LLM·러너에 의존하지 않는다 — Observatory API가 가볍게 읽을 수 있어야 한다.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import ExperimentsConfig
from app.core.ontology import CANONICAL_DOMAINS
from app.models.brain import BrainNode

STAGE_NAMES = {
    0: "Dormant",
    1: "Spark",
    2: "Cluster Awake",
    3: "Region Online",
    4: "Cross-Region Flow",  # 미구현 — 위 주석 2 참조
    5: "Whole Brain Resonance",
}


@dataclass
class RegionStage:
    region: str
    stage: int
    stage_name: str
    reliability: float | None   # 측정된 노드 heldout 평균 (미측정이면 None)
    node_count: int
    measured_count: int


def region_stage(
    reliability: float | None, node_count: int, measured_count: int, config: ExperimentsConfig
) -> int:
    """만족하는 가장 높은 단계. Stage 4는 절대 반환하지 않는다(§7-6 해석 2)."""
    if measured_count == 0:
        return 0  # Dormant — 노드 heldout 미측정
    if reliability is not None and reliability >= config.stages.region_online_reliability:
        return 3  # Region Online
    if node_count and (measured_count / node_count) >= config.stages.cluster_awake_measured_ratio:
        return 2  # Cluster Awake
    return 1      # Spark — 측정 1회 이상


def region_stages(session: Session, config: ExperimentsConfig) -> dict[str, RegionStage]:
    """region별 스테이지. reliability는 **측정된 노드만** 평균낸다(미측정은 0%가 아니다)."""
    buckets: dict[str, list[float | None]] = {d: [] for d in CANONICAL_DOMAINS}
    for node in session.scalars(select(BrainNode)):
        buckets.setdefault(node.region, []).append(node.heldout_accuracy)

    out: dict[str, RegionStage] = {}
    for region, values in buckets.items():
        measured = [v for v in values if v is not None]
        reliability = round(sum(measured) / len(measured), 4) if measured else None
        stage = region_stage(reliability, len(values), len(measured), config)
        out[region] = RegionStage(
            region=region, stage=stage, stage_name=STAGE_NAMES[stage],
            reliability=reliability, node_count=len(values), measured_count=len(measured),
        )
    return out


def brain_stage(
    ktib_global: float | None, regions: dict[str, RegionStage], config: ExperimentsConfig
) -> int:
    """전역 스테이지. global ≥ KTIB 목표면 5, 아니면 region 최고 단계 (4는 건너뛴다)."""
    if ktib_global is not None and ktib_global >= config.arena.first_intent_accuracy_target:
        return 5
    return max((r.stage for r in regions.values()), default=0)
