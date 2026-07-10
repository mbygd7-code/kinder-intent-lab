"""Risk Model rm-1.0 AC (2026-07-10 확정): evaluation_critical 지정.

- CRITICAL 7종, 축 ∈ {E, D, R}, 전부 온톨로지 실재 intent
- config.arena.critical_intents와 정확히 일치 (drift 시 loud-fail)
- obs_tag_children은 ELEVATED — 내부 변이를 egress와 이중 게이트하지 않는다(CWAR 희석 방지)
- visual_privacy_mask는 STANDARD — 위험 방향은 CWAR-miss가 잡는다
- 위험 등급은 온톨로지에 들어가지 않는다 (replay 축 churn 방지)
"""
import pytest
from sqlalchemy import delete, func, select

from app.core.config import get_config
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.core.risk_model import (
    RISK_MODEL_EVENT,
    assert_config_coherence,
    get_risk_model,
    load_risk_model,
    record_risk_model_update,
)
from app.models.governance import GovernanceEvent

CFG = get_config()
RM = get_risk_model()


def test_risk_model_shape() -> None:
    assert RM.risk_model_version == "rm-1.0"
    assert {a.id for a in RM.axes} == {"E", "D", "R"}
    assert set(RM.tiers) == {"CRITICAL", "ELEVATED", "STANDARD"}


def test_exactly_seven_critical_with_axes() -> None:
    """CRITICAL 7종. 과잉 지정은 CWAR를 희석하고, 과소 지정은 위험하다."""
    critical = [i for i in RM.intents if i.tier == "CRITICAL"]
    assert len(critical) == 7
    assert all(i.axis in {"E", "D", "R"} for i in critical)
    assert all(i.rationale for i in critical)


def test_all_graded_intents_exist_in_ontology() -> None:
    """유령 intent 금지 — 등급표의 모든 id가 온톨로지에 실재한다."""
    real = {i.intent_id for i in load_ontology().intents if i.intent_id != UNKNOWN_INTENT_ID}
    assert {i.intent_id for i in RM.intents} <= real


def test_critical_set_matches_config() -> None:
    """★ config.arena.critical_intents가 CRITICAL 집합과 정확히 일치해야 한다.

    config를 비우면 §6-6 critical 절과 CWAR가 **조용히** 무력화된다 — 그 경로를 막는다.
    """
    assert RM.critical_intents == sorted(CFG.arena.critical_intents)
    assert_config_coherence(CFG.arena.critical_intents)  # 예외 없이 통과


def test_config_drift_loud_fails() -> None:
    with pytest.raises(ValueError, match="critical_intents 불일치"):
        assert_config_coherence(["op_workspace_delete"])  # 6종 누락


def test_obs_tag_children_is_elevated_not_critical() -> None:
    """★ 내부 신원 결합은 재태깅 가능하고, 비가역 피해는 이미-CRITICAL인 egress로만 실현된다.

    egress 경계에서 게이트하고 내부 변이를 이중 게이트하지 않는다 (CWAR 희석 방지).
    """
    assert RM.tier_of("obs_tag_children") == "ELEVATED"
    assert "obs_tag_children" not in RM.critical_intents


def test_visual_privacy_mask_is_standard_and_covered_by_cwar_miss() -> None:
    """마스킹 실패(아동 얼굴 노출)는 fire 방향으로 못 본다 → CWAR-miss가 잡는다(2026-07-10 결정)."""
    assert RM.tier_of("visual_privacy_mask") == "STANDARD"
    assert CFG.gate.cwar_miss_max <= 1.0  # miss 방향 게이트가 실제로 존재한다


def test_unlisted_intent_defaults_to_standard() -> None:
    assert RM.tier_of("play_expand") == "STANDARD"


def test_elevated_intents_never_enter_critical_set() -> None:
    """ELEVATED는 UX/telemetry 티어일 뿐 — CWAR·게이트에 들어가면 지표가 희석된다."""
    elevated = {i.intent_id for i in RM.intents if i.tier == "ELEVATED"}
    assert elevated and not (elevated & set(RM.critical_intents))


# --- 계약 위반 loud-fail ---


def test_critical_without_axis_rejected(tmp_path) -> None:
    bad = tmp_path / "rm.yaml"
    bad.write_text(
        "risk_model_version: rm-9.9\n"
        "axes:\n- {id: E, name: n, question: q}\n"
        "tiers: [CRITICAL, ELEVATED, STANDARD]\n"
        "intents:\n- {intent_id: op_workspace_delete, tier: CRITICAL, axis: null, rationale: r}\n",
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="위험 축"):
        load_risk_model(bad)


def test_ghost_intent_rejected(tmp_path) -> None:
    bad = tmp_path / "rm.yaml"
    bad.write_text(
        "risk_model_version: rm-9.9\n"
        "axes:\n- {id: D, name: n, question: q}\n"
        "tiers: [CRITICAL, ELEVATED, STANDARD]\n"
        "intents:\n- {intent_id: not_a_real_intent, tier: CRITICAL, axis: D, rationale: r}\n",
        encoding="utf-8",
    )
    with pytest.raises(Exception, match="온톨로지에 없는 intent"):
        load_risk_model(bad)


# --- 온톨로지 불변 (replay 축 churn 방지) ---


def test_ontology_carries_no_risk_grade() -> None:
    """★ 위험 등급은 intent의 '의미'가 아니라 '평가 정책'이다 — 온톨로지에 넣지 않는다.

    넣으면 등급을 고칠 때마다 ontology_version이 올라가 arena_runs의 replay 축이 흔들린다.
    """
    onto = load_ontology()
    assert onto.version == "onto-1.0"  # 위험 모델 도입이 온톨로지를 bump하지 않았다
    intent = onto.intents[0]
    assert not hasattr(intent, "risk_tier") and not hasattr(intent, "evaluation_critical")


# --- 거버넌스 ---


def test_risk_model_update_records_governance_event(db_session) -> None:
    """위험 등급 지정·개정은 승인 흔적을 남긴다 (원칙 9의 정신)."""
    db_session.execute(delete(GovernanceEvent).where(
        GovernanceEvent.event_type == RISK_MODEL_EVENT
    ))
    db_session.flush()

    event = record_risk_model_update(db_session, approved_by="lab")
    assert event.event_type == RISK_MODEL_EVENT
    assert event.payload["risk_model_version"] == "rm-1.0"
    assert event.payload["critical_intents"] == RM.critical_intents

    count = db_session.scalar(
        select(func.count()).select_from(GovernanceEvent).where(
            GovernanceEvent.event_type == RISK_MODEL_EVENT
        )
    )
    assert count == 1
