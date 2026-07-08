"""Label Aggregator — evidence 집합 → label distribution + 게이트 (§3-6, §3-3).

Snorkel류 weak supervision: 개별 신호는 부정확하고 상관될 수 있으므로 신호 수·합의·충돌을
함께 본다. 게이트(전부 config): 독립 신호 수 ≥ min_label_functions ∧ aggregate_confidence ≥
임계 ∧ conflict_score ≤ 임계.

절대 규칙 6: adversarial=true evidence는 자연 분포 학습·집계에서 분리(제외).
절대 규칙 10: evidence_type 고정 서열을 만들지 않는다 — 가중치는 strength × 실측 신뢰도.
"""
from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from app.aggregator.state_machine import advance_label_state
from app.core.config import ExperimentsConfig


@dataclass(frozen=True)
class EvidenceSignal:
    """집계 입력 단위 (Evidence ORM에서 파생 가능)."""

    intent_id: str
    polarity: str  # supports | refutes
    strength: float
    evidence_type: str
    actor_type: str
    trainer_ref: str | None = None
    reliability: float | None = None
    adversarial: bool = False


@dataclass(frozen=True)
class AggregationResult:
    label_distribution: dict[str, float]
    top_intent: str | None
    signal_count: int
    aggregate_confidence: float
    conflict_score: float
    excluded_adversarial: int


def _signal_key(s: EvidenceSignal) -> tuple[str, str, str | None]:
    """독립 신호 식별 — 같은 (evidence_type, actor, trainer)는 하나의 labeling function."""
    return (s.evidence_type, s.actor_type, s.trainer_ref)


def _clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))


def _weight(s: EvidenceSignal) -> float:
    # 실측 신뢰도 기반 (evidence_type 고정 서열 금지 — 절대 규칙 10).
    # strength·reliability를 [0,1]로 클램프 — 음수 부호반전·과대 가중 방지(DB 밖 입력 대비).
    reliability = s.reliability if s.reliability is not None else 1.0
    return _clamp01(s.strength) * _clamp01(reliability)


def aggregate(signals: Iterable[EvidenceSignal], config: ExperimentsConfig) -> AggregationResult:
    """adversarial 제외 후 intent별 순가중치를 분포로 정규화하고 신호·합의·충돌을 계산."""
    all_signals = list(signals)
    active = [s for s in all_signals if not s.adversarial]
    excluded = len(all_signals) - len(active)

    # 정보량 0(가중치 0)인 신호는 독립 신호로 세지 않는다 — 빈 신호로 게이트를 채우지 못하게
    signal_count = len({_signal_key(s) for s in active if _weight(s) > 0})

    net: dict[str, float] = {}
    for s in active:
        delta = _weight(s) if s.polarity == "supports" else -_weight(s)
        net[s.intent_id] = net.get(s.intent_id, 0.0) + delta

    positive = {i: w for i, w in net.items() if w > 0}
    total = sum(positive.values())
    if total <= 0:
        return AggregationResult({}, None, signal_count, 0.0, 0.0, excluded)

    distribution = {i: w / total for i, w in positive.items()}
    ranked = sorted(distribution.values(), reverse=True)
    top_intent = max(distribution, key=distribution.__getitem__)
    confidence = ranked[0]
    conflict = ranked[1] if len(ranked) > 1 else 0.0  # 최강 경쟁자의 몫

    return AggregationResult(distribution, top_intent, signal_count, confidence, conflict, excluded)


def evaluate_gate(result: AggregationResult, config: ExperimentsConfig) -> bool:
    """SILVER 게이트 — 신호 수·합의·충돌 3조건 (전부 config)."""
    lac = config.label_aggregator
    return (
        result.signal_count >= lac.min_label_functions
        and result.aggregate_confidence >= lac.aggregate_confidence_min
        and result.conflict_score <= lac.conflict_max
    )


def recommend_tier(result: AggregationResult, config: ExperimentsConfig) -> str:
    """게이트 통과 → SILVER, 신호는 있으나 미통과 → BRONZE, 신호 없음 → UNVERIFIED.

    GOLD은 절대 반환하지 않는다 — 인간 검수 2인 일치로만 도달(§3-3).
    """
    if evaluate_gate(result, config):
        return "SILVER"
    # BRONZE는 유효 라벨(positive 분포)이 있을 때만 — 전부 refute면 라벨 없음 → UNVERIFIED
    if result.signal_count > 0 and result.label_distribution:
        return "BRONZE"
    return "UNVERIFIED"


def recommend_state(result: AggregationResult, config: ExperimentsConfig) -> str:
    """Aggregator 결과 상태 — 통과 시 LABEL_CANDIDATE, 아니면 REVIEW_REQUIRED (§3-6)."""
    return "LABEL_CANDIDATE" if evaluate_gate(result, config) else "REVIEW_REQUIRED"


def apply_aggregation(
    episode, result: AggregationResult, config: ExperimentsConfig
) -> None:
    """집계 결과를 에피소드에 반영 — label_state(전이 검증)와 reliability_tier를 각각 독립 갱신.

    episode는 AGGREGATION_READY 상태여야 한다 (advance_label_state가 전이를 검증).
    """
    advance_label_state(episode, recommend_state(result, config))
    episode.reliability_tier = recommend_tier(result, config)
    episode.label_distribution = result.label_distribution or {"UNKNOWN": 1.0}
    episode.consensus = result.aggregate_confidence


def signals_from_rows(rows: Iterable[object]) -> list[EvidenceSignal]:
    """Evidence ORM 행 → EvidenceSignal (adversarial은 evidence.adversarial 컬럼)."""
    return [
        EvidenceSignal(
            intent_id=r.intent_id,
            polarity=r.polarity,
            strength=r.strength,
            evidence_type=r.evidence_type,
            actor_type=r.actor_type,
            trainer_ref=r.trainer_ref,
            reliability=r.reliability,
            adversarial=bool(r.adversarial),
        )
        for r in rows
    ]
