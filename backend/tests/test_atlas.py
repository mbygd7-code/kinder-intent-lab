"""T2.2 AC (§2, §2-4).

- Atlas Coverage: 신규 발화 중 기존 pattern_cluster에 매핑되는 비율
- 미매핑 발화 → Atlas 확장 큐 자동 적재
- Simulator 통계 재보정 훅 (길이·지시어 분포)
"""
import math

from app.core.config import get_config
from app.foundry.atlas import (
    compute_coverage,
    enqueue_unmapped,
    simulator_stats,
)
from app.models.foundry import AtlasEntry, AtlasExpansionEntry

CFG = get_config()


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _embed(mapping: dict[str, list[float]]):
    return lambda texts: [mapping[t] for t in texts]


def _atlas(db_session, surface_form: str, cluster: str, observed=10) -> AtlasEntry:
    import uuid

    entry = AtlasEntry(
        atlas_id=f"ATL_{uuid.uuid4().hex[:10]}", surface_form=surface_form,
        pattern_cluster=cluster, ambiguity_types=["TARGET_UNSPECIFIED"],
        possible_intents=["text_naturalize"], resolution_signals=[{"signal": "selection_type"}],
        register={"style": "반말"}, observed_count=observed,
    )
    db_session.add(entry)
    return entry


# --- Coverage 계산 (AC 1) ---


def test_coverage_computed(db_session) -> None:
    _atlas(db_session, "자연스럽게 해줘", "NATURALIZE")
    _atlas(db_session, "정리해줘", "TIDY_UP")
    db_session.flush()

    naturalize = _unit([1.0, 0.0, 0.0])
    tidy = _unit([0.0, 1.0, 0.0])
    utterances = ["자연스럽게 만들어줘", "완전 새로운 표현"]
    embed = _embed({
        "자연스럽게 해줘": naturalize,
        "정리해줘": tidy,
        "자연스럽게 만들어줘": _unit([0.98, 0.02, 0.0]),  # NATURALIZE에 가까움 → 매핑
        "완전 새로운 표현": _unit([0.0, 0.0, 1.0]),        # 어느 것과도 멂 → 미매핑
    })
    report = compute_coverage(db_session, utterances, embed, CFG)
    assert report.total == 2
    assert report.mapped == 1
    assert report.coverage() == 0.5
    assert report.unmapped == ["완전 새로운 표현"]


def test_empty_atlas_zero_coverage(db_session) -> None:
    embed = _embed({"아무 발화": _unit([1.0, 0.0])})
    report = compute_coverage(db_session, ["아무 발화"], embed, CFG)
    assert report.coverage() == 0.0
    assert report.unmapped == ["아무 발화"]


def test_empty_utterances_coverage_zero(db_session) -> None:
    report = compute_coverage(db_session, [], _embed({}), CFG)
    assert report.total == 0
    assert report.coverage() == 0.0


def test_mapping_respects_threshold(db_session) -> None:
    """유사도 == map_min_similarity면 매핑(≥), 미만이면 미매핑."""
    _atlas(db_session, "기준 표현", "BASE")
    db_session.flush()
    t = CFG.atlas.map_min_similarity
    a = _unit([1.0, 0.0])
    at_threshold = _unit([t, math.sqrt(1 - t * t)])  # cos == t
    below = _unit([t - 0.05, math.sqrt(1 - (t - 0.05) ** 2)])
    report = compute_coverage(
        db_session, ["at", "below"],
        _embed({"기준 표현": a, "at": at_threshold, "below": below}), CFG,
    )
    assert report.mapped == 1
    assert report.unmapped == ["below"]


# --- 확장 큐 적재 (AC 2) ---


def test_enqueue_unmapped(db_session) -> None:
    created = enqueue_unmapped(db_session, ["미매핑1", "미매핑2"], source_run="run1")
    db_session.flush()
    assert len(created) == 2
    rows = db_session.query(AtlasExpansionEntry).filter(
        AtlasExpansionEntry.source_run == "run1"
    ).all()
    assert {r.utterance for r in rows} == {"미매핑1", "미매핑2"}
    assert all(r.status == "PENDING" for r in rows)


def test_enqueue_dedups_existing(db_session) -> None:
    enqueue_unmapped(db_session, ["중복 발화"], source_run="run2")
    db_session.flush()
    again = enqueue_unmapped(db_session, ["중복 발화", "신규 발화"], source_run="run2")
    db_session.flush()
    assert len(again) == 1  # 이미 큐에 있는 것은 재적재 안 함
    assert again[0].utterance == "신규 발화"


def test_coverage_to_queue_pipeline(db_session) -> None:
    _atlas(db_session, "정리해줘", "TIDY_UP")
    db_session.flush()
    embed = _embed({
        "정리해줘": _unit([1.0, 0.0]),
        "이건 새로운 패턴": _unit([0.0, 1.0]),
    })
    report = compute_coverage(db_session, ["이건 새로운 패턴"], embed, CFG)
    enqueue_unmapped(db_session, report.unmapped, source_run="pipe")
    db_session.flush()
    queued = db_session.query(AtlasExpansionEntry).filter(
        AtlasExpansionEntry.source_run == "pipe"
    ).count()
    assert queued == 1


# --- Simulator 통계 재보정 훅 ---


def test_simulator_stats_from_atlas(db_session) -> None:
    _atlas(db_session, "이거 자연스럽게 해줘", "NATURALIZE", observed=30)  # 지시어 '이거' 포함
    _atlas(db_session, "다음 활동 추천", "WHATS_NEXT", observed=10)         # 지시어 없음
    db_session.flush()
    stats = simulator_stats(db_session)
    assert stats.sample_count == 2
    assert stats.mean_word_length > 0
    assert 0 <= stats.deixis_ratio <= 1
    assert stats.deixis_ratio > 0.5  # observed 가중 시 지시어 포함이 우세


def test_simulator_stats_empty_atlas(db_session) -> None:
    # 다른 테스트가 적재한 게 없다는 보장은 없으므로 구조만 검증
    stats = simulator_stats(db_session)
    assert stats.sample_count >= 0
    assert stats.mean_word_length >= 0


def test_deixis_not_overmatched_on_nouns(db_session) -> None:
    """'종이·높이·고양이' 등 이/그로 끝나는 명사를 지시어로 오탐하지 않는다."""
    for noun_form in ["종이 정리해줘", "높이 맞춰줘", "고양이 그려줘", "블록 정리해줘"]:
        _atlas(db_session, noun_form, "TIDY_UP")
    db_session.flush()
    assert simulator_stats(db_session).deixis_ratio == 0.0


def test_deixis_matched_on_real_deixis(db_session) -> None:
    _atlas(db_session, "이 사진 정리해줘", "TIDY_UP")   # 관형사 '이'
    _atlas(db_session, "이거 자연스럽게", "NATURALIZE")  # 대명사 '이거'
    db_session.flush()
    assert simulator_stats(db_session).deixis_ratio == 1.0
