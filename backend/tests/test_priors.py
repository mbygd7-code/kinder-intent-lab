"""T2.4 AC (§5-3·§5-5, replay 규칙).

- prior 조회가 항상 state_version과 함께 반환
- cap(config.brain.persona_prior_cap) 적용
- 변경 시 새 state_version 발급, 특정 버전 replay 가능
"""
import pytest

from app.brain.priors import (
    apply_persona_prior,
    capped_prior_factor,
    current_state_version,
    get_population_priors,
    get_teacher_priors,
    issue_state_version,
    set_population_priors,
    set_teacher_priors,
)
from app.core.config import get_config
from app.models.persona import PersonaCluster

CFG = get_config()
CAP = CFG.brain.persona_prior_cap


def _cluster(db_session, cluster_id: str) -> None:
    """population_priors.cluster_id FK를 만족시키는 persona_cluster 시드."""
    db_session.add(
        PersonaCluster(cluster_id=cluster_id, method="HDBSCAN", axes={}, member_count=1,
                       version="pv-seed")
    )
    db_session.flush()


# --- state_version 발급 ---


def test_issue_state_version_monotonic(db_session) -> None:
    v1 = issue_state_version(db_session, reason="discovery")
    v2 = issue_state_version(db_session, reason="update", parent=v1)
    assert v1 != v2
    assert current_state_version(db_session) == v2


def test_current_version_none_when_empty(db_session) -> None:
    # 이 테스트의 savepoint 안에서는 아직 발급된 버전이 없다
    assert current_state_version(db_session) is None


# --- population prior CRUD + state_version 동반 반환 (AC) ---


def test_set_get_population_priors_returns_state_version(db_session) -> None:
    _cluster(db_session, "PC_x")
    v = issue_state_version(db_session, reason="d")
    set_population_priors(db_session, "PC_x", {"play_expand": 0.7, "text_naturalize": 0.3}, v)
    db_session.flush()
    result = get_population_priors(db_session, "PC_x", v)
    assert result.state_version == v
    assert result.priors == {"play_expand": 0.7, "text_naturalize": 0.3}


def test_get_uses_current_version_when_none(db_session) -> None:
    _cluster(db_session, "PC_y")
    v = issue_state_version(db_session, reason="d")
    set_population_priors(db_session, "PC_y", {"play_expand": 1.0}, v)
    db_session.flush()
    result = get_population_priors(db_session, "PC_y")  # state_version 미지정 → current
    assert result.state_version == v
    assert result.priors == {"play_expand": 1.0}


def test_replay_specific_version(db_session) -> None:
    """변경 시 새 버전 — 옛 버전을 지정하면 그 시점 prior를 그대로 replay."""
    _cluster(db_session, "PC_z")
    v1 = issue_state_version(db_session, reason="v1")
    set_population_priors(db_session, "PC_z", {"play_expand": 0.9, "text_naturalize": 0.1}, v1)
    db_session.flush()
    v2 = issue_state_version(db_session, reason="v2", parent=v1)
    set_population_priors(db_session, "PC_z", {"play_expand": 0.4, "text_naturalize": 0.6}, v2)
    db_session.flush()

    assert get_population_priors(db_session, "PC_z", v1).priors["play_expand"] == 0.9
    assert get_population_priors(db_session, "PC_z", v2).priors["play_expand"] == 0.4
    assert get_population_priors(db_session, "PC_z").state_version == v2  # current=v2


def test_teacher_priors_set_get(db_session) -> None:
    v = issue_state_version(db_session, reason="d")
    set_teacher_priors(db_session, "TR_1", {"play_expand": 0.6, "obs_record_moment": 0.4}, v)
    db_session.flush()
    result = get_teacher_priors(db_session, "TR_1", v)
    assert result.state_version == v
    assert result.priors["play_expand"] == 0.6


def test_get_missing_priors_still_returns_version(db_session) -> None:
    v = issue_state_version(db_session, reason="d")
    result = get_population_priors(db_session, "PC_absent", v)
    assert result.state_version == v
    assert result.priors == {}


# --- cap 적용 (AC) ---


def test_cap_factor_bounds() -> None:
    assert capped_prior_factor(1.0, CAP) == pytest.approx(1.0 + CAP)   # 최대 부양
    assert capped_prior_factor(0.0, CAP) == pytest.approx(1.0 - CAP)   # 최대 감쇠
    assert capped_prior_factor(0.5, CAP) == pytest.approx(1.0)          # 중립


def test_cap_never_exceeds_bound() -> None:
    for prior in [-5.0, -0.3, 0.0, 0.25, 0.5, 0.75, 1.0, 3.0]:
        factor = capped_prior_factor(prior, CAP)
        assert abs(factor - 1.0) <= CAP + 1e-9  # 어떤 prior도 ±cap 초과 못 함


def test_apply_persona_prior_bounded() -> None:
    base = 0.5
    boosted = apply_persona_prior(base, prior=1.0, cap=CAP)
    dampened = apply_persona_prior(base, prior=0.0, cap=CAP)
    assert boosted == pytest.approx(base * (1.0 + CAP))
    assert dampened == pytest.approx(base * (1.0 - CAP))
    # 점수 변화율이 cap을 넘지 않는다
    assert abs(boosted - base) <= base * CAP + 1e-9


def test_zero_cap_disables_prior() -> None:
    assert apply_persona_prior(0.7, prior=1.0, cap=0.0) == pytest.approx(0.7)


# --- 리뷰 회귀 ---


def test_prior_range_validated(db_session) -> None:
    _cluster(db_session, "PC_range")
    v = issue_state_version(db_session, reason="d")
    for bad in ({"i": 1.5}, {"i": -0.1}):
        with pytest.raises(ValueError, match="밖"):
            set_population_priors(db_session, "PC_range", bad, v)
    with pytest.raises(ValueError, match="밖"):
        set_teacher_priors(db_session, "TR_range", {"i": 2.0}, v)
