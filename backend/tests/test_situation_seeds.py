"""킨더버스 화면 씨드 AC — seeds/situation_seeds_v1.yaml 수동 작성 구조 (2026-07-17 사용자 요청).

배경: 시나리오 172건 전부가 pilot의 코드 템플릿(_make_variant) 복제라
play_board / move_object·zoom_in / photo·text 단일 화면으로 굳었다. 재발 방지:
- 화면의 기본값(씨드)은 사람이 seeds/situation_seeds_v1.yaml에 작성한다 — 코드 템플릿 금지
- 로더가 어휘 밖 값·vs-1.0 위반·도메인 공백을 증산 시작 전에 거부한다
- 씨드 선택은 결정론(같은 salt → 같은 변형) — 재현 가능한 증산, §1-S5 변형 수 계약 유지
"""
import pytest
import yaml
from sqlalchemy import select

from app.core.config import get_config
from app.core.ontology import CANONICAL_DOMAINS
from app.foundry.situation_seeds import (
    SituationSeedError,
    load_situation_seeds,
    pick_variants,
)
from app.models.foundry import CanonicalScenario

CFG = get_config()


def _canon(d):
    """비교 정규화 — vs-1.0은 명시적 null 금지라 dump 시점에 따라 null 유무가 갈린다."""
    if isinstance(d, dict):
        return {k: _canon(v) for k, v in d.items() if v is not None}
    if isinstance(d, list):
        return [_canon(v) for v in d]
    return d


# --- tmp 씨드 파일 헬퍼 (깨진 파일은 실파일이 아니라 여기서 만든다) ---


def _vs_entry(**over) -> dict:
    base = {
        "object_ref": "photo_1",
        "schema_version": "vs-1.0",
        "extractor_version": "SYNTH_BUILDER_v1",
        "scene_type": ["INDOOR_CLASSROOM"],
        "activity_types": ["BLOCK_PLAY"],
        "observed_actions": ["BUILD"],
        "group_size_band": "SMALL_GROUP",
        "identity_removed": True,
    }
    base.update(over)
    return base


def _seed_doc(**over) -> dict:
    """전 도메인을 커버하는 최소 유효 씨드 문서 — over로 한 곳만 깨뜨려 테스트."""
    doc = {
        "version": "ss-test",
        "vocabulary": {
            "surface_types": {"play_board": "놀이 보드 화면"},
            "object_kinds": {"photo": "사진", "text": "글"},
            "actions": {"move_object": "카드를 옮김(드래그)"},
        },
        "seeds": [
            {
                "seed_id": "seed_all_domains",
                "domains": [],  # 빈 리스트 = 모든 도메인
                "workspace_state": {
                    "surface_type": "play_board",
                    "objects_summary": {"photo": 2, "text": 1},
                    "selection": {"type": "photo", "count": 1},
                    "recent_actions": ["move_object"],
                    "visual_semantics": [_vs_entry()],
                },
            }
        ],
    }
    doc.update(over)
    return doc


def _write(tmp_path, doc) -> str:
    p = tmp_path / "situation_seeds_test.yaml"
    p.write_text(yaml.safe_dump(doc, allow_unicode=True), encoding="utf-8")
    return str(p)


# --- 실파일 AC ---


def test_real_seed_file_loads_and_covers_all_domains() -> None:
    """★ 실파일이 로드되고, 8개 도메인 전부에 후보 씨드가 있다(도메인 공백 = 증산 즉사 방지)."""
    sf = load_situation_seeds()
    ids = [s.seed_id for s in sf.seeds]
    assert len(ids) == len(set(ids)), "seed_id 중복"
    for domain in CANONICAL_DOMAINS:
        candidates = [s for s in sf.seeds if not s.domains or domain in s.domains]
        assert candidates, f"도메인 {domain}에 씨드 후보가 없음"


def test_real_seed_file_screen_diversity() -> None:
    """★ 단일 화면(play_board 172건) 재발 방지 — 화면 종류·행동 어휘가 실제로 다양해야 한다."""
    sf = load_situation_seeds()
    surfaces = {s.workspace_state.surface_type for s in sf.seeds}
    actions = {a for s in sf.seeds for a in s.workspace_state.recent_actions}
    assert len(surfaces) >= 3, f"화면 종류가 {surfaces}뿐 — 하드코딩 시절과 다르지 않다"
    assert len(actions) >= 5, f"행동 어휘가 {actions}뿐"


def test_real_seed_vocabulary_matches_review_labels() -> None:
    """씨드 어휘는 검수 화면 한글 라벨 맵과 같은 집합 — 검수자에게 영어 원문 노출 방지."""
    sf = load_situation_seeds()
    used_surfaces = {s.workspace_state.surface_type for s in sf.seeds}
    used_actions = {a for s in sf.seeds for a in s.workspace_state.recent_actions}
    used_objects = {k for s in sf.seeds for k in s.workspace_state.objects_summary}
    assert used_surfaces <= set(sf.vocabulary.surface_types)
    assert used_actions <= set(sf.vocabulary.actions)
    assert used_objects <= set(sf.vocabulary.object_kinds)
    # 어휘 항목엔 전부 한글 라벨이 있어야 한다(빈 문자열 금지)
    for table in (sf.vocabulary.surface_types, sf.vocabulary.actions, sf.vocabulary.object_kinds):
        assert all(label.strip() for label in table.values())


# --- 로더 거부 AC (깨진 파일은 증산 시작 전에 죽어야 한다) ---


def test_out_of_vocabulary_values_rejected(tmp_path) -> None:
    """어휘 밖 surface/action/선택 대상은 로드 거부 — 수동 작성 오타의 어휘 오염 방지."""
    bad_surface = _seed_doc()
    bad_surface["seeds"][0]["workspace_state"]["surface_type"] = "whiteboard"
    with pytest.raises(SituationSeedError, match="whiteboard"):
        load_situation_seeds(_write(tmp_path, bad_surface))

    bad_action = _seed_doc()
    bad_action["seeds"][0]["workspace_state"]["recent_actions"] = ["teleport"]
    with pytest.raises(SituationSeedError, match="teleport"):
        load_situation_seeds(_write(tmp_path, bad_action))

    bad_selection = _seed_doc()
    bad_selection["seeds"][0]["workspace_state"]["selection"] = {"type": "hologram", "count": 1}
    with pytest.raises(SituationSeedError, match="hologram"):
        load_situation_seeds(_write(tmp_path, bad_selection))


def test_non_synthetic_extractor_rejected(tmp_path) -> None:
    """visual_semantics는 vs-1.0 계약 그대로 — 합성 표기(SYNTH_BUILDER_*) 아니면 거부 (§1-S5)."""
    doc = _seed_doc()
    doc["seeds"][0]["workspace_state"]["visual_semantics"] = [
        _vs_entry(extractor_version="REAL_EXTRACTOR_v1")
    ]
    with pytest.raises(SituationSeedError, match="SYNTH_BUILDER"):
        load_situation_seeds(_write(tmp_path, doc))


def test_domain_gap_rejected(tmp_path) -> None:
    """어느 도메인이든 후보 씨드가 0이면 로드 거부 — 증산 배분 단계에서 죽기 전에."""
    doc = _seed_doc()
    doc["seeds"][0]["domains"] = ["PLAY"]  # 나머지 7개 도메인 공백
    with pytest.raises(SituationSeedError, match="OBSERVATION"):
        load_situation_seeds(_write(tmp_path, doc))


def test_duplicate_seed_id_rejected(tmp_path) -> None:
    doc = _seed_doc()
    doc["seeds"].append({**doc["seeds"][0]})  # 같은 seed_id 복제
    with pytest.raises(SituationSeedError, match="seed_all_domains"):
        load_situation_seeds(_write(tmp_path, doc))


# --- 결정론 선택 AC ---


def test_pick_variants_deterministic_domain_scoped_and_recycles() -> None:
    """같은 salt → 같은 변형 k개(재현 가능 증산). 후보는 도메인 씨드에서만, 부족하면 순환."""
    sf = load_situation_seeds()
    k = CFG.foundry.scenario_variants
    a = pick_variants(sf, domain="PLAY", k=k, salt="run_x|PLAY|0")
    b = pick_variants(sf, domain="PLAY", k=k, salt="run_x|PLAY|0")
    assert a == b and len(a) == k

    allowed = [
        _canon(s.workspace_state.model_dump(mode="json"))
        for s in sf.seeds
        if not s.domains or "PLAY" in s.domains
    ]
    assert all(_canon(v) in allowed for v in a), "도메인 밖 씨드가 섞임"

    big = pick_variants(sf, domain="PLAY", k=len(allowed) + k, salt="run_y")
    assert len(big) == len(allowed) + k  # 풀보다 커도 순환 재사용으로 채운다


# --- 파이프라인 통합 AC: 증산 경로가 씨드를 유일 원천으로 쓴다 ---


def test_batch_pipeline_persists_seeded_scenarios(db_session) -> None:
    """★ batch S1~S5 준비가 씨드에서만 workspace를 만들고, 화면이 단일종으로 굳지 않는다."""
    from app.foundry.batch import prepare_scenarios

    scen = prepare_scenarios(db_session, run_id="run_seed_ac", config=CFG)
    ids = [s[0] for s in scen]
    rows = db_session.scalars(
        select(CanonicalScenario).where(CanonicalScenario.scenario_id.in_(ids))
    ).all()
    assert rows

    sf = load_situation_seeds()
    allowed = [_canon(s.workspace_state.model_dump(mode="json")) for s in sf.seeds]
    assert all(_canon(r.workspace_state) in allowed for r in rows), "씨드 밖 workspace가 생성됨"
    assert len({r.workspace_state["surface_type"] for r in rows}) >= 2, "화면이 단일종"


def test_campaign_prepare_uses_seeds(db_session) -> None:
    """증산 본선(campaign)도 같은 씨드 경로 — 스케줄이 만들어지고 전부 씨드 출신이다."""
    from app.foundry.campaign import prepare_campaign_scenarios

    target = CFG.foundry.scenario_variants * 2
    sched = prepare_campaign_scenarios(
        db_session, run_id="run_seed_camp", config=CFG, target_n=target
    )
    assert len(sched.scenarios) == target
    ids = {s[0] for s in sched.scenarios}
    rows = db_session.scalars(
        select(CanonicalScenario).where(CanonicalScenario.scenario_id.in_(ids))
    ).all()
    sf = load_situation_seeds()
    allowed = [_canon(s.workspace_state.model_dump(mode="json")) for s in sf.seeds]
    assert rows and all(_canon(r.workspace_state) in allowed for r in rows)
