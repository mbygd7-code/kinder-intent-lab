"""§3-3 AC: 인간 검수 → GOLD. **GOLD를 만드는 유일한 경로**이므로 가드를 전부 고정한다.

- 서로 다른 검수자 2인 이상 ∧ 만장일치여야 확정. 1인·불일치는 상태 불변(강제 확정 없음)
- 배치 kappa < 하한 → 배치 전량 거부. kappa 계산 불가(변별력 없음)도 거부
- 합성 에피소드도 GOLD가 될 수 있으나 BENCHMARK_HOLDOUT에는 못 간다 (절대 규칙 2)
- 전이는 advance_label_state·promote_tier만 경유 (§3-6·§3-3)
"""
import pytest
from sqlalchemy import delete, func, select

from app.aggregator.review import (
    REVIEW_EVENT,
    ReviewBatchRejected,
    ReviewVote,
    UnknownReviewIntent,
    apply_review_batch,
    batch_kappa,
    cohens_kappa,
)
from app.core.config import get_config
from app.core.ontology import load_ontology
from app.models.brain import Exemplar
from app.models.episodes import Episode, Evidence
from app.models.governance import GovernanceEvent

CFG = get_config()


@pytest.fixture(autouse=True)
def _empty(db_session):
    for model in (Exemplar, Evidence, Episode, GovernanceEvent):
        db_session.execute(delete(model))
    db_session.flush()


def _intents(n=4):
    return [i.intent_id for i in load_ontology().intents if i.domain][:n]


def _candidate(db, epid, intent, *, origin="FOUNDRY_SYNTHETIC", split="TRAIN"):
    """Aggregator가 SILVER까지 올려둔 검수 대기 에피소드."""
    db.add(Episode(
        episode_id=epid, ontology_version="onto-1.0", lang="ko", dataset_split=split,
        reliability_tier="SILVER", label_state="LABEL_CANDIDATE", origin_channel=origin,
        episode_creator_type="FOUNDRY_PIPELINE", primary_subject_type="SIMULATED_TEACHER",
        teacher_prompt=f"발화 {epid}", label_distribution={intent: 1.0},
    ))
    db.flush()


def _agreeing_batch(db, intents, n=4):
    """검수자 2명이 n건에 만장일치. 라벨이 다양해야 kappa가 계산된다."""
    votes = []
    for i in range(n):
        intent = intents[i % len(intents)]
        _candidate(db, f"EP_{i}", intent)
        votes += [ReviewVote(f"EP_{i}", "HR_kim", intent), ReviewVote(f"EP_{i}", "HR_lee", intent)]
    return votes


# --- Cohen's kappa ---


def test_kappa_one_on_perfect_agreement_with_varied_labels() -> None:
    assert cohens_kappa(["a", "b", "a", "c"], ["a", "b", "a", "c"]) == 1.0


def test_kappa_none_when_no_discrimination() -> None:
    """★ 둘 다 늘 같은 하나의 라벨만 골랐다면 kappa는 정의되지 않는다 (1.0 반올림 금지)."""
    assert cohens_kappa(["a", "a", "a"], ["a", "a", "a"]) is None


def test_kappa_low_on_disagreement() -> None:
    k = cohens_kappa(["a", "b", "a", "b"], ["b", "a", "b", "a"])
    assert k is not None and k < 0


def test_batch_kappa_takes_the_worst_pair() -> None:
    """검수자 3명이면 가장 나쁜 쌍을 취한다(보수적)."""
    votes = [
        ReviewVote("E1", "R1", "a"), ReviewVote("E1", "R2", "a"), ReviewVote("E1", "R3", "b"),
        ReviewVote("E2", "R1", "b"), ReviewVote("E2", "R2", "b"), ReviewVote("E2", "R3", "a"),
    ]
    assert batch_kappa(votes) == cohens_kappa(["a", "b"], ["b", "a"])


# --- 확정 경로 ---


def test_two_reviewers_agreeing_creates_gold(db_session) -> None:
    """★ §3-3: 2인 일치 → LABELED + GOLD + human_review(reviewers, kappa) 기록."""
    intents = _intents()
    votes = _agreeing_batch(db_session, intents)
    report = apply_review_batch(db_session, votes, CFG, approved_by="총괄")
    db_session.flush()

    assert report.kappa == 1.0 and report.labeled == 4 and report.unchanged == 0
    for i in range(4):
        ep = db_session.get(Episode, f"EP_{i}")
        assert ep.label_state == "LABELED" and ep.reliability_tier == "GOLD"
        # 기록은 정규화된 신원으로 — 별칭 두 개가 '2인'을 주장하지 못하게
        assert ep.human_review == {"reviewers": ["hr_kim", "hr_lee"], "agreement_kappa": 1.0}
        assert ep.label_distribution == {intents[i % len(intents)]: 1.0}


def test_gold_creation_records_governance_event(db_session) -> None:
    apply_review_batch(db_session, _agreeing_batch(db_session, _intents()), CFG,
                       approved_by="김총괄")
    db_session.flush()
    event = db_session.scalar(
        select(GovernanceEvent).where(GovernanceEvent.event_type == REVIEW_EVENT)
    )
    assert event is not None and event.approved_by == "김총괄"
    assert event.payload["labeled"] == 4 and event.payload["agreement_kappa"] == 1.0


def test_unanimous_reject_marks_rejected(db_session) -> None:
    intents = _intents()
    votes = _agreeing_batch(db_session, intents)
    _candidate(db_session, "EP_BAD", intents[0])
    votes += [ReviewVote("EP_BAD", "HR_kim", None), ReviewVote("EP_BAD", "HR_lee", None)]

    report = apply_review_batch(db_session, votes, CFG, approved_by="총괄")
    db_session.flush()
    assert report.rejected == 1
    assert db_session.get(Episode, "EP_BAD").label_state == "REJECTED"
    assert db_session.get(Episode, "EP_BAD").reliability_tier == "SILVER"  # tier 불변


# --- 강제 확정 없음 ---


def test_single_reviewer_never_confirms(db_session) -> None:
    """★ 1인 검수는 절대 GOLD를 만들지 못한다. 배치에 섞여 있어도 그 에피소드만 불변."""
    intents = _intents()
    votes = _agreeing_batch(db_session, intents)
    _candidate(db_session, "EP_SOLO", intents[0])
    votes.append(ReviewVote("EP_SOLO", "HR_kim", intents[0]))  # 1인만

    report = apply_review_batch(db_session, votes, CFG, approved_by="총괄")
    db_session.flush()
    solo = next(o for o in report.episodes if o.episode_id == "EP_SOLO")
    assert solo.outcome == "UNCHANGED" and "1명" in solo.reason
    ep = db_session.get(Episode, "EP_SOLO")
    assert ep.label_state == "LABEL_CANDIDATE" and ep.reliability_tier == "SILVER"


def test_reviewer_disagreement_leaves_episode_untouched(db_session) -> None:
    """★ 불일치는 다수결로 밀어붙이지 않는다 — 상태 불변."""
    intents = _intents()
    votes = _agreeing_batch(db_session, intents)
    _candidate(db_session, "EP_SPLIT", intents[0])
    votes += [ReviewVote("EP_SPLIT", "HR_kim", intents[0]),
              ReviewVote("EP_SPLIT", "HR_lee", intents[1])]

    report = apply_review_batch(db_session, votes, CFG, approved_by="총괄")
    db_session.flush()
    split = next(o for o in report.episodes if o.episode_id == "EP_SPLIT")
    assert split.outcome == "UNCHANGED" and "불일치" in split.reason
    assert db_session.get(Episode, "EP_SPLIT").reliability_tier == "SILVER"


# --- 배치 게이트 ---


def test_low_kappa_rejects_entire_batch(db_session) -> None:
    """★ 검수자들이 서로 일치하지 않으면 우연히 겹친 몇 건도 확정하지 않는다."""
    a, b = _intents(2)
    votes = []
    for i in range(4):
        _candidate(db_session, f"EP_{i}", a)
        # 두 검수자가 정반대로 라벨링 → kappa < 0
        votes += [ReviewVote(f"EP_{i}", "HR_kim", a if i % 2 else b),
                  ReviewVote(f"EP_{i}", "HR_lee", b if i % 2 else a)]

    with pytest.raises(ReviewBatchRejected, match="kappa"):
        apply_review_batch(db_session, votes, CFG, approved_by="총괄")
    assert db_session.get(Episode, "EP_0").reliability_tier == "SILVER"  # 무변화


def test_undiscriminating_batch_rejected(db_session) -> None:
    """★ 모든 라벨이 같아 kappa를 계산할 수 없는 배치는 거부 — 검증한 바가 없다."""
    a = _intents(1)[0]
    votes = []
    for i in range(3):
        _candidate(db_session, f"EP_{i}", a)
        votes += [ReviewVote(f"EP_{i}", "HR_kim", a), ReviewVote(f"EP_{i}", "HR_lee", a)]

    with pytest.raises(ReviewBatchRejected, match="계산 불가"):
        apply_review_batch(db_session, votes, CFG, approved_by="총괄")


def test_single_reviewer_batch_rejected(db_session) -> None:
    intents = _intents()
    _candidate(db_session, "EP_0", intents[0])
    with pytest.raises(ReviewBatchRejected, match="검수자"):
        apply_review_batch(db_session, [ReviewVote("EP_0", "HR_kim", intents[0])], CFG,
                           approved_by="총괄")


def test_unknown_intent_rejected(db_session) -> None:
    """검수자가 온톨로지 밖 라벨을 써도 통과하지 않는다."""
    _candidate(db_session, "EP_0", _intents()[0])
    votes = [ReviewVote("EP_0", "HR_kim", "NOT_AN_INTENT"),
             ReviewVote("EP_0", "HR_lee", "NOT_AN_INTENT")]
    with pytest.raises(UnknownReviewIntent):
        apply_review_batch(db_session, votes, CFG, approved_by="총괄")


def test_empty_batch_rejected(db_session) -> None:
    with pytest.raises(ReviewBatchRejected):
        apply_review_batch(db_session, [], CFG, approved_by="총괄")


# --- 절대 규칙 2: 합성 GOLD는 벤치마크에 못 간다 ---


def test_synthetic_can_become_gold_but_never_benchmark(db_session) -> None:
    """★ 합성 에피소드의 GOLD는 exemplar·new_gold에 쓰인다. 그러나 KTIB에는 영원히 못 들어간다."""
    intents = _intents()
    apply_review_batch(db_session, _agreeing_batch(db_session, intents), CFG, approved_by="총괄")
    db_session.flush()

    ep = db_session.get(Episode, "EP_0")
    assert ep.reliability_tier == "GOLD" and ep.origin_channel == "FOUNDRY_SYNTHETIC"

    # 이제 이 GOLD를 벤치마크로 옮기려 하면 DB CHECK가 막는다 (절대 규칙 2)
    from sqlalchemy.exc import IntegrityError
    ep.dataset_split = "BENCHMARK_HOLDOUT"
    with pytest.raises(IntegrityError, match="benchmark_integrity"):
        db_session.flush()
    db_session.rollback()


# --- 적대적 리뷰가 잡은 결함들의 회귀 테스트 ---


def test_one_human_cannot_forge_gold_with_alias_variants(db_session) -> None:
    """★ CRITICAL: 'alice'와 'alice ', 'Alice'는 한 사람이다. 문자열 부등호 ≠ 사람의 구별."""
    a, b = _intents(2)
    _candidate(db_session, "EP_0", a)
    _candidate(db_session, "EP_1", b)
    votes = [
        ReviewVote("EP_0", "alice", a), ReviewVote("EP_0", "alice ", a),   # 공백 별칭
        ReviewVote("EP_1", "alice", b), ReviewVote("EP_1", "Alice", b),    # 대소문자 별칭
    ]
    with pytest.raises(ReviewBatchRejected, match="검수자 1명"):
        apply_review_batch(db_session, votes, CFG, approved_by="총괄")
    assert db_session.get(Episode, "EP_0").reliability_tier == "SILVER"


def test_blank_reviewer_ref_rejected(db_session) -> None:
    """공백뿐인 ref 두 개로 2인 검수를 위장할 수 없다."""
    a = _intents(1)[0]
    _candidate(db_session, "EP_0", a)
    votes = [ReviewVote("EP_0", "", a), ReviewVote("EP_0", "   ", a)]
    with pytest.raises(ReviewBatchRejected, match="빈 검수자"):
        apply_review_batch(db_session, votes, CFG, approved_by="총괄")


def test_canonical_identity_recorded_not_alias(db_session) -> None:
    """human_review에는 정규화된 신원이 남는다 — 별칭으로 2인을 주장하지 못한다."""
    intents = _intents()
    votes = []
    for i in range(4):
        intent = intents[i % len(intents)]
        _candidate(db_session, f"EP_{i}", intent)
        votes += [ReviewVote(f"EP_{i}", " HR_Kim ", intent),
                  ReviewVote(f"EP_{i}", "hr_lee", intent)]
    apply_review_batch(db_session, votes, CFG, approved_by="총괄")
    db_session.flush()
    assert db_session.get(Episode, "EP_0").human_review["reviewers"] == ["hr_kim", "hr_lee"]


def test_phantom_votes_cannot_forge_label_diversity(db_session) -> None:
    """★ CRITICAL: DB에 없는 에피소드 표로 라벨 다양성을 지어내 pe≥1 가드를 우회할 수 없다.

    실 에피소드는 전부 같은 라벨(변별력 0)인데, 가짜 에피소드 표가 kappa를 계산 가능하게 만든다.
    """
    a, b = _intents(2)
    for i in range(3):
        _candidate(db_session, f"EP_{i}", a)
    votes = [v for i in range(3) for v in
             (ReviewVote(f"EP_{i}", "HR_kim", a), ReviewVote(f"EP_{i}", "HR_lee", a))]
    # 유령 표: 라벨 b를 섞어 pe < 1로 만든다
    votes += [ReviewVote("EP_GHOST", "HR_kim", b), ReviewVote("EP_GHOST", "HR_lee", b)]

    with pytest.raises(ReviewBatchRejected, match="DB에 없는 에피소드"):
        apply_review_batch(db_session, votes, CFG, approved_by="총괄")
    assert db_session.get(Episode, "EP_0").reliability_tier == "SILVER"


def test_kappa_compared_before_rounding(db_session) -> None:
    """★ 0.64995를 0.65로 반올림해 통과시키지 않는다 — 임계 비교는 원값으로."""
    from app.aggregator.review import cohens_kappa
    # 반올림하지 않은 원값을 반환한다
    k = cohens_kappa(["a", "b", "a", "b", "a", "b", "a"], ["a", "b", "a", "b", "a", "b", "b"])
    assert k is not None and k != round(k, 4)  # 4자리로 딱 떨어지지 않는 값


def test_reapplying_a_committed_batch_is_harmless(db_session) -> None:
    """★ 같은 배치를 두 번 적용해도 IllegalTransition으로 죽지 않고 UNCHANGED가 된다."""
    intents = _intents()
    votes = _agreeing_batch(db_session, intents)
    first = apply_review_batch(db_session, votes, CFG, approved_by="총괄")
    db_session.flush()
    assert first.labeled == 4

    second = apply_review_batch(db_session, votes, CFG, approved_by="총괄")  # 재적용
    db_session.flush()
    assert second.labeled == 0 and second.unchanged == 4
    assert all("검수 대상 상태가 아님" in o.reason for o in second.episodes)
    assert db_session.get(Episode, "EP_0").reliability_tier == "GOLD"  # 그대로


def test_non_reviewable_state_left_untouched(db_session) -> None:
    """검수 대상 상태(LABEL_CANDIDATE/REVIEW_REQUIRED)가 아니면 건드리지 않는다."""
    intents = _intents()
    votes = _agreeing_batch(db_session, intents)
    db_session.add(Episode(
        episode_id="EP_RAW", ontology_version="onto-1.0", lang="ko", dataset_split="TRAIN",
        reliability_tier="UNVERIFIED", label_state="UNLABELED",
        origin_channel="FOUNDRY_SYNTHETIC", episode_creator_type="FOUNDRY_PIPELINE",
        primary_subject_type="SIMULATED_TEACHER", teacher_prompt="미집계",
        label_distribution={intents[0]: 1.0},
    ))
    db_session.flush()
    votes += [ReviewVote("EP_RAW", "HR_kim", intents[0]),
              ReviewVote("EP_RAW", "HR_lee", intents[0])]

    report = apply_review_batch(db_session, votes, CFG, approved_by="총괄")
    db_session.flush()
    raw = next(o for o in report.episodes if o.episode_id == "EP_RAW")
    assert raw.outcome == "UNCHANGED"
    assert db_session.get(Episode, "EP_RAW").label_state == "UNLABELED"


def test_reject_sentinel_cannot_collide_with_an_intent() -> None:
    """폐기 자리표시자가 실 intent_id와 충돌하면 폐기표가 라벨로 둔갑한다."""
    from app.aggregator.review import REJECT
    real = {i.intent_id for i in load_ontology().intents}
    assert REJECT not in real and not REJECT.isidentifier()


def test_gold_from_review_becomes_exemplar_material(db_session) -> None:
    """검수로 만든 GOLD는 training_gold()에 잡혀 exemplar 재료가 된다 (§5-7)."""
    from app.core.datasets import is_training_gold

    apply_review_batch(db_session, _agreeing_batch(db_session, _intents()), CFG,
                       approved_by="총괄")
    db_session.flush()
    assert is_training_gold(db_session.get(Episode, "EP_0")) is True
    assert db_session.scalar(select(func.count()).select_from(Episode).where(
        Episode.reliability_tier == "GOLD", Episode.label_state == "LABELED"
    )) == 4
