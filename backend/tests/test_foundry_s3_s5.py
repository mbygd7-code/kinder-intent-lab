"""T1.8 AC (§1-S3~S5, §2).

- S3: situation_frame 적재 + extraction_confidence < extract_min → 사람 검토 큐
- S4: 대표형이 원문과 임베딩 유사도 > paraphrase_max면 폐기 (원문 잔존 방지, 규칙 7)
- S5: frame→scenario 변형 수 = config.foundry.scenario_variants
       scenario visual_semantics가 vs-1.0 통제 어휘 밖이면 거부
"""
import math

import pytest
from pydantic import ValidationError

from app.core.config import get_config
from app.foundry.stages.s3_extractor import (
    FrameInput,
    build_situation_frame,
    frames_needing_review,
    needs_human_review,
)
from app.foundry.stages.s4_language_miner import (
    AtlasInput,
    ParaphraseTooSimilar,
    cosine_similarity,
    mine_atlas_entry,
)
from app.foundry.stages.s5_situation_builder import (
    ScenarioVariantCountError,
    VisualSemanticsRejected,
    build_scenarios,
)
from app.models.foundry import AtlasEntry, CanonicalScenario, SourceDocument

CFG = get_config()


# --- S3: Extractor ---


def _frame_input(**kw) -> FrameInput:
    base = dict(
        domain="PLAY",
        summary="아이들이 나뭇잎 분류 놀이를 20분 이상 지속, 교사는 확장 여부를 고민",
        participants={"children": "4-6명", "age": "만4"},
        materials=["나뭇잎", "분류판"],
        teacher_concern="개입 시점과 방식",
        source_refs=["SRC_0007#p112"],
        extraction_confidence=0.82,
    )
    base.update(kw)
    return FrameInput(**base)


def test_build_situation_frame_persists(db_session) -> None:
    frame = build_situation_frame(db_session, _frame_input())
    db_session.flush()
    assert frame.frame_id.startswith("SF_")
    assert frame.domain == "PLAY"
    assert frame.extraction_confidence == pytest.approx(0.82)


def test_frame_invalid_domain_rejected() -> None:
    with pytest.raises(ValidationError):
        _frame_input(domain="MAGIC")


def test_low_confidence_frame_flagged_for_review(db_session) -> None:
    low = CFG.foundry.extract_min - 0.1
    frame = build_situation_frame(db_session, _frame_input(extraction_confidence=low))
    db_session.flush()
    assert needs_human_review(frame) is True
    assert frame.frame_id in {f.frame_id for f in frames_needing_review(db_session)}


def test_high_confidence_frame_not_flagged(db_session) -> None:
    frame = build_situation_frame(
        db_session, _frame_input(extraction_confidence=CFG.foundry.extract_min)
    )
    db_session.flush()
    assert needs_human_review(frame) is False
    assert frame.frame_id not in {f.frame_id for f in frames_needing_review(db_session)}


# --- S4: Teacher Language Miner (패러프레이즈 유사도 가드) ---


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _embed_fn(mapping: dict[str, list[float]]):
    return lambda texts: [mapping[t] for t in texts]


def _atlas_input(**kw) -> AtlasInput:
    base = dict(
        representative="자연스럽게 해달라는 요청",
        pattern_cluster="NATURALIZE",
        ambiguity_types=["TARGET_UNSPECIFIED", "VERB_POLYSEMY"],
        possible_intents=["text_naturalize", "visual_layout_refine"],
        resolution_signals=[{"signal": "selection_type", "rule": "photo면 VISUAL 우세"}],
        register={"style": "반말·해요체 혼재"},
        source_class_mix={"TEACHER_LANGUAGE": 0.71},
    )
    base.update(kw)
    return AtlasInput(**base)


def test_paraphrase_too_similar_discarded(db_session) -> None:
    """대표형이 원문과 거의 동일(유사도 1.0)이면 원문 잔존으로 간주해 폐기."""
    raw = "선생님이 실제로 쓴 원문 문장"
    rep = "선생님이 실제로 쓴 원문 문장"  # 사실상 원문 그대로
    embed = _embed_fn({raw: _unit([1.0, 0.0]), rep: _unit([1.0, 0.0])})
    before = db_session.query(AtlasEntry).count()
    with pytest.raises(ParaphraseTooSimilar):
        mine_atlas_entry(db_session, raw_text=raw, atlas=_atlas_input(representative=rep),
                         embed_fn=embed, config=CFG)
    db_session.flush()
    assert db_session.query(AtlasEntry).count() == before  # 적재 안 됨


def test_paraphrase_sufficiently_different_persisted(db_session) -> None:
    raw = "선생님이 실제로 쓴 원문 문장"
    rep = "자연스럽게 다듬어 달라는 취지의 요청 표현"
    embed = _embed_fn({raw: _unit([1.0, 0.0]), rep: _unit([0.0, 1.0])})  # 직교 → 유사도 0
    entry = mine_atlas_entry(db_session, raw_text=raw, atlas=_atlas_input(representative=rep),
                             embed_fn=embed, config=CFG)
    db_session.flush()
    assert entry.surface_form == rep
    assert entry.pattern_cluster == "NATURALIZE"


def test_paraphrase_at_threshold_kept(db_session) -> None:
    """경계: 유사도 == paraphrase_max는 폐기하지 않는다 (가드는 strict >)."""
    pmax = CFG.foundry.paraphrase_max
    raw = "원문"
    rep = "대표형"
    a = _unit([1.0, 0.0])
    b = _unit([pmax, math.sqrt(1 - pmax * pmax)])  # cos(a,b) == pmax
    embed = _embed_fn({raw: a, rep: b})
    assert cosine_similarity(a, b) == pytest.approx(pmax)
    entry = mine_atlas_entry(db_session, raw_text=raw, atlas=_atlas_input(representative=rep),
                             embed_fn=embed, config=CFG)
    db_session.flush()
    assert entry.surface_form == rep


def test_raw_text_never_persisted(db_session) -> None:
    """원문은 어디에도 저장되지 않는다 (surface_form은 대표형)."""
    raw = "저장되면 안 되는 원문 텍스트 XYZ"
    rep = "완전히 다른 대표 표현"
    embed = _embed_fn({raw: _unit([1.0, 0.0]), rep: _unit([0.0, 1.0])})
    entry = mine_atlas_entry(db_session, raw_text=raw, atlas=_atlas_input(representative=rep),
                             embed_fn=embed, config=CFG)
    db_session.flush()
    assert raw not in entry.surface_form
    assert db_session.query(SourceDocument).filter(SourceDocument.content == raw).count() == 0


# --- S5: Situation Builder (변형 수 = config, vs-1.0 통제 어휘) ---


def _vs(**kw) -> dict:
    base = dict(
        object_ref="photo_1",
        schema_version="vs-1.0",
        extractor_version="SYNTH_BUILDER_v1",
        scene_type=["OUTDOOR_YARD"],
        activity_types=["NATURE_SORTING"],
        materials=["LEAF", "TRAY"],
        observed_actions=["SORT", "COMPARE"],
        interaction_pattern=["PEER_COLLABORATIVE"],
        group_size_band="SMALL_GROUP",
        identity_removed=True,
    )
    base.update(kw)
    return base


def _variant(vs_overrides=None) -> dict:
    return {
        "surface_type": "play_board",
        "objects_summary": {"photo": 4, "text": 2},
        "selection": {"type": "photo", "count": 2},
        "recent_actions": ["move_object", "zoom_in"],
        "visual_semantics": [_vs(**(vs_overrides or {}))],
    }


def _frame(db_session):
    frame = build_situation_frame(db_session, _frame_input())
    db_session.flush()
    return frame


def test_build_scenarios_count_matches_config(db_session) -> None:
    frame = _frame(db_session)
    n = CFG.foundry.scenario_variants
    variants = [_variant() for _ in range(n)]
    scenarios = build_scenarios(db_session, frame, variants, CFG)
    db_session.flush()
    assert len(scenarios) == n
    persisted = (
        db_session.query(CanonicalScenario)
        .filter(CanonicalScenario.frame_id == frame.frame_id)
        .count()
    )
    assert persisted == n


def test_wrong_variant_count_rejected(db_session) -> None:
    frame = _frame(db_session)
    variants = [_variant() for _ in range(CFG.foundry.scenario_variants + 1)]
    with pytest.raises(ScenarioVariantCountError):
        build_scenarios(db_session, frame, variants, CFG)


def test_out_of_vocabulary_material_rejected(db_session) -> None:
    frame = _frame(db_session)
    variants = [_variant() for _ in range(CFG.foundry.scenario_variants)]
    variants[0]["visual_semantics"][0]["materials"] = ["MAGIC_WAND"]
    with pytest.raises(VisualSemanticsRejected):
        build_scenarios(db_session, frame, variants, CFG)


def test_free_text_visual_semantics_rejected(db_session) -> None:
    frame = _frame(db_session)
    variants = [_variant() for _ in range(CFG.foundry.scenario_variants)]
    variants[0]["visual_semantics"][0]["free_description"] = "아이들이 즐겁게 논다"
    with pytest.raises(VisualSemanticsRejected):
        build_scenarios(db_session, frame, variants, CFG)


def test_identity_removed_must_be_true(db_session) -> None:
    frame = _frame(db_session)
    variants = [_variant() for _ in range(CFG.foundry.scenario_variants)]
    variants[0]["visual_semantics"][0]["identity_removed"] = False
    with pytest.raises(VisualSemanticsRejected):
        build_scenarios(db_session, frame, variants, CFG)


def test_synthetic_extractor_version_required(db_session) -> None:
    """합성 생성분은 SYNTH_BUILDER_* 표기 (§1-S5 provenance)."""
    frame = _frame(db_session)
    variants = [_variant() for _ in range(CFG.foundry.scenario_variants)]
    variants[0]["visual_semantics"][0]["extractor_version"] = "vsx-0.3.1"  # 실측 extractor
    with pytest.raises(VisualSemanticsRejected):
        build_scenarios(db_session, frame, variants, CFG)


def test_synthetic_extractor_version_requires_underscore(db_session) -> None:
    """SYNTH_BUILDER_* 는 밑줄 구분자까지 요구 (SYNTH_BUILDERX 거부)."""
    frame = _frame(db_session)
    variants = [_variant() for _ in range(CFG.foundry.scenario_variants)]
    variants[0]["visual_semantics"][0]["extractor_version"] = "SYNTH_BUILDERX"
    with pytest.raises(VisualSemanticsRejected):
        build_scenarios(db_session, frame, variants, CFG)


def test_scenario_persists_workspace_state(db_session) -> None:
    frame = _frame(db_session)
    variants = [_variant() for _ in range(CFG.foundry.scenario_variants)]
    scenarios = build_scenarios(db_session, frame, variants, CFG)
    db_session.flush()
    ws = scenarios[0].workspace_state
    assert ws["surface_type"] == "play_board"
    assert ws["visual_semantics"][0]["materials"] == ["LEAF", "TRAY"]
