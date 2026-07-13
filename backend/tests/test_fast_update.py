"""T4.4 AC (§6-5): Fast Update 안전 규칙 — teacher prior 미세 조정.

- 표본(트레이너 gym evidence) < fast_min_samples인 intent는 조정하지 않는다 (no-op)
- |목표 − 현재| > fast_delta_cap인 조정은 거부한다 (상한 초과 거부)
- weekly decay: prior가 중립(0.5)으로 주간 감쇠
- rollback: 이전 state_version의 prior를 복원 (새 스냅샷으로 — 불변성 유지)

전부 config.fast_update — 리터럴 금지 (절대 규칙 1). 스냅샷 불변: 조정은 새 state_version 발급.
Fast는 개인(teacher) prior만 건드린다 — 공유 뇌(node brightness 등)엔 접근하지 않는다(규칙 3).
"""
import pytest
from sqlalchemy import delete

from app.brain.fast_update import (
    NEUTRAL_PRIOR,
    count_teacher_samples,
    fast_update_from_gym,
    fast_update_teacher_prior,
    propose_from_gym,
    rollback_teacher_prior,
    run_fast_update_batch,
    weekly_decay_teacher_prior,
)
from app.brain.priors import (
    current_state_version,
    get_population_priors,
    get_teacher_priors,
    issue_state_version,
    set_population_priors,
    set_teacher_priors,
)
from app.core.config import get_config
from app.core.ontology import load_ontology
from app.models.arena import ArenaRun, KtibItem, KtibVersion
from app.models.episodes import Episode, Evidence
from app.models.persona import (
    PersonaCluster,
    PersonaStateVersion,
    PopulationPrior,
    TeacherPrior,
)

CFG = get_config()
FU = CFG.fast_update


@pytest.fixture(autouse=True)
def _empty(db_session):
    """prior/버전 카운트 전제 — 세이브포인트 안에서 비운다(FK: evidence→episode, pop→cluster).

    population·teacher·version을 모두 비워, 이월(carry-forward) 테스트가 실 DB의 기존 스냅샷에
    오염되지 않게 한다."""
    # 실 KTIB(ktib_items)가 episodes를 FK로 잡는다 — 자식 먼저
    db_session.execute(delete(ArenaRun))
    db_session.execute(delete(KtibItem))
    db_session.execute(delete(KtibVersion))
    db_session.execute(delete(Evidence))
    db_session.execute(delete(Episode))
    db_session.execute(delete(TeacherPrior))
    db_session.execute(delete(PopulationPrior))
    db_session.execute(delete(PersonaCluster))
    db_session.execute(delete(PersonaStateVersion))
    db_session.flush()


def _intent(idx=0):
    return [i.intent_id for i in load_ontology().intents if i.domain][idx]


def _gym_evidence(db, trainer, intent, n):
    """트레이너의 gym evidence n건(에피소드 1개 공유) — 표본 카운트용."""
    ep_id = f"EP_FU_{trainer}_{intent}"
    db.add(Episode(
        episode_id=ep_id, ontology_version="onto-1.0", lang="ko", dataset_split="TRAIN",
        reliability_tier="UNVERIFIED", label_state="EVIDENCE_ACCUMULATING",
        origin_channel="GYM_HUMAN", episode_creator_type="GYM_SESSION",
        primary_subject_type="TEACHER", teacher_prompt="발화", label_distribution={intent: 1.0},
    ))
    for k in range(n):
        db.add(Evidence(
            evidence_id=f"EV_FU_{trainer}_{intent}_{k}", episode_id=ep_id, intent_id=intent,
            polarity="supports", strength=CFG.gym.evidence_strength,
            evidence_type="HUMAN_CONFIRMATION", actor_type="TEACHER_TRAINER",
            trainer_ref=trainer, adversarial=False,
        ))
    db.flush()


def _seed_prior(db, trainer, priors) -> str:
    v = issue_state_version(db, reason="seed")
    set_teacher_priors(db, trainer, priors, v)
    db.flush()
    return v


# --- 표본 카운트 ---


def test_count_teacher_samples_from_gym_evidence(db_session) -> None:
    node = _intent(0)
    _gym_evidence(db_session, "TR_c", node, 7)
    counts = count_teacher_samples(db_session, "TR_c")
    assert counts[node] == 7


def test_adversarial_evidence_not_counted(db_session) -> None:
    """절대 규칙 6: adversarial evidence는 표본에 들어가지 않는다."""
    node = _intent(0)
    _gym_evidence(db_session, "TR_a", node, 3)
    db_session.add(Evidence(
        evidence_id="EV_ADV", episode_id=f"EP_FU_TR_a_{node}", intent_id=node, polarity="supports",
        strength=0.9, evidence_type="HUMAN_CONFIRMATION", actor_type="TEACHER_TRAINER",
        adversarial=True,
    ))
    db_session.flush()
    assert count_teacher_samples(db_session, "TR_a")[node] == 3  # adversarial 제외


# --- AC 1: 표본 미달 → no-op ---


def test_insufficient_samples_is_noop(db_session) -> None:
    node = _intent(0)
    base_v = _seed_prior(db_session, "TR_i", {node: 0.5})
    _gym_evidence(db_session, "TR_i", node, FU.fast_min_samples - 1)  # 임계 미달
    result = fast_update_teacher_prior(
        db_session, "TR_i", {node: 0.5 + FU.fast_delta_cap}, CFG
    )
    assert node in result.skipped_insufficient
    assert result.updated == {}
    assert result.state_version is None                 # 새 버전 미발급 — no-op
    assert current_state_version(db_session) == base_v   # current 그대로
    assert get_teacher_priors(db_session, "TR_i", base_v).priors[node] == 0.5  # 불변


# --- AC 2: 상한 초과 조정 → 거부 ---


def test_over_cap_adjustment_rejected(db_session) -> None:
    node = _intent(0)
    base_v = _seed_prior(db_session, "TR_o", {node: 0.5})
    _gym_evidence(db_session, "TR_o", node, FU.fast_min_samples)  # 표본 충분
    over = 0.5 + FU.fast_delta_cap * 2  # 목표가 cap의 2배만큼 이동 — 초과
    result = fast_update_teacher_prior(db_session, "TR_o", {node: over}, CFG)
    assert node in result.rejected_over_cap
    assert result.updated == {}
    assert result.state_version is None
    assert get_teacher_priors(db_session, "TR_o", base_v).priors[node] == 0.5  # 불변


def test_at_cap_boundary_accepted(db_session) -> None:
    """정확히 cap만큼의 이동은 허용(경계 포함)."""
    node = _intent(0)
    _seed_prior(db_session, "TR_bnd", {node: 0.5})
    _gym_evidence(db_session, "TR_bnd", node, FU.fast_min_samples)
    target = 0.5 + FU.fast_delta_cap
    result = fast_update_teacher_prior(db_session, "TR_bnd", {node: target}, CFG)
    assert result.updated[node] == pytest.approx(target)
    assert node not in result.rejected_over_cap


# --- AC 2 계속: cap 내 조정은 적용 + 새 버전 + replay ---


def test_within_cap_applied_new_version_replayable(db_session) -> None:
    node = _intent(0)
    base_v = _seed_prior(db_session, "TR_w", {node: 0.50})
    _gym_evidence(db_session, "TR_w", node, FU.fast_min_samples)
    target = 0.50 + FU.fast_delta_cap / 2
    result = fast_update_teacher_prior(db_session, "TR_w", {node: target}, CFG)
    db_session.flush()
    assert result.state_version is not None and result.state_version != base_v
    assert current_state_version(db_session) == result.state_version
    # 새 버전엔 조정값, 옛 버전은 그대로(replay 무결성)
    new = get_teacher_priors(db_session, "TR_w", result.state_version).priors
    assert new[node] == pytest.approx(target)
    assert get_teacher_priors(db_session, "TR_w", base_v).priors[node] == 0.50


def test_snapshot_carries_forward_unchanged_priors(db_session) -> None:
    """스냅샷 불변·완결성: 한 intent만 조정해도 새 버전은 나머지 prior를 그대로 이어 담는다."""
    a, b = _intent(0), _intent(1)
    _seed_prior(db_session, "TR_cf", {a: 0.50, b: 0.80})
    _gym_evidence(db_session, "TR_cf", a, FU.fast_min_samples)  # a만 표본 충분
    result = fast_update_teacher_prior(db_session, "TR_cf", {a: 0.50 + FU.fast_delta_cap}, CFG)
    db_session.flush()
    snap = get_teacher_priors(db_session, "TR_cf", result.state_version).priors
    assert snap[a] == pytest.approx(0.50 + FU.fast_delta_cap)  # 조정됨
    assert snap[b] == 0.80  # 미조정 prior도 새 스냅샷에 이어짐


# --- 증거 기반 자동 제안 + 적용 ---


def test_fast_update_from_gym_nudges_confirmed_intent(db_session) -> None:
    """트레이너가 반복 확인한 intent 쪽으로 최대 한 스텝(cap) 보수적으로 민다."""
    node = _intent(0)
    _seed_prior(db_session, "TR_g", {node: 0.50})
    _gym_evidence(db_session, "TR_g", node, FU.fast_min_samples)
    proposals = propose_from_gym(db_session, "TR_g", CFG)
    assert proposals[node] == pytest.approx(0.50 + FU.fast_delta_cap)  # 한 스텝 상향
    result = fast_update_from_gym(db_session, "TR_g", CFG)
    db_session.flush()
    assert result.updated[node] == pytest.approx(0.50 + FU.fast_delta_cap)


def test_from_gym_skips_below_min_samples(db_session) -> None:
    node = _intent(0)
    _seed_prior(db_session, "TR_gs", {node: 0.50})
    _gym_evidence(db_session, "TR_gs", node, FU.fast_min_samples - 1)
    result = fast_update_from_gym(db_session, "TR_gs", CFG)
    assert result.state_version is None and node in result.skipped_insufficient


def test_from_gym_converges_to_share_target_no_runaway(db_session) -> None:
    """수렴·비드리프트: 반복 fast update가 evidence 분포 목표(0.5+0.5·share)로 수렴하고
    각 스텝은 cap 이하, 목표를 넘어 폭주하지 않는다."""
    a, b = _intent(0), _intent(1)
    _gym_evidence(db_session, "TR_cv", a, FU.fast_min_samples)  # share_a = 0.5
    _gym_evidence(db_session, "TR_cv", b, FU.fast_min_samples)  # share_b = 0.5
    target = NEUTRAL_PRIOR + (1.0 - NEUTRAL_PRIOR) * 0.5        # = 0.75
    prev = NEUTRAL_PRIOR
    for _ in range(50):
        result = fast_update_from_gym(db_session, "TR_cv", CFG)
        db_session.flush()
        if result.state_version is None:
            break  # 수렴 — 더 조정할 것 없음
        cur = get_teacher_priors(db_session, "TR_cv").priors[a]
        assert cur - prev <= FU.fast_delta_cap + 1e-9  # 스텝은 cap 이하
        assert cur <= target + 1e-9                    # 목표를 넘지 않는다(폭주 없음)
        prev = cur
    else:
        raise AssertionError("50회 안에 수렴하지 않음")
    assert get_teacher_priors(db_session, "TR_cv").priors[a] == pytest.approx(target, abs=1e-6)


# --- weekly decay ---


def test_weekly_decay_toward_neutral(db_session) -> None:
    node = _intent(0)
    _seed_prior(db_session, "TR_d", {node: 0.70})
    result = weekly_decay_teacher_prior(db_session, "TR_d", CFG)
    db_session.flush()
    expected = 0.5 + (0.70 - 0.5) * FU.weekly_decay
    assert result.updated[node] == pytest.approx(expected)
    assert 0.5 < result.updated[node] < 0.70  # 중립 쪽으로, 넘지 않게


def test_weekly_decay_noop_without_priors(db_session) -> None:
    result = weekly_decay_teacher_prior(db_session, "TR_none", CFG)
    assert result.state_version is None and result.updated == {}


# --- AC 3: rollback → 이전 버전 복원 ---


def test_rollback_restores_prior_version(db_session) -> None:
    node = _intent(0)
    v1 = _seed_prior(db_session, "TR_r", {node: 0.50})
    _gym_evidence(db_session, "TR_r", node, FU.fast_min_samples)
    fast_update_teacher_prior(db_session, "TR_r", {node: 0.50 + FU.fast_delta_cap}, CFG)
    db_session.flush()
    bumped = get_teacher_priors(db_session, "TR_r").priors[node]
    assert bumped == pytest.approx(0.50 + FU.fast_delta_cap)

    restored = rollback_teacher_prior(db_session, "TR_r", to_version=v1, config=CFG)
    db_session.flush()
    # 롤백 후 current prior가 v1 값으로 복원 — 새 버전으로(불변성), v1 자체는 보존
    assert restored != v1
    assert current_state_version(db_session) == restored
    assert get_teacher_priors(db_session, "TR_r").priors[node] == 0.50
    assert get_teacher_priors(db_session, "TR_r", v1).priors[node] == 0.50  # 원본 보존


# --- CRITICAL 회귀: 전역 state_version 스냅샷은 모든 principal을 이월해야 한다 ---


def test_carry_forward_preserves_population_and_other_teachers(db_session) -> None:
    """한 트레이너 fast update가 새 global 버전을 발급해도, current에서 population prior와
    다른 트레이너의 prior가 사라지지 않는다(완결 스냅샷 — 리뷰 CRITICAL)."""
    node = _intent(0)
    db_session.add(PersonaCluster(
        cluster_id="PC_cf", method="HDBSCAN", axes={}, member_count=1, version="pv"
    ))
    db_session.flush()
    v0 = issue_state_version(db_session, reason="seed")
    set_population_priors(db_session, "PC_cf", {node: 0.70}, v0)     # 직전 스냅샷의 population
    set_teacher_priors(db_session, "TR_B", {node: 0.60}, v0)        # 다른 트레이너 B
    db_session.flush()

    _gym_evidence(db_session, "TR_A", node, FU.fast_min_samples)
    result = fast_update_teacher_prior(db_session, "TR_A", {node: 0.50 + FU.fast_delta_cap}, CFG)
    db_session.flush()
    assert result.state_version is not None and result.state_version != v0
    assert current_state_version(db_session) == result.state_version
    # 새 current 버전에도 population + B의 prior가 그대로 이월돼 있다(추론이 neutral로 안 떨어진다)
    assert get_population_priors(db_session, "PC_cf").priors[node] == pytest.approx(0.70)
    assert get_teacher_priors(db_session, "TR_B").priors[node] == pytest.approx(0.60)
    a_prior = get_teacher_priors(db_session, "TR_A").priors[node]
    assert a_prior == pytest.approx(0.50 + FU.fast_delta_cap)


# --- MAJOR 회귀: float32 저장 정밀도에서 수렴 후 버전 churn이 멈춘다 ---


def test_multi_intent_converges_no_version_churn(db_session) -> None:
    """비이분수(non-dyadic) share 목표(1/3)에서도 float32 정밀도로 수렴 — 반복이 no-op(버전
    미발급)으로 끝난다. epsilon이 float32 ULP보다 작으면 여기서 무한 churn한다."""
    a, b, c = _intent(0), _intent(1), _intent(2)
    for intent in (a, b, c):
        _gym_evidence(db_session, "TR_ch", intent, FU.fast_min_samples)  # share 1/3 each
    for _ in range(40):
        if fast_update_from_gym(db_session, "TR_ch", CFG).state_version is None:
            break  # 수렴 — 더 발급하지 않는다
        db_session.flush()
    else:
        raise AssertionError("40회 내 수렴 못 함 — 버전 churn")
    # 수렴 후 한 번 더 호출해도 no-op(새 버전 없음)
    assert fast_update_from_gym(db_session, "TR_ch", CFG).state_version is None


# --- 배치: 여러 트레이너를 한 버전으로 (요청 경로 아님) ---


def test_run_fast_update_batch_single_version(db_session) -> None:
    node = _intent(0)
    _gym_evidence(db_session, "TR_1", node, FU.fast_min_samples)
    _gym_evidence(db_session, "TR_2", node, FU.fast_min_samples)
    report = run_fast_update_batch(db_session, CFG)
    db_session.flush()
    assert report.state_version is not None
    assert set(report.trainers_updated) == {"TR_1", "TR_2"}          # 두 트레이너 모두
    # 한 버전에 둘 다 반영 (per-트레이너 버전 폭증 없음)
    assert get_teacher_priors(db_session, "TR_1").state_version == report.state_version
    assert get_teacher_priors(db_session, "TR_2").state_version == report.state_version
    p1 = get_teacher_priors(db_session, "TR_1").priors[node]
    assert p1 == pytest.approx(0.50 + FU.fast_delta_cap)


def test_run_fast_update_batch_noop_when_all_below_samples(db_session) -> None:
    node = _intent(0)
    _gym_evidence(db_session, "TR_x", node, FU.fast_min_samples - 1)
    report = run_fast_update_batch(db_session, CFG)
    assert report.state_version is None and report.trainers_updated == {}
