"""T5.1 AC (§8-2, 절대 규칙 2): KTIB 구성기.

- 자격: BENCHMARK_HOLDOUT ∧ GOLD ∧ LABELED ∧ 비합성만 선별
- 합성 에피소드의 벤치마크 유입 시도가 DB constraint로 차단됨을 **통합 경로에서** 재확인
- extractor 재추출 시 새 ktib_version 강제 (기존 버전 동결 — 덮어쓰기 차단)
- 빈 벤치마크는 0%가 아니라 EmptyKtib
"""
import pytest
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError

from app.arena.ktib import (
    AmbiguousGoldLabel,
    EmptyKtib,
    build_ktib,
    eligible_episodes,
    extractor_versions,
    freeze_items,
    load_items,
)
from app.core.config import get_config
from app.models.arena import KtibItem, KtibVersion
from app.models.brain import Exemplar
from app.models.episodes import Episode, Evidence
from app.models.foundry import CanonicalScenario
from app.models.guards import KtibFrozen

CFG = get_config()


@pytest.fixture(autouse=True)
def _empty(db_session):
    """빈 슬레이트 — 실 DB 뱅크(TRAIN 합성)가 자격 판정을 흐리지 않게 세이브포인트 안에서 비운다."""
    for model in (KtibItem, KtibVersion, Exemplar, Evidence, Episode, CanonicalScenario):
        db_session.execute(delete(model))
    db_session.flush()


def _workspace(extractor: str = "SYNTH_BUILDER_v1") -> dict:
    return {
        "surface_type": "play_board",
        "objects_summary": {"photo": 2},
        "selection": {"type": "photo", "count": 1},
        "recent_actions": ["move_object"],
        "visual_semantics": [{
            "object_ref": "photo_0",
            "schema_version": "vs-1.0",
            "extractor_version": extractor,
            "scene_type": ["INDOOR_CLASSROOM"],
            "identity_removed": True,
        }],
    }


def _scenario(db, scenario_id: str, extractor: str = "SYNTH_BUILDER_v1") -> CanonicalScenario:
    row = CanonicalScenario(
        scenario_id=scenario_id, frame_id=None, workspace_state=_workspace(extractor),
        variation_of=None, variation_axis=None,
    )
    db.add(row)
    db.flush()
    return row


def _bench(db, epid, intent, *, prompt="이거 자연스럽게 해줘", scenario_id=None,
           origin="EXPERT_AUTHORED", dist=None) -> Episode:
    """KTIB 자격을 갖춘 벤치마크 에피소드 (GOLD ∧ LABELED ∧ 비합성)."""
    ep = Episode(
        episode_id=epid, ontology_version="onto-1.0", lang="ko",
        dataset_split="BENCHMARK_HOLDOUT", reliability_tier="GOLD", label_state="LABELED",
        origin_channel=origin, episode_creator_type="HUMAN_ANNOTATOR",
        primary_subject_type="TEACHER", scenario_id=scenario_id, teacher_prompt=prompt,
        label_distribution=dist or {intent: 1.0},
    )
    db.add(ep)
    db.flush()
    return ep


def _train(db, epid, intent) -> None:
    """학습 분할의 GOLD — 자격 없음(dataset_split ≠ BENCHMARK_HOLDOUT)."""
    db.add(Episode(
        episode_id=epid, ontology_version="onto-1.0", lang="ko", dataset_split="TRAIN",
        reliability_tier="GOLD", label_state="LABELED", origin_channel="EXPERT_AUTHORED",
        episode_creator_type="HUMAN_ANNOTATOR", primary_subject_type="TEACHER",
        teacher_prompt="학습용", label_distribution={intent: 1.0},
    ))
    db.flush()


# --- AC 1: 합성 에피소드의 벤치마크 유입 차단 (DB constraint 재확인, 통합 경로) ---


@pytest.mark.parametrize("channel", ["FOUNDRY_SYNTHETIC", "FOUNDRY_AUGMENTED"])
def test_synthetic_cannot_enter_benchmark(db_session, channel) -> None:
    """GOLD·LABELED여도 합성 채널은 BENCHMARK_HOLDOUT에 못 들어간다 — DB CHECK가 막는다."""
    db_session.add(Episode(
        episode_id=f"EP_SYN_{channel}", ontology_version="onto-1.0", lang="ko",
        dataset_split="BENCHMARK_HOLDOUT", reliability_tier="GOLD", label_state="LABELED",
        origin_channel=channel, episode_creator_type="FOUNDRY_PIPELINE",
        primary_subject_type="SIMULATED_TEACHER", teacher_prompt="합성",
        label_distribution={"visual_naturalize": 1.0},
    ))
    with pytest.raises(IntegrityError, match="benchmark_integrity"):
        db_session.flush()
    db_session.rollback()


def test_build_ktib_never_sees_synthetic(db_session) -> None:
    """차단된 합성분은 애초에 자격 조회에도 잡히지 않는다 — 우회 경로 없음."""
    _bench(db_session, "EP_OK", "visual_naturalize")
    _train(db_session, "EP_TRAIN_GOLD", "visual_naturalize")  # 학습 GOLD — 벤치마크 아님
    ktib = build_ktib(db_session, CFG)
    assert ktib.episode_count == 1
    assert [i.episode_id for i in load_items(db_session, ktib.ktib_version)] == ["EP_OK"]


def test_eligible_excludes_non_gold_and_unlabeled(db_session) -> None:
    """자격 4조건 중 하나라도 빠지면 제외 — 여기서는 TRAIN 분할·비GOLD를 넣어 확인."""
    _bench(db_session, "EP_A", "visual_naturalize")
    _train(db_session, "EP_B", "visual_naturalize")
    db_session.add(Episode(
        episode_id="EP_C", ontology_version="onto-1.0", lang="ko", dataset_split="TEST",
        reliability_tier="SILVER", label_state="LABEL_CANDIDATE",
        origin_channel="EXPERT_AUTHORED", episode_creator_type="HUMAN_ANNOTATOR",
        primary_subject_type="TEACHER", teacher_prompt="후보",
        label_distribution={"visual_naturalize": 1.0},
    ))
    db_session.flush()
    assert [e.episode_id for e in eligible_episodes(db_session)] == ["EP_A"]


# --- AC 2: 동결(freeze) ---


def test_freeze_snapshots_workspace_at_adoption(db_session) -> None:
    """채택 시점의 workspace(visual_semantics 포함)를 복사한다 — 이후 시나리오 변경과 무관."""
    scenario = _scenario(db_session, "CS_1")
    _bench(db_session, "EP_A", "visual_naturalize", scenario_id="CS_1")
    ktib = build_ktib(db_session, CFG)
    item = load_items(db_session, ktib.ktib_version)[0]
    assert item.workspace_snapshot["visual_semantics"][0]["extractor_version"] == "SYNTH_BUILDER_v1"

    scenario.workspace_state = _workspace("SYNTH_BUILDER_v9")  # 원본 시나리오가 바뀌어도
    db_session.flush()
    db_session.refresh(item)
    assert item.workspace_snapshot["visual_semantics"][0]["extractor_version"] == "SYNTH_BUILDER_v1"


def test_snapshot_is_null_without_scenario(db_session) -> None:
    """시나리오가 없는 에피소드는 workspace를 지어내지 않고 NULL로 둔다."""
    _bench(db_session, "EP_A", "visual_naturalize")
    ktib = build_ktib(db_session, CFG)
    assert load_items(db_session, ktib.ktib_version)[0].workspace_snapshot is None


def test_extractor_versions_read_from_frozen_data(db_session) -> None:
    """replay 축은 config가 아니라 스냅샷에 박힌 extractor_version 집합이다."""
    _scenario(db_session, "CS_1", "EXT_v1")
    _scenario(db_session, "CS_2", "EXT_v2")
    _bench(db_session, "EP_A", "visual_naturalize", scenario_id="CS_1")
    _bench(db_session, "EP_B", "text_naturalize", scenario_id="CS_2")
    ev = extractor_versions(freeze_items(db_session), CFG)
    assert ev["visual_semantics_extractors"] == ["EXT_v1", "EXT_v2"]
    assert ev["visual_semantics_vocabulary"] == CFG.visual_semantics.vocabulary_version


# --- AC 3: 멱등 · extractor 재추출 시 새 ktib_version 강제 ---


def test_build_is_idempotent(db_session) -> None:
    """같은 에피소드 집합 ⊕ 같은 extractor → 같은 ktib_version (새 행 없음)."""
    _bench(db_session, "EP_A", "visual_naturalize")
    first = build_ktib(db_session, CFG)
    second = build_ktib(db_session, CFG)
    assert first.ktib_version == second.ktib_version
    assert db_session.scalars(select(KtibVersion)).all() == [first]


def test_reextraction_forces_new_ktib_version(db_session) -> None:
    """★ §8-2: extractor를 올려 재추출하면 새 ktib_version이 강제되고, 구 버전은 그대로 남는다."""
    scenario = _scenario(db_session, "CS_1", "EXT_v1")
    _bench(db_session, "EP_A", "visual_naturalize", scenario_id="CS_1")
    old = build_ktib(db_session, CFG)
    assert old.extractor_versions["visual_semantics_extractors"] == ["EXT_v1"]

    scenario.workspace_state = _workspace("EXT_v2")  # 재추출
    db_session.flush()
    new = build_ktib(db_session, CFG)

    assert new.ktib_version != old.ktib_version
    assert new.seq == old.seq + 1
    assert new.extractor_versions["visual_semantics_extractors"] == ["EXT_v2"]
    # 구 버전 동결 — 신·구 점수를 같은 축에 그리지 않기 위한 전제
    old_item = load_items(db_session, old.ktib_version)[0]
    assert old_item.workspace_snapshot["visual_semantics"][0]["extractor_version"] == "EXT_v1"


def test_new_benchmark_episode_forces_new_ktib_version(db_session) -> None:
    """벤치마크 구성(에피소드 집합)이 바뀌어도 새 버전 — 점수 비교 축이 달라지므로."""
    _bench(db_session, "EP_A", "visual_naturalize")
    old = build_ktib(db_session, CFG)
    _bench(db_session, "EP_B", "text_naturalize")
    new = build_ktib(db_session, CFG)
    assert new.ktib_version != old.ktib_version
    assert old.episode_count == 1 and new.episode_count == 2
    assert len(load_items(db_session, old.ktib_version)) == 1  # 구 버전 불변


def test_frozen_items_cannot_be_mutated(db_session) -> None:
    """ktib_extractor_pinned=true인 동안 기존 스냅샷 덮어쓰기는 flush에서 차단된다."""
    assert CFG.visual_semantics.ktib_extractor_pinned is True
    _scenario(db_session, "CS_1", "EXT_v1")
    _bench(db_session, "EP_A", "visual_naturalize", scenario_id="CS_1")
    ktib = build_ktib(db_session, CFG)

    item = load_items(db_session, ktib.ktib_version)[0]
    item.workspace_snapshot = _workspace("EXT_v2")
    with pytest.raises(KtibFrozen):
        db_session.flush()
    db_session.rollback()


def test_frozen_version_row_cannot_be_mutated(db_session) -> None:
    """ktib_versions의 extractor 지문도 사후 수정 불가 — 계보를 다시 쓸 수 없다."""
    _bench(db_session, "EP_A", "visual_naturalize")
    ktib = build_ktib(db_session, CFG)
    ktib.extractor_versions = {"visual_semantics_extractors": ["FORGED"]}
    with pytest.raises(KtibFrozen):
        db_session.flush()
    db_session.rollback()


# --- AC 4: 정직성 — 빈 벤치마크·모호한 정답은 loud-fail ---


def test_empty_benchmark_raises_instead_of_zero(db_session) -> None:
    """자격 0건은 '정확도 0%'가 아니라 구성 실패다."""
    with pytest.raises(EmptyKtib):
        build_ktib(db_session, CFG)


def test_ambiguous_gold_label_raises(db_session) -> None:
    """label_distribution 최댓값이 동률이면 정답을 임의로 고르지 않는다."""
    _bench(db_session, "EP_TIE", "visual_naturalize",
           dist={"visual_naturalize": 0.5, "text_naturalize": 0.5})
    with pytest.raises(AmbiguousGoldLabel, match="동률"):
        build_ktib(db_session, CFG)
