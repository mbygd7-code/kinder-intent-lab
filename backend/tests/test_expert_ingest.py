"""§8-2 AC: 전문가 저작 에피소드 유입 — KTIB에 데이터가 들어가는 유일한 경로.

- 합성 채널(FOUNDRY_SYNTHETIC/AUGMENTED)로는 유입 불가 (절대 규칙 2)
- BENCHMARK_HOLDOUT은 검수자 2인 이상 필수 → GOLD ∧ LABELED (§3-3)
- 온톨로지 밖·UNKNOWN intent 거부 (벤치마크의 정답이 '모름'일 수 없다)
- dedup_hash로 재유입 방지 (같은 파일 두 번 넣어도 안 늘어난다)
- 유입된 벤치마크 에피소드는 KTIB를 구성할 수 있고, **학습 exemplar로는 새지 않는다** (§8-2)
"""
import pytest
from sqlalchemy import delete, func, select

from app.arena.ktib import build_ktib
from app.core.config import get_config
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.foundry.expert_ingest import (
    INGEST_EVENT,
    BenchmarkNeedsReview,
    ExpertEpisode,
    SyntheticChannelRejected,
    TrainBenchmarkContamination,
    UnknownIngestIntent,
    ingest_expert_episodes,
)
from app.models.arena import KtibItem, KtibVersion
from app.models.brain import Exemplar
from app.models.episodes import Episode, Evidence
from app.models.foundry import CanonicalScenario
from app.models.governance import GovernanceEvent

CFG = get_config()
REVIEWERS = ("HR_kim", "HR_lee")


@pytest.fixture(autouse=True)
def _empty(db_session):
    for model in (KtibItem, KtibVersion, Exemplar, Evidence, Episode, CanonicalScenario,
                  GovernanceEvent):
        db_session.execute(delete(model))
    db_session.flush()


def _intents(n=3):
    return [i.intent_id for i in load_ontology().intents if i.domain][:n]


def _eps(intents, n=2, reviewers=REVIEWERS):
    return [
        ExpertEpisode(f"EP_KTIB_{i}", f"교사가 실제로 한 발화 {i}", intents[i % len(intents)],
                      reviewers=tuple(reviewers), agreement_kappa=1.0)
        for i in range(n)
    ]


def _ingest(db, eps, *, channel="EXPERT_AUTHORED", split="BENCHMARK_HOLDOUT"):
    return ingest_expert_episodes(
        db, eps, CFG, origin_channel=channel, dataset_split=split,
        authored_by="김OO (유아교사 5년)", approved_by="총괄",
    )


# --- 절대 규칙 2: 합성 채널 차단 ---


@pytest.mark.parametrize("channel", ["FOUNDRY_SYNTHETIC", "FOUNDRY_AUGMENTED"])
def test_synthetic_channel_rejected(db_session, channel) -> None:
    """★ 합성 발화를 전문가 저작으로 위장해 벤치마크에 넣는 경로를 여기서 막는다."""
    with pytest.raises(SyntheticChannelRejected, match="절대 규칙 2"):
        _ingest(db_session, _eps(_intents()), channel=channel)


@pytest.mark.parametrize("channel", ["EXPERT_AUTHORED", "OFFICIAL_CORPUS", "COMMUNITY_DERIVED"])
def test_non_synthetic_channels_allowed(db_session, channel) -> None:
    report = _ingest(db_session, _eps(_intents()), channel=channel)
    assert report.inserted == 2


# --- §3-3: 벤치마크는 GOLD이고 GOLD는 2인 검수다 ---


def test_benchmark_requires_two_reviewers(db_session) -> None:
    with pytest.raises(BenchmarkNeedsReview, match="§3-3"):
        _ingest(db_session, _eps(_intents(), reviewers=("HR_kim",)))


def test_alias_reviewers_cannot_forge_two_person_review(db_session) -> None:
    """★ CRITICAL: ('kim','kim ')는 한 사람이다 — 혼자 벤치마크 정답을 확정할 수 없다."""
    with pytest.raises(BenchmarkNeedsReview, match="별칭"):
        _ingest(db_session, _eps(_intents(), reviewers=("kim", "kim ")))
    with pytest.raises(BenchmarkNeedsReview, match="별칭"):
        _ingest(db_session, _eps(_intents(), reviewers=("Kim", "kim")))


def test_blank_reviewers_rejected(db_session) -> None:
    with pytest.raises(BenchmarkNeedsReview):
        _ingest(db_session, _eps(_intents(), reviewers=("", "   ")))


def test_benchmark_requires_recorded_kappa(db_session) -> None:
    """★ CRITICAL: 측정하지 않은 일치도는 일치가 아니다. kappa=None은 KTIB 정답이 될 수 없다."""
    eps = [ExpertEpisode("EP_K", "사람이 쓴 발화", _intents()[0], reviewers=REVIEWERS,
                         agreement_kappa=None)]
    with pytest.raises(BenchmarkNeedsReview, match="미기록"):
        _ingest(db_session, eps)


def test_benchmark_rejects_low_kappa(db_session) -> None:
    """★ 검수 경로(review.py)보다 느슨하면 사람들은 느슨한 문을 쓴다 — 같은 하한을 요구한다."""
    low = CFG.review.min_agreement_kappa - 0.01
    eps = [ExpertEpisode("EP_K", "사람이 쓴 발화", _intents()[0], reviewers=REVIEWERS,
                         agreement_kappa=low)]
    with pytest.raises(BenchmarkNeedsReview, match="하한"):
        _ingest(db_session, eps)


def test_canonical_reviewers_recorded(db_session) -> None:
    eps = [ExpertEpisode("EP_K", "사람이 쓴 발화", _intents()[0],
                         reviewers=(" HR_Kim ", "hr_lee"), agreement_kappa=1.0)]
    _ingest(db_session, eps)
    db_session.flush()
    assert db_session.get(Episode, "EP_K").human_review["reviewers"] == ["hr_kim", "hr_lee"]


# --- §8-2: 학습/시험 오염 차단 ---


def test_same_utterance_cannot_exist_in_train_and_benchmark(db_session) -> None:
    """★ MAJOR: 같은 발화가 학습 분할에도 있으면 벤치마크는 일반화가 아니라 암기를 잰다."""
    intent = _intents()[0]
    prompt = "교사가 실제로 한 발화 0"
    db_session.add(Episode(
        episode_id="EP_TRAIN", ontology_version="onto-1.0", lang="ko", dataset_split="TRAIN",
        reliability_tier="BRONZE", label_state="LABEL_CANDIDATE",
        origin_channel="FOUNDRY_SYNTHETIC", episode_creator_type="FOUNDRY_PIPELINE",
        primary_subject_type="SIMULATED_TEACHER", teacher_prompt=prompt,
        label_distribution={intent: 1.0},
    ))
    db_session.flush()

    eps = [ExpertEpisode("EP_KTIB_X", prompt, intent, reviewers=REVIEWERS, agreement_kappa=1.0)]
    with pytest.raises(TrainBenchmarkContamination, match="§8-2"):
        _ingest(db_session, eps)


def test_dedup_hash_is_split_independent(db_session) -> None:
    """★ split을 해시에 넣으면 같은 발화가 TRAIN·BENCHMARK에 공존한다 — 넣지 않는다."""
    import inspect

    from app.foundry.expert_ingest import _dedup_hash
    assert "split" not in inspect.signature(_dedup_hash).parameters

    intent = _intents()[0]
    _ingest(db_session, [ExpertEpisode("EP_T", "발화 T", intent)], split="TRAIN")
    db_session.flush()
    # 같은 발화를 다른 split으로 다시 넣어도 dedup이 잡는다(오염 가드가 먼저 잡지 못하는 경로 대비)
    report = _ingest(db_session, [ExpertEpisode("EP_T2", "발화 T", intent)], split="VALIDATION")
    assert report.inserted == 0 and report.skipped_duplicate == 1


def test_benchmark_episodes_land_as_gold_labeled(db_session) -> None:
    _ingest(db_session, _eps(_intents()))
    db_session.flush()
    ep = db_session.get(Episode, "EP_KTIB_0")
    assert ep.dataset_split == "BENCHMARK_HOLDOUT"
    assert ep.reliability_tier == "GOLD" and ep.label_state == "LABELED"
    assert ep.origin_channel == "EXPERT_AUTHORED"
    assert ep.episode_creator_type == "HUMAN_ANNOTATOR"
    assert ep.primary_subject_type == "TEACHER"
    # 정규화된 신원으로 기록 — 별칭 두 개가 '2인 검수'를 주장하지 못한다
    assert ep.human_review == {"reviewers": ["hr_kim", "hr_lee"], "agreement_kappa": 1.0}


def test_train_split_lands_unverified_pending_review(db_session) -> None:
    """벤치마크가 아니면 검수 전 상태로 들어간다 — 유입만으로 GOLD가 되지 않는다."""
    _ingest(db_session, _eps(_intents(), reviewers=()), split="TRAIN")
    db_session.flush()
    ep = db_session.get(Episode, "EP_KTIB_0")
    assert ep.reliability_tier == "UNVERIFIED" and ep.label_state == "UNLABELED"


# --- intent 검증 ---


def test_unknown_intent_rejected(db_session) -> None:
    bad = [ExpertEpisode("EP_X", "발화", "NOT_AN_INTENT", reviewers=REVIEWERS)]
    with pytest.raises(UnknownIngestIntent):
        _ingest(db_session, bad)


def test_unknown_placeholder_intent_rejected(db_session) -> None:
    """★ 벤치마크의 정답이 '모름'일 수 없다."""
    bad = [ExpertEpisode("EP_X", "발화", UNKNOWN_INTENT_ID, reviewers=REVIEWERS)]
    with pytest.raises(UnknownIngestIntent):
        _ingest(db_session, bad)


def test_authored_by_required(db_session) -> None:
    """누가 썼는지 남지 않는 벤치마크는 없다."""
    with pytest.raises(ValueError, match="authored_by"):
        ingest_expert_episodes(
            db_session, _eps(_intents()), CFG, origin_channel="EXPERT_AUTHORED",
            dataset_split="BENCHMARK_HOLDOUT", authored_by="  ", approved_by="총괄",
        )


# --- 멱등 · 거버넌스 ---


def test_reingest_is_idempotent(db_session) -> None:
    """같은 파일을 두 번 넣어도 벤치마크가 늘어나지 않는다."""
    eps = _eps(_intents())
    assert _ingest(db_session, eps).inserted == 2
    db_session.flush()
    second = _ingest(db_session, [
        ExpertEpisode(f"EP_DUP_{i}", e.teacher_prompt, e.intent, reviewers=REVIEWERS,
                      agreement_kappa=1.0)
        for i, e in enumerate(eps)
    ])
    assert second.inserted == 0 and second.skipped_duplicate == 2
    db_session.flush()
    assert db_session.scalar(select(func.count()).select_from(Episode)) == 2


def test_ingest_records_governance_event(db_session) -> None:
    _ingest(db_session, _eps(_intents()))
    db_session.flush()
    event = db_session.scalar(
        select(GovernanceEvent).where(GovernanceEvent.event_type == INGEST_EVENT)
    )
    assert event is not None
    assert event.payload["authored_by"] == "김OO (유아교사 5년)"
    assert event.payload["origin_channel"] == "EXPERT_AUTHORED"
    assert event.payload["inserted"] == 2


# --- §8-2: 유입 → KTIB 구성 → 학습 격리 유지 ---


def test_ingested_episodes_build_a_ktib(db_session) -> None:
    """★ 이것이 KTIB를 처음 존재하게 만드는 유일한 경로다."""
    _ingest(db_session, _eps(_intents(), n=3))
    db_session.flush()
    ktib = build_ktib(db_session, CFG)
    assert ktib.episode_count == 3 and ktib.ktib_version == "ktib-1"


def test_ingested_benchmark_never_becomes_exemplar(db_session) -> None:
    """★ 유입된 벤치마크 GOLD가 학습 exemplar로 새면 Arena 점수는 암기의 측정치가 된다."""
    from app.brain.backfill import bootstrap_nodes, select_exemplars
    from tests.brain_helpers import _embed

    bootstrap_nodes(db_session, approved_by="lab")
    _ingest(db_session, _eps(_intents(), n=3))
    db_session.flush()

    assert select_exemplars(db_session, CFG, _embed()) == 0
    assert db_session.scalars(select(Exemplar)).first() is None
