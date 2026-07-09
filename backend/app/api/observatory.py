"""GET /v1/observatory/brain — 3D Brain 렌더 상태 (§7-1·§7-5).

원칙 8(절대 규칙 3): brightness 계열의 원천은 Arena뿐이다.
- ktib_global ← 최신 arena_runs.metrics.first_intent_accuracy (run 없으면 null)
- node.heldout_accuracy ← brain_nodes 컬럼 그대로 (Arena 러너만 기록; 여기선 읽기 전용)
- region.reliability ← region 내 비null heldout 평균 (전부 null이면 null)
여기서 어떤 값도 계산으로 지어내지 않는다 — 훈련량(size)·다양성(density)은 evidence_stats에서.
"""
from __future__ import annotations

import math

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.contracts.observatory import ObservatoryBrain, ObservatoryNode, ObservatoryRegion
from app.core.db import get_session
from app.core.ontology import CANONICAL_DOMAINS, load_ontology
from app.models.arena import ArenaRun
from app.models.brain import BrainNode, BrainVersion, Exemplar

router = APIRouter(prefix="/v1/observatory", tags=["observatory"])

# evidence_stats 버킷(§5-1 계약 EvidenceStats의 구조 상수 — 실험 임계값 아님)
_BUCKETS = ("synthetic", "weak_behavioral", "human_confirmed", "gold", "expert")


def _diversity(stats: dict) -> float:
    """Evidence Diversity(§7-5 Density 원천) = 버킷 분포의 정규화 섀넌 엔트로피 [0,1]."""
    counts = [int(stats.get(b, 0) or 0) for b in _BUCKETS]
    total = sum(counts)
    if total <= 0:
        return 0.0
    entropy = -sum((c / total) * math.log(c / total) for c in counts if c > 0)
    return round(entropy / math.log(len(_BUCKETS)), 4)


def _ktib_global(session: Session) -> float | None:
    metrics = session.scalar(
        select(ArenaRun.metrics).order_by(ArenaRun.created_at.desc()).limit(1)
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
def brain_state(session: Session = Depends(get_session)) -> ObservatoryBrain:
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

    regions = [
        ObservatoryRegion(
            region=d,
            reliability=(
                round(sum(a["heldouts"]) / len(a["heldouts"]), 4) if a["heldouts"] else None
            ),
            node_count=a["nodes"],
            gold_evidence=a["gold"],
            synthetic_evidence=a["synthetic"],
        )
        for d, a in region_acc.items()
    ]

    return ObservatoryBrain(
        brain_version=_brain_version(session),
        ontology_version=load_ontology().version,
        ktib_global=_ktib_global(session),
        regions=regions,
        nodes=out_nodes,
    )
