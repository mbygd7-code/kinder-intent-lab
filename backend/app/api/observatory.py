"""GET /v1/observatory/brain — 3D Brain 렌더 상태 (§7-1·§7-5·§7-6).

원칙 8(절대 규칙 3): brightness 계열의 원천은 Arena뿐이다.
- ktib_global ← 최신 **run_type='brain'** arena_runs.metrics.first_intent_accuracy
  (zero-shot 베이스라인 run은 3D에 새지 않는다 — §8-2 베이스라인 규칙)
- node.heldout_accuracy ← brain_nodes 컬럼 그대로 (promote 경로만 기록; 여기선 읽기 전용)
- region.reliability ← region 내 비null heldout 평균 (전부 null이면 null)
- stage ← §7-6 성장 스테이지, 전부 위 Arena 산출에서 유도(저장하지 않고 매번 재계산)
여기서 어떤 값도 계산으로 지어내지 않는다 — 훈련량(size)·다양성(density)은 evidence_stats에서.
"""
from __future__ import annotations

import math

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.arena.stages import STAGE_NAMES, brain_stage, region_stages, stage4_inputs
from app.brain.diagnosis import diagnose_node
from app.brain.priors import current_state_version
from app.brain.version_gate import version_gate_status
from app.contracts.observatory import ObservatoryBrain, ObservatoryNode, ObservatoryRegion
from app.core.config import ExperimentsConfig, get_config
from app.core.db import get_session
from app.core.ontology import CANONICAL_DOMAINS, UNKNOWN_INTENT_ID, load_ontology
from app.models.arena import RUN_TYPE_BRAIN, ArenaRun
from app.models.brain import BrainNode, BrainVersion, Exemplar
from app.models.persona import PersonaCluster, PopulationPrior

router = APIRouter(prefix="/v1/observatory", tags=["observatory"])

# evidence_stats 버킷(§5-1 계약 EvidenceStats의 구조 상수 — 실험 임계값 아님)
_BUCKETS = ("synthetic", "weak_behavioral", "human_confirmed", "gold", "expert")


def _get_experiments() -> ExperimentsConfig:
    return get_config()


def _diversity(stats: dict) -> float:
    """Evidence Diversity(§7-5 Density 원천) = 버킷 분포의 정규화 섀넌 엔트로피 [0,1]."""
    counts = [int(stats.get(b, 0) or 0) for b in _BUCKETS]
    total = sum(counts)
    if total <= 0:
        return 0.0
    entropy = -sum((c / total) * math.log(c / total) for c in counts if c > 0)
    return round(entropy / math.log(len(_BUCKETS)), 4)


def _ktib_global(session: Session) -> float | None:
    """§7-1 중앙 수치 — 마지막 **brain** arena run만. 베이스라인 run은 밝기 원천이 아니다(§8-2)."""
    metrics = session.scalar(
        select(ArenaRun.metrics)
        .where(ArenaRun.run_type == RUN_TYPE_BRAIN)
        .order_by(ArenaRun.created_at.desc())
        .limit(1)
    )
    if not metrics:
        return None
    value = metrics.get("first_intent_accuracy")
    return float(value) if value is not None else None


def _brain_version(session: Session) -> str:
    v = session.scalar(
        select(BrainVersion.version)
        .where(BrainVersion.decision == "promote")
        .order_by(BrainVersion.created_at.desc())
    )
    return v or "seed-v0"


@router.get("/brain", response_model=ObservatoryBrain)
def brain_state(
    session: Session = Depends(get_session),
    config: ExperimentsConfig = Depends(_get_experiments),
) -> ObservatoryBrain:
    nodes = list(session.scalars(select(BrainNode)))
    exemplar_counts = dict(
        session.execute(
            select(Exemplar.node_id, func.count()).group_by(Exemplar.node_id)
        ).all()
    )

    out_nodes: list[ObservatoryNode] = []
    region_acc: dict[str, dict] = {
        d: {"nodes": 0, "gold": 0, "synthetic": 0, "heldouts": []} for d in CANONICAL_DOMAINS
    }
    for n in nodes:
        stats = n.evidence_stats or {}
        total = sum(int(stats.get(b, 0) or 0) for b in _BUCKETS)
        out_nodes.append(ObservatoryNode(
            node_id=n.node_id,
            intent_id=n.intent_id,
            region=n.region,
            evidence_total=total,
            evidence_diversity=_diversity(stats),
            gold_count=int(stats.get("gold", 0) or 0),
            exemplar_count=int(exemplar_counts.get(n.node_id, 0)),
            heldout_accuracy=n.heldout_accuracy,   # Arena 전용 컬럼 — 그대로 통과
            calibration_ece=n.calibration_ece,
            last_arena_run=n.last_arena_run,
            pending_evaluation=n.pending_evaluation,
        ))
        acc = region_acc[n.region]
        acc["nodes"] += 1
        acc["gold"] += int(stats.get("gold", 0) or 0)
        acc["synthetic"] += int(stats.get("synthetic", 0) or 0)
        if n.heldout_accuracy is not None:
            acc["heldouts"].append(float(n.heldout_accuracy))

    stages = region_stages(session, config)  # §7-6 — Arena 산출에서 유도
    regions = [
        ObservatoryRegion(
            region=d,
            reliability=(
                round(sum(a["heldouts"]) / len(a["heldouts"]), 4) if a["heldouts"] else None
            ),
            node_count=a["nodes"],
            gold_evidence=a["gold"],
            synthetic_evidence=a["synthetic"],
            stage=stages[d].stage,
            stage_name=stages[d].stage_name,
            measured_count=stages[d].measured_count,
        )
        for d, a in region_acc.items()
    ]

    ktib_global = _ktib_global(session)
    # Stage 4(Semantic Cross-Region Flow)는 confirmed cross-region edge + 동일 ktib_version의
    # 최근 W개 brain run 추세가 있어야 판정된다. 근거가 없으면 방출되지 않는다(§7-6).
    edges, run_history = stage4_inputs(session, config)
    global_stage = brain_stage(
        ktib_global, stages, config, edges=edges, run_history=run_history
    )
    return ObservatoryBrain(
        brain_version=_brain_version(session),
        ontology_version=load_ontology().version,
        ktib_global=ktib_global,
        brain_stage=global_stage,
        brain_stage_name=STAGE_NAMES[global_stage],
        regions=regions,
        nodes=out_nodes,
    )


# --- Persona Overlay (§4-2·§7-6, T5.4) ---


class PersonaOverlayCluster(BaseModel):
    cluster_id: str
    member_count: int | None
    state_version: str
    priors: dict[str, float]  # intent_id → persona prior (activation을 곱으로 재정렬, §5-5)


class PersonaOverlayOut(BaseModel):
    """같은 뇌를 페르소나 클러스터별 활성 분포로 전환해 본다 (§7-6).

    원천은 `population_priors` — §5-5에서 **LLM 밖에서 activation에 곱해지는 배수**다.
    측정된 클러스터별 정확도(Persona Lift/Harm)가 아니다. 그 지표는 아직 정의되지 않았다
    (docs/05-arena §6 TBD) — 없는 값을 이 응답에서 지어내지 않는다.
    """

    state_version: str | None
    prior_cap: float          # §5-5 persona_prior_cap — 오버레이가 과장돼 보이지 않도록 함께 준다
    clusters: list[PersonaOverlayCluster]


@router.get("/persona-overlay", response_model=PersonaOverlayOut)
def persona_overlay(
    session: Session = Depends(get_session),
    config: ExperimentsConfig = Depends(_get_experiments),
) -> PersonaOverlayOut:
    """클러스터별 prior 분포. 클러스터가 없으면 빈 목록(§4 Persona Discovery 미실행)."""
    state_version = current_state_version(session)
    clusters = {c.cluster_id: c for c in session.scalars(select(PersonaCluster))}
    if not clusters or state_version is None:
        return PersonaOverlayOut(
            state_version=state_version, prior_cap=config.brain.persona_prior_cap, clusters=[]
        )

    rows = session.scalars(
        select(PopulationPrior).where(PopulationPrior.state_version == state_version)
    ).all()
    grouped: dict[str, dict[str, float]] = {}
    for row in rows:
        grouped.setdefault(row.cluster_id, {})[row.intent_id] = float(row.prior)

    return PersonaOverlayOut(
        state_version=state_version,
        prior_cap=config.brain.persona_prior_cap,
        clusters=[
            PersonaOverlayCluster(
                cluster_id=cid,
                member_count=clusters[cid].member_count,
                state_version=state_version,
                priors=dict(sorted(priors.items())),
            )
            for cid, priors in sorted(grouped.items())
            if cid in clusters
        ],
    )


# --- 노드 Weakness 진단 (§7-3, T4.1 실계산) ---


class AxisOut(BaseModel):
    value: float | None  # §7-3 원값. null = 데이터 없음(계산 불가)
    level: str | None    # HIGH | MED | LOW | null


class NodeDiagnosisOut(BaseModel):
    intent_id: str
    ambiguous_language: AxisOut
    screen_context_coverage: AxisOut
    persona_diversity: AxisOut
    gold_data: AxisOut


@router.get("/node/{intent_id}/diagnosis", response_model=NodeDiagnosisOut)
def node_diagnosis(
    intent_id: str,
    session: Session = Depends(get_session),
    config: ExperimentsConfig = Depends(_get_experiments),
) -> NodeDiagnosisOut:
    """§7-3 4축 실계산. 데이터 없는 축은 value/level null(지어내지 않음)."""
    real = {i.intent_id for i in load_ontology().intents if i.intent_id != UNKNOWN_INTENT_ID}
    if intent_id not in real:
        raise HTTPException(status_code=404, detail="알 수 없는 intent")
    dg = diagnose_node(session, intent_id, config)

    def ax(a) -> AxisOut:
        return AxisOut(value=a.value, level=a.level)

    return NodeDiagnosisOut(
        intent_id=dg.intent_id,
        ambiguous_language=ax(dg.ambiguous_language),
        screen_context_coverage=ax(dg.screen_context_coverage),
        persona_diversity=ax(dg.persona_diversity),
        gold_data=ax(dg.gold_data),
    )


# --- Version Gate 상태 (§6-6, T4.5 — candidate pending 표시용, 읽기 전용) ---


class VersionGateOut(BaseModel):
    base_version: str
    new_gold: int
    min_new_gold: int
    condition_met: bool           # 신규 GOLD ≥ 임계 → 후보 빌드 가능
    pending_candidate: str | None  # 아직 Arena 판정 안 난 후보(있으면 버전명)


@router.get("/version-gate", response_model=VersionGateOut)
def version_gate(
    session: Session = Depends(get_session),
    config: ExperimentsConfig = Depends(_get_experiments),
) -> VersionGateOut:
    """§6-6 후보 생성 게이트 상태 — 읽기만 한다(후보 빌드는 배치 scripts/run_version_gate.py)."""
    s = version_gate_status(session, config)
    return VersionGateOut(
        base_version=s.base_version, new_gold=s.new_gold, min_new_gold=s.min_new_gold,
        condition_met=s.condition_met, pending_candidate=s.pending_candidate,
    )
