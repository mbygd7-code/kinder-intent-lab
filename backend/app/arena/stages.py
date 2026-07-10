"""§7-6 성장 스테이지 — 판정 기준은 전부 Arena 산출 (T5.4, Stage 4는 2026-07-10 확정).

저장하지 않고 매번 재계산한다(읽기 시점 VIEW). 저장된 스테이지가 실제 밝기와 어긋난 상태를
만들지 않기 위해서고, Stage 4가 run 이력에 의존해 `arena_runs`에 얼려두면 replay가 깨지기 때문이다.

문서 §7-6 표를 그대로 옮길 수 없는 지점이 두 곳 있었다 (docs/05-arena §6에 기록):

1. **Stage 1~3 기준이 서로 배타적이지 않다** (측정비율 40% + reliability 60%는 어느 줄에도 없다)
   → **높은 단계부터 검사해 처음 만족하는 값**을 쓴다(단조 사다리). **확정.**
2. **Stage 4의 "인접 region"이 설계에 정의돼 있지 않다.** 공간 인접 그래프를 발명하지 않고,
   Arena가 실측하는 유일한 인접 신호인 **cross-region confusion**으로 **재정의**했다:
   *Semantic Cross-Region Flow*. 두 region의 intent 사이에 `state='confirmed'`인 방향성 혼동
   edge가 있으면 의미적으로 인접하다 — 뇌가 실제로 헷갈렸다는 뜻이므로.

   인접을 **rate가 아니라 state로** 판정하는 것이 핵심이다. `apply_confusion_edges`는 state를
   절대 낮추지 않고(단조) 혼동이 사라지면 `confusion_rate=0.0`으로만 소등하므로, **혼동이 줄어
   목표를 달성해도 인접이 사라지지 않는다.** rate를 인접 기준으로 삼으면 Stage 4는 도달하는
   순간 스스로를 지운다.
"""
from __future__ import annotations

from collections.abc import Iterable, Sequence
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import ExperimentsConfig
from app.core.ontology import CANONICAL_DOMAINS, load_ontology
from app.models.arena import ArenaRun
from app.models.brain import BrainNode, ConfusionEdge

STAGE_NAMES = {
    0: "Dormant",
    1: "Spark",
    2: "Cluster Awake",
    3: "Region Online",
    4: "Semantic Cross-Region Flow",
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
    """만족하는 가장 높은 단계. region 단위는 0~3만 반환한다.

    Stage 4는 region 쌍 사이의 *흐름*이고 Stage 5는 global 지표라, 둘 다 brain_stage 소관이다.
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


# --- Stage 4: Semantic Cross-Region Flow (§7-6, 2026-07-10 확정) ---


def _region_of(intent_id: str, domains: dict[str, str | None]) -> str | None:
    return domains.get(intent_id)


def _bridges(edges: Iterable[ConfusionEdge]) -> dict[frozenset[str], list[tuple[str, str]]]:
    """의미적 인접 region 쌍 → 그 쌍을 잇는 방향성 confirmed cross-region edge 목록.

    `hypothesized`/`observed`는 다리를 놓지 않는다: 순간 잡음이 인접을 지어내지 못하게.
    온톨로지에 매핑되지 않는 intent(UNKNOWN 등)는 드롭한다 — region을 추측하지 않는다.
    """
    domains = {i.intent_id: i.domain for i in load_ontology().intents}
    out: dict[frozenset[str], list[tuple[str, str]]] = {}
    for edge in edges:
        if edge.state != "confirmed":
            continue
        a = _region_of(edge.from_true, domains)
        b = _region_of(edge.to_predicted, domains)
        if a is None or b is None or a == b:
            continue  # 같은 region 내 혼동은 '흐름'이 아니다
        out.setdefault(frozenset((a, b)), []).append((edge.from_true, edge.to_predicted))
    return {pair: sorted(v) for pair, v in out.items()}


def adjacent_pairs(edges: Iterable[ConfusionEdge]) -> set[frozenset[str]]:
    """의미적으로 인접한 region 쌍 (confirmed cross-region 혼동 edge가 만드는 무향 그래프)."""
    return set(_bridges(edges))


def rate_in_run(run: ArenaRun, from_true: str, to_predicted: str) -> float | None:
    """그 run의 confusion_matrix에서 방향성 pair의 rate. 없으면 None(=혼동 미관측)."""
    for row in run.confusion_matrix or []:
        if row.get("from_true") == from_true and row.get("to_predicted") == to_predicted:
            return float(row["confusion_rate"])
    return None


def _mean_bridge_rate(run: ArenaRun, directed: list[tuple[str, str]]) -> float | None:
    """주요 다리들의 평균 rate. rate 0.0도 유효 표본이다(혼동 소멸 = 흐름). 미관측은 0으로 본다.

    이 run에서 정답 A가 아예 측정되지 않았다면 rate는 None인데, 그때는 표본에서 뺀다 —
    미측정을 0으로 채워 '개선됐다'고 주장하지 않는다.
    """
    seen: list[float] = []
    for from_true, to_predicted in directed:
        r = rate_in_run(run, from_true, to_predicted)
        measured = from_true in ((run.metrics or {}).get("by_node") or {})
        if r is not None:
            seen.append(r)
        elif measured:
            seen.append(0.0)  # 정답 A는 측정됐고 A→B 오답이 하나도 없었다 = rate 0
    return (sum(seen) / len(seen)) if seen else None


def cross_region_flow(
    regions: dict[str, RegionStage],
    edges: Sequence[ConfusionEdge],
    run_history: Sequence[ArenaRun],
    config: ExperimentsConfig,
) -> bool:
    """§7-6 Stage 4 — "인접 region ≥ 70% ∧ 주요 confusion edge 감소 추세".

    `run_history`는 **동일 ktib_version의 brain run**을 오래된 순으로 정확히 W개 받는다
    (호출자 책임). 다른 ktib_version을 섞으면 신·구 벤치마크를 같은 축에 그리게 된다(§8-2).

    미측정은 미충족이 아니다: 윈도가 W개에 못 미치면 추세는 NULL이고 Stage 4는 방출되지 않는다.
    """
    window = config.stages.cross_region_trend_window
    if len(run_history) < window:
        return False  # 추세 NULL — 지어내지 않는다

    online = {
        r for r, s in regions.items()
        if s.reliability is not None and s.reliability >= config.stages.region_online_reliability
    }
    start, end = run_history[0], run_history[-1]

    for pair, directed in sorted(_bridges(edges).items(), key=lambda kv: sorted(kv[0])):
        if not pair <= online:
            continue  # 두 인접 region 모두 Region Online이어야 한다
        # '주요' 다리를 **윈도 시작 run에서 스냅샷**한다 — 이후 rate가 떨어져도 집합이 안 바뀐다.
        major = [
            d for d in directed
            if (r := rate_in_run(start, *d)) is not None
            and r >= config.stages.cross_region_major_edge_min
        ]
        if not major:
            continue  # 시작 시점에 '주요' 다리가 없었다 — 감소를 주장할 대상이 없다
        oldest = _mean_bridge_rate(start, major)
        newest = _mean_bridge_rate(end, major)
        if oldest is None or newest is None:
            continue
        if (oldest - newest) >= config.stages.cross_region_trend_min_drop:
            return True
    return False


def brain_stage(
    ktib_global: float | None,
    regions: dict[str, RegionStage],
    config: ExperimentsConfig,
    *,
    edges: Sequence[ConfusionEdge] | None = None,
    run_history: Sequence[ArenaRun] | None = None,
) -> int:
    """전역 스테이지 (highest-satisfied-wins).

    5 = global ≥ KTIB 목표 → 4 = Semantic Cross-Region Flow → region 최고 단계(0~3).

    `edges`/`run_history`를 주지 않는 경량 호출자는 Stage 4 평가를 **생략**한다 — 근거 없이
    4를 지어내지 않고 3-or-5로 떨어진다.
    """
    if ktib_global is not None and ktib_global >= config.arena.first_intent_accuracy_target:
        return 5
    if edges is not None and run_history is not None and cross_region_flow(
        regions, edges, run_history, config
    ):
        return 4
    return max((r.stage for r in regions.values()), default=0)


# --- Observatory 편의: Stage 4 입력 조회 (동일 ktib_version brain run 윈도) ---


def stage4_inputs(
    session: Session, config: ExperimentsConfig
) -> tuple[list[ConfusionEdge], list[ArenaRun]]:
    """confirmed edge 전체 + **현행 뇌를 잰** 최근 W개 brain run(오래된 순, 동일 ktib_version).

    candidate run(`<base>-rcN`)은 제외한다 — reject된 후보의 점수로 성장 추세를 그리면 존재하지
    않는 뇌의 상태를 렌더하게 된다(§6-6 "reject → 숫자는 폐기된다").
    """
    from app.brain.version_gate import current_brain_version  # 지역 import — 순환 방지
    from app.models.arena import RUN_TYPE_BRAIN

    edges = list(session.scalars(select(ConfusionEdge)))
    brain_version = current_brain_version(session)
    latest = session.scalar(
        select(ArenaRun)
        .where(
            ArenaRun.run_type == RUN_TYPE_BRAIN,
            ArenaRun.model_version == brain_version,
        )
        .order_by(ArenaRun.created_at.desc())
        .limit(1)
    )
    if latest is None:
        return edges, []
    window = config.stages.cross_region_trend_window
    recent = list(session.scalars(
        select(ArenaRun)
        .where(
            ArenaRun.run_type == RUN_TYPE_BRAIN,
            ArenaRun.model_version == brain_version,
            ArenaRun.ktib_version == latest.ktib_version,  # 신·구 벤치마크를 섞지 않는다(§8-2)
        )
        .order_by(ArenaRun.created_at.desc())
        .limit(window)
    ))
    return edges, list(reversed(recent))  # 오래된 순
