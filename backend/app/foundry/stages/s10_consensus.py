"""S10. Consensus Labeler — S7~S9 종합 → 단일 정답이 아니라 label distribution (§1-S10).

합의도(consensus)와 disagreement를 함께 기록 — disagreement가 confusion 후보의 두 번째 공급원
(§5-6 CONSENSUS_DISAGREEMENT). label_distribution 합 = 1 (정규화). 신호 전무 시 UNKNOWN=1.0.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field

from app.core.config import ExperimentsConfig, get_config
from app.core.ontology import UNKNOWN_INTENT_ID
from app.foundry.stages.s7_analyst import IntentCandidate
from app.foundry.stages.s8_skeptic import ConfusionPair


@dataclass
class ConsensusResult:
    label_distribution: dict[str, float]
    top_intent: str
    consensus: float  # top intent 확률 (합의 강도 대리값)
    disagreement_pairs: list[list[str]] = field(default_factory=list)


def build_label_distribution(weighted: dict[str, float]) -> dict[str, float]:
    """intent별 가중치를 합=1로 정규화. 유한·양수만 반영, 총합 0이면 UNKNOWN=1.0."""
    clean = {i: w for i, w in weighted.items() if math.isfinite(w) and w > 0}
    total = sum(clean.values())
    if total <= 0 or not math.isfinite(total):
        return {UNKNOWN_INTENT_ID: 1.0}
    return {intent: w / total for intent, w in clean.items()}


def build_consensus(
    candidates: list[IntentCandidate],
    confusion_pairs: list[ConfusionPair] | None = None,
    config: ExperimentsConfig | None = None,
) -> ConsensusResult:
    """Analyst 후보 가중치를 분포로 정규화하고 disagreement를 수집한다.

    disagreement = Skeptic 쌍 + Analyst 상위 후보 간 이견(top1−top2 ≤ margin).
    """
    cfg = config or get_config()

    weighted: dict[str, float] = {}
    for c in candidates:
        weighted[c.intent_id] = weighted.get(c.intent_id, 0.0) + c.weight

    distribution = build_label_distribution(weighted)
    top_intent = max(distribution, key=distribution.__getitem__)

    disagreement: list[list[str]] = []
    for pair in confusion_pairs or []:
        disagreement.append([pair.from_true, pair.to_predicted])

    # Analyst 상위 후보 간 이견 (UNKNOWN 제외, top1−top2 ≤ margin)
    ranked = sorted(
        ((i, p) for i, p in distribution.items() if i != UNKNOWN_INTENT_ID),
        key=lambda kv: kv[1],
        reverse=True,
    )
    if len(ranked) >= 2:
        (i1, w1), (i2, w2) = ranked[0], ranked[1]
        if w1 - w2 <= cfg.foundry.consensus_disagreement_margin:
            if [i1, i2] not in disagreement and [i2, i1] not in disagreement:
                disagreement.append([i1, i2])

    return ConsensusResult(
        label_distribution=distribution,
        top_intent=top_intent,
        consensus=distribution[top_intent],
        disagreement_pairs=disagreement,
    )
