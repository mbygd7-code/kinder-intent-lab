"""Arena → Observatory 반영 잡 (§7-5·§7-6, T5.4).

**Arena 결과만이 3D 뇌의 brightness와 edge flicker를 바꾼다**(§8-2, 절대 규칙 3 / 원칙 8):

| 시각 요소 | 저장 위치 | 이 모듈에서 |
|---|---|---|
| Node Brightness | `brain_nodes.heldout_accuracy` | promote 시에만 (promote.resolve_candidate) |
| Edge Flicker | `confusion_edges.confusion_rate` | 모든 brain run (runner.apply_confusion_edges) |
| Pending Ring | `brain_nodes.pending_evaluation` | promote 시 소등 (§6-7 [9]) |

강제 수단은 `models.guards.arena_brightness_write` 컨텍스트 + flush 리스너다 — 훈련 코드가
brightness를 대입하면 `BrightnessWriteBlocked`로 실패한다.

`zero_shot_baseline` run은 반영 대상이 아니다(§8-2 베이스라인 규칙) — 여기서 loud-fail한다.

§7-6 성장 스테이지도 여기서 계산한다. 전부 Arena 산출에서 유도되며 어떤 값도 저장하지 않는다
(읽을 때마다 재계산 — 저장된 스테이지가 실제 밝기와 어긋나는 상태를 만들지 않기 위해).
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.arena.runner import apply_confusion_edges
from app.core.config import ExperimentsConfig
from app.core.ontology import CANONICAL_DOMAINS
from app.models.arena import RUN_TYPE_BRAIN, ArenaRun
from app.models.brain import BrainNode

# §7-6 스테이지 이름 (4는 미구현 — 아래 region_stage 참조)
STAGE_NAMES = {
    0: "Dormant",
    1: "Spark",
    2: "Cluster Awake",
    3: "Region Online",
    4: "Cross-Region Flow",
    5: "Whole Brain Resonance",
}


class BaselineRunNotReflectable(Exception):
    """zero-shot 베이스라인 run을 3D 뇌에 반영하려 함 — 밝기의 원천은 brain run뿐 (§8-2)."""


@dataclass
class ReflectResult:
    run_id: str
    edges_touched: int
    resonance: bool  # promote 순간의 Full Brain Resonance 발동 여부(§6-6)


def reflect_arena_run(
    session: Session, run: ArenaRun, config: ExperimentsConfig, *, promoted: bool = False
) -> ReflectResult:
    """arena run을 3D 뇌 상태에 반영한다 — edge flicker 갱신 (+ promote면 Resonance 표시).

    brightness는 여기서 쓰지 않는다: promote 판정을 통과한 candidate에 한해
    `promote.resolve_candidate`가 `arena_brightness_write` 컨텍스트 안에서 쓴다(§6-7 [9]).
    정기(주간) run은 edge flicker만 갱신한다 — 승격 없이 밝아지는 경로는 없다.
    """
    if run.run_type != RUN_TYPE_BRAIN:
        raise BaselineRunNotReflectable(
            f"run {run.run_id}(run_type={run.run_type})은 3D 반영 대상이 아니다 (§8-2)"
        )
    edges = apply_confusion_edges(session, run)
    return ReflectResult(run_id=run.run_id, edges_touched=edges, resonance=promoted)


# --- §7-6 성장 스테이지 (전부 Arena 산출에서 유도) ---


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
    """§7-6 판정 — 만족하는 가장 높은 단계를 취한다(단조 사다리).

    문서 §7-6의 Stage 1~3 기준은 서로 배타적이지 않다(예: 측정 비율 40% + reliability 60%는
    어느 줄에도 정확히 걸리지 않는다). 여기서는 **높은 단계부터 검사해 처음 만족하는 값**을
    쓴다. 이 해석은 docs/05-arena/README.md §8에 기록돼 있다.

    Stage 4(Cross-Region Flow)는 '인접 region' 정의가 설계에 없어 **판정하지 않는다** —
    없는 개념을 지어내지 않는다. Stage 5는 global 지표이므로 region 단위로 반환하지 않는다.
    """
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


def brain_stage(ktib_global: float | None, regions: dict[str, RegionStage],
                config: ExperimentsConfig) -> int:
    """전역 스테이지. global ≥ 목표면 5(Whole Brain Resonance), 아니면 region 최고 단계.

    Stage 4는 판정하지 않으므로 3에서 5로 건너뛴다 (§7-6 표의 Cross-Region Flow 미구현).
    """
    if ktib_global is not None and ktib_global >= config.arena.first_intent_accuracy_target:
        return 5
    return max((r.stage for r in regions.values()), default=0)
