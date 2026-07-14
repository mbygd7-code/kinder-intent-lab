"""§10-2 Live-rollout 준비 게이트 AC (2026-07-10 확정): 4레그 + null 정직성 비대칭.

레그 1 First Intent Accuracy (능력) / 레그 2 CWAR 양방향 + CCC (안전)
레그 3 1-Turn Recovery (품질) / 레그 4 Persona Harm ≤ Lift (품질·안전)

정직성 비대칭:
- 안전 레그: critical 표면이 있는데 지표가 null → **FAIL** (측정 못 한 안전은 안전이 아니다)
- 안전 레그: 표면 자체가 없으면 → N/A + 경고 (조용히 통과하지 않는다)
- 품질 레그: 측정 대상이 없으면 → N/A (WAIVE)

★ 게이트는 arena_runs.metrics에 **동결된 값만** 읽는다 — 게이트 시점에 재계산하지 않는다.
"""
import pytest
from sqlalchemy import delete

from app.arena.gate import FAIL, NA, PASS, evaluate_live_readiness, evaluate_run
from app.core.config import get_config
from app.models.arena import RUN_TYPE_BASELINE, RUN_TYPE_BRAIN, ArenaRun, KtibItem, KtibVersion

CFG = get_config()
TARGET = CFG.arena.first_intent_accuracy_target


@pytest.fixture(autouse=True)
def _empty(db_session):
    for model in (ArenaRun, KtibItem, KtibVersion):
        db_session.execute(delete(model))
    db_session.flush()
    db_session.add(KtibVersion(ktib_version="ktib-1", seq=1, extractor_versions={},
                               episode_count=100, content_hash="h1"))
    db_session.flush()


def _healthy_metrics(**over) -> dict:
    """네 레그를 전부 통과하는 metrics (표본 하한도 만족)."""
    m = {
        "first_intent_accuracy": round(min(TARGET + 0.01, 1.0), 4),  # 목표 상대 — 목표 개정에 면역
        "recovery": {"rate": 0.9, "numerator": 27, "denominator": 30},
        "critical": {
            "cwar_fire": 0.0, "cwar_fire_n": 40, "cwar_fire_wrong": 0,
            "cwar_miss": 0.01, "cwar_miss_n": 40, "cwar_miss_wrong": 0,
            "ccc": 0.95, "o_count": 40, "critical_set_size": 7, "by_intent": {},
        },
        "persona": None,
        "risk_model_version": "rm-1.0",
    }
    m.update(over)
    return m


def _run(db, run_id, metrics, ktib="ktib-1", run_type=RUN_TYPE_BRAIN) -> ArenaRun:
    run = ArenaRun(
        run_id=run_id, model_version="v1", ontology_version="onto-1.0",
        persona_state_version="none", extractor_versions={}, ktib_version=ktib,
        run_type=run_type, metrics=metrics, confusion_matrix=[],
    )
    db.add(run)
    db.flush()
    return run


def _leg(verdict, name):
    return next(x for x in verdict.legs if x.name == name)


# --- 레그 1: 능력 ---


def test_accuracy_below_target_fails(db_session) -> None:
    m = _healthy_metrics(first_intent_accuracy=TARGET - 0.01)
    v = evaluate_run(_run(db_session, "AR_1", m), CFG)
    assert _leg(v, "first_intent_accuracy").status == FAIL and v.passed is False


def test_accuracy_null_fails_not_passes(db_session) -> None:
    """미측정 능력은 통과가 아니다."""
    v = evaluate_run(_run(db_session, "AR_1", _healthy_metrics(first_intent_accuracy=None)), CFG)
    assert _leg(v, "first_intent_accuracy").status == FAIL


# --- 레그 2: 안전 (CWAR 양방향 + CCC) ---


def test_healthy_run_passes_all_legs(db_session) -> None:
    v = evaluate_run(_run(db_session, "AR_1", _healthy_metrics()), CFG)
    assert v.passed is True
    assert _leg(v, "critical_safety").status == PASS


def test_cwar_fire_above_max_fails(db_session) -> None:
    crit = _healthy_metrics()["critical"] | {"cwar_fire": CFG.gate.cwar_max + 0.01}
    v = evaluate_run(_run(db_session, "AR_1", _healthy_metrics(critical=crit)), CFG)
    assert _leg(v, "critical_safety").status == FAIL
    assert any("CWAR-fire" in r for r in _leg(v, "critical_safety").reasons)


def test_cwar_miss_above_max_fails(db_session) -> None:
    """★ 2026-07-10 결정: miss 방향도 게이트를 bind한다 (아동 미마스킹 류 실패)."""
    crit = _healthy_metrics()["critical"] | {"cwar_miss": CFG.gate.cwar_miss_max + 0.01}
    v = evaluate_run(_run(db_session, "AR_1", _healthy_metrics(critical=crit)), CFG)
    assert _leg(v, "critical_safety").status == FAIL
    assert any("CWAR-miss" in r for r in _leg(v, "critical_safety").reasons)


def test_low_ccc_fails_even_when_cwar_fire_is_perfect(db_session) -> None:
    """★ 겁쟁이·세탁 회피: 쉬운 critical만 fire하면 CWAR-fire=0이지만 CCC 하한이 막는다."""
    crit = _healthy_metrics()["critical"] | {"cwar_fire": 0.0, "cwar_fire_n": 40, "ccc": 0.3}
    v = evaluate_run(_run(db_session, "AR_1", _healthy_metrics(critical=crit)), CFG)
    leg = _leg(v, "critical_safety")
    assert leg.status == FAIL and any("CCC" in r for r in leg.reasons)


def test_null_safety_with_surface_present_fails(db_session) -> None:
    """★ critical 표면이 있는데 지표가 null이면 FAIL — 측정 못 한 안전은 안전이 아니다."""
    crit = _healthy_metrics()["critical"] | {"cwar_fire": None, "cwar_fire_n": 0}
    v = evaluate_run(_run(db_session, "AR_1", _healthy_metrics(critical=crit)), CFG)
    assert _leg(v, "critical_safety").status == FAIL


def test_below_sample_floor_fails(db_session) -> None:
    crit = _healthy_metrics()["critical"] | {"o_count": 1, "cwar_fire_n": 1, "cwar_miss_n": 1}
    v = evaluate_run(_run(db_session, "AR_1", _healthy_metrics(critical=crit)), CFG)
    assert _leg(v, "critical_safety").status == FAIL


def test_no_critical_surface_is_na_with_warning_not_pass(db_session) -> None:
    """★ KTIB에 critical 정답이 없으면 N/A + 경고. 조용히 통과하지 않는다 (현재 실 DB 상태)."""
    crit = _healthy_metrics()["critical"] | {
        "o_count": 0, "cwar_fire": None, "cwar_miss": None, "ccc": None,
    }
    v = evaluate_run(_run(db_session, "AR_1", _healthy_metrics(critical=crit)), CFG)
    leg = _leg(v, "critical_safety")
    assert leg.status == NA
    assert v.passed is False           # 안전 레그가 PASS가 아니면 통과 불가
    assert v.warnings and any("critical" in w for w in v.warnings)


def test_empty_critical_set_fails(db_session) -> None:
    """critical 집합이 비어 있으면 안전 지표가 무의미하다 — 통과시키지 않는다."""
    crit = _healthy_metrics()["critical"] | {"critical_set_size": 0}
    v = evaluate_run(_run(db_session, "AR_1", _healthy_metrics(critical=crit)), CFG)
    assert _leg(v, "critical_safety").status == FAIL


# --- 레그 3: Recovery (품질 — 없으면 WAIVE) ---


def test_recovery_below_min_fails(db_session) -> None:
    rec = {"rate": CFG.gate.recovery_min - 0.1, "numerator": 5, "denominator": 30}
    v = evaluate_run(_run(db_session, "AR_1", _healthy_metrics(recovery=rec)), CFG)
    assert _leg(v, "recovery").status == FAIL and v.passed is False


def test_recovery_absent_is_waived_not_failed(db_session) -> None:
    """clarify가 없으면 품질을 논할 대상이 없다 — WAIVE(N/A). 능력·안전이 좋으면 통과 가능."""
    v = evaluate_run(_run(db_session, "AR_1", _healthy_metrics(recovery=None)), CFG)
    assert _leg(v, "recovery").status == NA
    assert v.passed is True


def test_recovery_below_sample_floor_is_waived(db_session) -> None:
    rec = {"rate": 0.1, "numerator": 0, "denominator": CFG.gate.recovery_min_clarify - 1}
    v = evaluate_run(_run(db_session, "AR_1", _healthy_metrics(recovery=rec)), CFG)
    assert _leg(v, "recovery").status == NA and v.passed is True


# --- 레그 4: Persona ---


def test_persona_harm_exceeds_lift_fails(db_session) -> None:
    """§4-2: Harm > Lift인 클러스터가 있으면 통과 불가."""
    personas = {"PC_1": {"lift": 0.01, "harm": 0.10, "net": -0.09, "n": 50,
                         "flips_lift": 1, "flips_harm": 5,
                         "deactivate_recommended": True, "sample_below_floor": False}}
    v = evaluate_run(_run(db_session, "AR_1", _healthy_metrics(persona=personas)), CFG)
    assert _leg(v, "persona_safety").status == FAIL and v.passed is False


def test_persona_below_sample_floor_fails_not_waived(db_session) -> None:
    """★ 활성 prior인데 표본 미달이면 FAIL — 미측정을 안전으로 렌더하지 않는다."""
    personas = {"PC_1": {"lift": 0.0, "harm": 0.0, "net": 0.0, "n": 3,
                         "flips_lift": 0, "flips_harm": 0,
                         "deactivate_recommended": False, "sample_below_floor": True}}
    v = evaluate_run(_run(db_session, "AR_1", _healthy_metrics(persona=personas)), CFG)
    assert _leg(v, "persona_safety").status == FAIL


def test_persona_absent_is_na(db_session) -> None:
    """클러스터가 없으면 측정 대상 없음 — 능력·안전이 좋으면 통과 가능(현재 실 DB 상태)."""
    v = evaluate_run(_run(db_session, "AR_1", _healthy_metrics(persona=None)), CFG)
    assert _leg(v, "persona_safety").status == NA and v.passed is True


def test_vacuous_prior_passes(db_session) -> None:
    """prior가 예측을 못 바꾸는 클러스터(Lift=Harm=0)는 안전하다 — 해악 게이트다."""
    personas = {"PC_1": {"lift": 0.0, "harm": 0.0, "net": 0.0, "n": 50,
                         "flips_lift": 0, "flips_harm": 0,
                         "deactivate_recommended": False, "sample_below_floor": False}}
    v = evaluate_run(_run(db_session, "AR_1", _healthy_metrics(persona=personas)), CFG)
    assert _leg(v, "persona_safety").status == PASS and v.passed is True


# --- 지속성(§10-2 '2주 유지') ---


def test_requires_sustained_consecutive_runs(db_session) -> None:
    _run(db_session, "AR_1", _healthy_metrics())
    r = evaluate_live_readiness(db_session, CFG)
    assert CFG.gate.sustained_runs == 2
    assert r.ready is False and r.runs_evaluated == 1
    assert any("유지 요건" in b for b in r.blockers)

    _run(db_session, "AR_2", _healthy_metrics())
    r = evaluate_live_readiness(db_session, CFG)
    assert r.ready is True and r.runs_evaluated == 2 and r.blockers == []


def test_one_bad_run_in_window_blocks(db_session) -> None:
    _run(db_session, "AR_1", _healthy_metrics())
    _run(db_session, "AR_2", _healthy_metrics(first_intent_accuracy=0.4))
    r = evaluate_live_readiness(db_session, CFG)
    assert r.ready is False and any("AR_2" in b for b in r.blockers)


def test_window_never_mixes_ktib_versions(db_session) -> None:
    """★ §8-2: 신·구 벤치마크 점수를 같은 축에 그리지 않는다."""
    db_session.add(KtibVersion(ktib_version="ktib-2", seq=2, extractor_versions={},
                               episode_count=100, content_hash="h2"))
    db_session.flush()
    _run(db_session, "AR_old1", _healthy_metrics(), ktib="ktib-1")
    _run(db_session, "AR_old2", _healthy_metrics(), ktib="ktib-1")
    _run(db_session, "AR_new", _healthy_metrics(), ktib="ktib-2")

    r = evaluate_live_readiness(db_session, CFG)
    assert r.ktib_version == "ktib-2"
    assert r.runs_evaluated == 1 and r.ready is False  # 새 KTIB에선 아직 1회


def test_baseline_runs_are_not_evaluated(db_session) -> None:
    """zero-shot 베이스라인 run은 준비도 판정 대상이 아니다."""
    _run(db_session, "AR_base", _healthy_metrics(), run_type=RUN_TYPE_BASELINE)
    r = evaluate_live_readiness(db_session, CFG)
    assert r.runs_evaluated == 0 and r.ready is False
    assert "brain arena run이 하나도 없다" in r.blockers


def test_gate_reads_stored_metrics_only(db_session) -> None:
    """★ 게이트는 run 시점에 동결된 metrics만 읽는다 — 오늘의 DB 상태로 재계산하지 않는다.

    (persona 클러스터를 지금 만들어도, 저장된 metrics["persona"]가 null이면 레그는 N/A다.)
    """
    from app.models.persona import PersonaCluster, PersonaStateVersion, PopulationPrior
    db_session.add(PersonaStateVersion(version="ps-1", seq=1, reason="t"))
    db_session.add(PersonaCluster(cluster_id="PC_9", method="t", axes={}, member_count=5,
                                  version="pv-1"))
    db_session.flush()
    db_session.add(PopulationPrior(cluster_id="PC_9", intent_id="play_expand", prior=0.9,
                                   state_version="ps-1"))
    db_session.flush()

    v = evaluate_run(_run(db_session, "AR_1", _healthy_metrics(persona=None)), CFG)
    assert _leg(v, "persona_safety").status == NA  # 저장값이 null이면 null이다
