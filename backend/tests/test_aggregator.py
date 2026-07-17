"""T1.10 AC (§3-3·§3-6, 절대 규칙 6·8).

- 허용되지 않는 상태 전이 거부 (예: UNLABELED→LABELED 직행)
- 신호 1개로 SILVER 승격 불가
- adversarial=true evidence는 집계 제외 (자연 분포와 분리)
- label_state(워크플로)와 reliability_tier(품질)를 혼용하지 않는다
"""
import pytest

from app.aggregator.aggregator import (
    EvidenceSignal,
    aggregate,
    apply_aggregation,
    evaluate_gate,
    recommend_state,
    recommend_tier,
)
from app.aggregator.state_machine import (
    ALLOWED_TRANSITIONS,
    IllegalTransition,
    advance_label_state,
    assert_transition,
    can_transition,
)
from app.core.config import get_config
from app.models.episodes import Episode

CFG = get_config()


# --- 상태 기계 (AC 1) ---


def test_legal_transitions_allowed() -> None:
    for src, targets in ALLOWED_TRANSITIONS.items():
        for dst in targets:
            assert can_transition(src, dst) is True


def test_illegal_direct_transition_rejected() -> None:
    assert can_transition("UNLABELED", "LABELED") is False
    with pytest.raises(IllegalTransition):
        assert_transition("UNLABELED", "LABELED")


def test_illegal_skip_rejected() -> None:
    # EVIDENCE_ACCUMULATING → LABEL_CANDIDATE (AGGREGATION_READY 건너뜀)
    with pytest.raises(IllegalTransition):
        assert_transition("EVIDENCE_ACCUMULATING", "LABEL_CANDIDATE")


def test_terminal_states_have_no_exit() -> None:
    assert ALLOWED_TRANSITIONS["LABELED"] == set()
    assert ALLOWED_TRANSITIONS["REJECTED"] == set()
    with pytest.raises(IllegalTransition):
        assert_transition("LABELED", "REVIEW_REQUIRED")


def test_unknown_state_rejected() -> None:
    with pytest.raises(IllegalTransition):
        assert_transition("AGGREGATION_READY", "BANANA")


def _episode(state: str) -> Episode:
    return Episode(
        episode_id=f"EP_SM_{state}",
        ontology_version="onto-1.0",
        dataset_split="TRAIN",
        reliability_tier="UNVERIFIED",
        label_state=state,
        origin_channel="FOUNDRY_SYNTHETIC",
        episode_creator_type="FOUNDRY_PIPELINE",
        primary_subject_type="SIMULATED_TEACHER",
        teacher_prompt="다음엔?",
        label_distribution={"UNKNOWN": 1.0},
    )


def test_advance_label_state_valid() -> None:
    ep = _episode("AGGREGATION_READY")
    advance_label_state(ep, "LABEL_CANDIDATE")
    assert ep.label_state == "LABEL_CANDIDATE"


def test_advance_label_state_illegal_leaves_state() -> None:
    ep = _episode("UNLABELED")
    with pytest.raises(IllegalTransition):
        advance_label_state(ep, "LABELED")
    assert ep.label_state == "UNLABELED"


# --- Aggregator: 신호·분포 ---


def _sig(intent="play_expand", polarity="supports", strength=0.8, etype="SYNTHETIC_CONSENSUS",
         actor="LLM_ANALYST", trainer=None, reliability=0.9, adversarial=False) -> EvidenceSignal:
    return EvidenceSignal(
        intent_id=intent, polarity=polarity, strength=strength, evidence_type=etype,
        actor_type=actor, trainer_ref=trainer, reliability=reliability, adversarial=adversarial,
    )


def test_distribution_sums_to_one() -> None:
    result = aggregate(
        [_sig(intent="play_expand"), _sig(intent="text_naturalize", etype="DOMAIN_RULE",
                                          actor="RULE_ENGINE")],
        CFG,
    )
    assert abs(sum(result.label_distribution.values()) - 1.0) <= 0.01


def test_independent_signal_counting() -> None:
    # 같은 (evidence_type, actor, trainer) = 1 신호
    same = [_sig(), _sig()]
    assert aggregate(same, CFG).signal_count == 1
    # 서로 다른 출처 = 2 신호
    diff = [_sig(), _sig(etype="HUMAN_CORRECTION", actor="TEACHER_TRAINER", trainer="TR_1")]
    assert aggregate(diff, CFG).signal_count == 2


def test_refute_reduces_intent_weight() -> None:
    supported = aggregate([_sig(intent="play_expand", strength=0.9)], CFG)
    refuted = aggregate(
        [
            _sig(intent="play_expand", strength=0.9),
            _sig(intent="play_expand", polarity="refutes", strength=0.8,
                 etype="HUMAN_CORRECTION", actor="TEACHER_TRAINER", trainer="TR_1"),
        ],
        CFG,
    )
    assert refuted.label_distribution.get("play_expand", 0.0) < supported.label_distribution[
        "play_expand"
    ] + 1e-9  # refute가 순가중치를 낮춘다 (여기선 top이 유지되되 감소)


# --- AC 3: adversarial 집계 제외 ---


def test_adversarial_evidence_excluded() -> None:
    signals = [
        _sig(intent="play_expand", trainer="TR_1", etype="HUMAN_CORRECTION",
             actor="TEACHER_TRAINER"),
        _sig(intent="play_expand", etype="DOMAIN_RULE", actor="RULE_ENGINE"),
        _sig(intent="break_the_brain_intent", adversarial=True),  # 분리 대상
    ]
    result = aggregate(signals, CFG)
    assert result.excluded_adversarial == 1
    assert "break_the_brain_intent" not in result.label_distribution
    assert result.signal_count == 2  # adversarial은 신호로도 세지 않는다


def test_all_adversarial_yields_no_signal() -> None:
    result = aggregate([_sig(adversarial=True), _sig(adversarial=True)], CFG)
    assert result.signal_count == 0
    assert result.excluded_adversarial == 2
    assert recommend_tier(result, CFG) == "UNVERIFIED"


def test_zero_weight_signal_not_counted() -> None:
    """정보량 0(reliability=0) 신호는 게이트를 채우지 못한다 — 실질 1신호."""
    signals = [
        _sig(intent="play_expand", strength=0.95, reliability=0.95),
        _sig(intent="play_expand", reliability=0.0,  # weight 0
             etype="HUMAN_CONFIRMATION", actor="TEACHER_TRAINER", trainer="TR_1"),
    ]
    result = aggregate(signals, CFG)
    assert result.signal_count == 1
    assert recommend_tier(result, CFG) != "SILVER"


def test_reliability_clamped_no_sign_flip() -> None:
    """음수 reliability가 refute를 support처럼 부양(부호 이중반전)해 승자를 바꾸지 않는다.

    클램프 없으면 refute text_naturalize(rel=-0.9)가 +0.81로 부양돼 승자가 뒤집힌다.
    """
    result = aggregate(
        [
            _sig(intent="play_expand", polarity="supports", strength=0.5, reliability=0.5),
            _sig(intent="text_naturalize", polarity="refutes", strength=0.9, reliability=-0.9,
                 etype="DOMAIN_RULE", actor="RULE_ENGINE"),
        ],
        CFG,
    )
    assert result.top_intent == "play_expand"
    assert "text_naturalize" not in result.label_distribution


def test_all_refute_is_unverified() -> None:
    """전부 refute면 유효 라벨이 없다 → BRONZE가 아니라 UNVERIFIED."""
    result = aggregate(
        [
            _sig(intent="play_expand", polarity="refutes", strength=0.9),
            _sig(intent="play_expand", polarity="refutes", strength=0.8,
                 etype="DOMAIN_RULE", actor="RULE_ENGINE"),
        ],
        CFG,
    )
    assert result.label_distribution == {}
    assert recommend_tier(result, CFG) == "UNVERIFIED"


def test_db_rejects_out_of_range_reliability(db_session) -> None:
    """evidence.reliability는 DB에서 [0,1]로 제약 (마이그레이션 0005)."""
    from sqlalchemy.exc import IntegrityError

    ep = _episode("UNLABELED")
    ep.episode_id = "EP_REL_1"
    db_session.add(ep)
    db_session.flush()
    from app.models.episodes import Evidence

    db_session.add(
        Evidence(
            evidence_id="EV_REL_1", episode_id="EP_REL_1", intent_id="play_expand",
            polarity="supports", strength=0.8, evidence_type="DOMAIN_RULE",
            actor_type="RULE_ENGINE", reliability=2.0,
        )
    )
    with pytest.raises(IntegrityError, match="evidence_reliability_range"):
        db_session.flush()


# --- AC 2: 신호 1개로 SILVER 불가 ---


def test_single_signal_not_silver() -> None:
    result = aggregate([_sig(strength=0.95, reliability=0.95)], CFG)
    assert result.signal_count == 1
    assert evaluate_gate(result, CFG) is False
    assert recommend_tier(result, CFG) != "SILVER"
    assert recommend_tier(result, CFG) == "BRONZE"


def test_two_agreeing_signals_pass_gate_silver() -> None:
    signals = [
        _sig(intent="play_expand", strength=0.95, reliability=0.95),
        _sig(intent="play_expand", strength=0.9, reliability=0.9,
             etype="HUMAN_CONFIRMATION", actor="TEACHER_TRAINER", trainer="TR_9"),
    ]
    result = aggregate(signals, CFG)
    assert result.signal_count >= CFG.label_aggregator.min_label_functions
    assert evaluate_gate(result, CFG) is True
    assert recommend_tier(result, CFG) == "SILVER"
    assert recommend_state(result, CFG) == "LABEL_CANDIDATE"


def test_high_conflict_routes_to_review() -> None:
    # 두 intent가 팽팽 → conflict_score 높음 → 게이트 실패 → REVIEW_REQUIRED
    signals = [
        _sig(intent="play_expand", strength=0.9, reliability=0.9),
        _sig(intent="text_naturalize", strength=0.9, reliability=0.9,
             etype="DOMAIN_RULE", actor="RULE_ENGINE"),
    ]
    result = aggregate(signals, CFG)
    assert result.conflict_score > CFG.label_aggregator.conflict_max
    assert evaluate_gate(result, CFG) is False
    assert recommend_state(result, CFG) == "REVIEW_REQUIRED"


def test_never_recommends_gold() -> None:
    strong = [
        _sig(strength=1.0, reliability=1.0),
        _sig(strength=1.0, reliability=1.0, etype="EXPERT_REVIEW", actor="DOMAIN_EXPERT",
             trainer="EX_1"),
        _sig(strength=1.0, reliability=1.0, etype="HUMAN_CONFIRMATION", actor="TEACHER_TRAINER",
             trainer="TR_2"),
    ]
    assert recommend_tier(aggregate(strong, CFG), CFG) != "GOLD"  # GOLD은 사람 검수만


# --- apply_aggregation: 상태 + tier 동시 반영 (혼용 아님 — 각 축 독립 계산) ---


def _agg_ready_episode(db_session) -> Episode:
    ep = _episode("AGGREGATION_READY")
    ep.episode_id = "EP_APPLY_1"
    db_session.add(ep)
    db_session.flush()
    return ep


def test_apply_aggregation_gate_pass(db_session) -> None:
    ep = _agg_ready_episode(db_session)
    signals = [
        _sig(intent="play_expand", strength=0.95, reliability=0.95),
        _sig(intent="play_expand", strength=0.9, reliability=0.9,
             etype="HUMAN_CONFIRMATION", actor="TEACHER_TRAINER", trainer="TR_9"),
    ]
    result = aggregate(signals, CFG)
    apply_aggregation(ep, result, CFG)
    db_session.flush()
    assert ep.label_state == "LABEL_CANDIDATE"
    assert ep.reliability_tier == "SILVER"
    assert abs(sum(ep.label_distribution.values()) - 1.0) <= 0.01


def test_apply_aggregation_requires_aggregation_ready(db_session) -> None:
    ep = _episode("UNLABELED")
    ep.episode_id = "EP_APPLY_2"
    db_session.add(ep)
    db_session.flush()
    result = aggregate([_sig(), _sig(etype="DOMAIN_RULE", actor="RULE_ENGINE")], CFG)
    with pytest.raises(IllegalTransition):
        apply_aggregation(ep, result, CFG)


# --- config 임계값 사용 (리터럴 아님) ---


def test_gate_uses_config_thresholds() -> None:
    lac = CFG.label_aggregator
    # confidence가 임계 바로 아래면 게이트 실패
    from dataclasses import replace

    base = aggregate(
        [
            _sig(intent="play_expand", strength=0.95, reliability=0.95),
            _sig(intent="play_expand", strength=0.9, reliability=0.9,
                 etype="HUMAN_CONFIRMATION", actor="TEACHER_TRAINER", trainer="TR_9"),
        ],
        CFG,
    )
    below = replace(base, aggregate_confidence=lac.aggregate_confidence_min - 0.01)
    assert evaluate_gate(below, CFG) is False
    at = replace(base, aggregate_confidence=lac.aggregate_confidence_min, conflict_score=0.0)
    assert evaluate_gate(at, CFG) is True


# --- evidence_type_weights 실구현 AC (절대 규칙 10 — 가중치는 config, 2026-07-17) ---


def _weights_cfg(weights):
    return CFG.model_copy(update={
        "label_aggregator": CFG.label_aggregator.model_copy(
            update={"evidence_type_weights": weights}
        )
    })


def _wsig(intent, etype, strength=0.8):
    return EvidenceSignal(
        intent_id=intent, polarity="supports", strength=strength,
        evidence_type=etype, actor_type="LLM_ANALYST", reliability=1.0,
    )


def test_weights_empirical_mode_unchanged() -> None:
    """'empirical'(기본)은 현행 실측 가중 그대로 — 동률 두 신호는 반반."""
    r = aggregate([_wsig("A", "T1"), _wsig("B", "T2")], CFG)
    assert abs(r.label_distribution["A"] - 0.5) < 1e-9


def test_weights_dict_scales_and_zero_kills_signal() -> None:
    """dict 모드: type별 배율이 실제로 적용된다 — 0배는 신호 수에서도 빠진다."""
    cfg = _weights_cfg({"T1": 2.0, "T2": 0.0})
    r = aggregate([_wsig("A", "T1"), _wsig("B", "T2"), _wsig("B", "T3")], cfg)
    # A: 0.8×2.0=1.6 / B: T2죽고 T3만 0.8 → A 2/3
    assert abs(r.label_distribution["A"] - (1.6 / 2.4)) < 1e-9
    assert r.signal_count == 2  # T2는 정보량 0 — 독립 신호로 안 센다


def test_weights_unknown_mode_rejected_early() -> None:
    """오타 모드 문자열은 조기 폭발 — 조용한 무시(유령 키) 재발 방지."""
    cfg = _weights_cfg("fixed_rank")
    with pytest.raises(ValueError, match="empirical"):
        aggregate([_wsig("A", "T1")], cfg)


def test_weights_negative_factor_rejected() -> None:
    """음수 배율은 조기 폭발 — 부호 반전으로 evidence가 정반대로 작동하는 사고 차단(적대 검증)."""
    cfg = _weights_cfg({"T1": -1.0})
    with pytest.raises(ValueError, match="음수"):
        aggregate([_wsig("A", "T1")], cfg)
