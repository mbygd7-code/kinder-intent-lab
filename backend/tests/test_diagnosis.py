"""T4.1 AC (§7-3): Weakness 진단 4축 실계산.

§7-3 표의 계산 정의와 1:1:
- Ambiguous Language = 이 intent가 possible_intents에 등장하는 Atlas 패턴들의 평균 경쟁 intent 수
- Screen Context Coverage = 이 노드 episode들의 workspace 상태 조합(S5 변형축) 커버리지
- Persona Diversity = 노드 episode의 persona 분포 엔트로피
- Gold Data = GOLD evidence(에피소드) 절대량
데이터 없으면 값은 None(지어내지 않음). 레벨 버킷 임계는 config.diagnosis(절대 규칙 1).
"""
import pytest
from sqlalchemy import delete

from app.brain.diagnosis import diagnose_node
from app.core.config import get_config
from app.core.ontology import load_ontology
from app.models.arena import ArenaRun, KtibItem, KtibVersion
from app.models.brain import Exemplar
from app.models.episodes import Episode, Evidence
from app.models.foundry import AtlasEntry, CanonicalScenario

CFG = get_config()


@pytest.fixture(autouse=True)
def _empty(db_session):
    # FK 순서: arena/ktib → evidence·exemplar → episode → canonical_scenario (자식 먼저)
    db_session.execute(delete(ArenaRun))
    db_session.execute(delete(KtibItem))
    db_session.execute(delete(KtibVersion))
    db_session.execute(delete(Evidence))
    db_session.execute(delete(Exemplar))
    db_session.execute(delete(Episode))
    db_session.execute(delete(CanonicalScenario))
    db_session.execute(delete(AtlasEntry))
    db_session.flush()


def _intent(idx=0):
    return [i.intent_id for i in load_ontology().intents if i.domain][idx]


def _atlas(db, aid, surface, intents):
    db.add(AtlasEntry(
        atlas_id=aid, surface_form=surface, pattern_cluster="pc",
        ambiguity_types=[], possible_intents=intents, resolution_signals=[],
    ))


def _scenario(db, sid, axis):
    # frame_id nullable — SituationFrame FK 없이 시나리오만 (진단은 variation_axis만 읽는다)
    db.add(CanonicalScenario(
        scenario_id=sid, frame_id=None, workspace_state={"objects": [axis]}, variation_axis=axis,
    ))


def _episode(db, epid, intent, *, tier="TRAIN_UNVERIFIED", scenario=None, persona=None, gold=False):
    db.add(Episode(
        episode_id=epid, ontology_version="onto-1.0", lang="ko", dataset_split="TRAIN",
        reliability_tier="GOLD" if gold else "UNVERIFIED",
        label_state="LABELED" if gold else "EVIDENCE_ACCUMULATING",
        origin_channel="FOUNDRY_SYNTHETIC", episode_creator_type="FOUNDRY_PIPELINE",
        primary_subject_type="SIMULATED_TEACHER", teacher_prompt="발화",
        label_distribution={intent: 1.0}, scenario_id=scenario, persona_lens_used=persona,
    ))


# --- Ambiguous Language (§7-3: Atlas 평균 경쟁 intent 수) ---


def test_ambiguous_language_avg_competitors(db_session) -> None:
    node, b, c = _intent(0), _intent(1), _intent(2)
    # node가 등장하는 2개 패턴: [node,b,c](경쟁 2), [node,b](경쟁 1) → 평균 1.5
    _atlas(db_session, "A1", "발화1", [node, b, c])
    _atlas(db_session, "A2", "발화2", [node, b])
    _atlas(db_session, "A3", "발화3", [b, c])  # node 없음 — 무관
    db_session.flush()
    dg = diagnose_node(db_session, node, CFG)
    assert dg.ambiguous_language.value == pytest.approx(1.5)
    assert dg.ambiguous_language.level == "MED"  # 1.0 ≤ 1.5 < 2.5


def test_ambiguous_language_none_when_absent(db_session) -> None:
    node = _intent(0)
    _atlas(db_session, "A1", "발화", [_intent(1), _intent(2)])  # node 미등장
    db_session.flush()
    assert diagnose_node(db_session, node, CFG).ambiguous_language.value is None


# --- Screen Context Coverage (§7-3: S5 변형축 커버리지) ---


def test_screen_context_coverage_fraction(db_session) -> None:
    node = _intent(0)
    # 전체 변형축 4종(ax1..ax4), 노드 에피소드는 2종만 커버 → 0.5
    for ax in ("ax1", "ax2", "ax3", "ax4"):
        _scenario(db_session, f"SC_{ax}", ax)
    db_session.flush()  # 시나리오를 에피소드 FK보다 먼저 적재
    _episode(db_session, "EP1", node, scenario="SC_ax1")
    _episode(db_session, "EP2", node, scenario="SC_ax2")
    _episode(db_session, "EPX", _intent(1), scenario="SC_ax3")  # 다른 intent
    db_session.flush()
    dg = diagnose_node(db_session, node, CFG)
    assert dg.screen_context_coverage.value == pytest.approx(0.5)
    assert dg.screen_context_coverage.level == "MED"  # 0.3 ≤ 0.5 < 0.6


def test_screen_context_coverage_none_without_scenarios(db_session) -> None:
    node = _intent(0)
    _episode(db_session, "EP1", node)  # scenario 없음
    db_session.flush()
    assert diagnose_node(db_session, node, CFG).screen_context_coverage.value is None


# --- Persona Diversity (§7-3: persona 분포 엔트로피) ---


def test_persona_diversity_entropy(db_session) -> None:
    node = _intent(0)
    # persona 2종 균등(p1,p2) → 정규화 엔트로피 1.0
    _episode(db_session, "EP1", node, persona="p1")
    _episode(db_session, "EP2", node, persona="p2")
    db_session.flush()
    dg = diagnose_node(db_session, node, CFG)
    assert dg.persona_diversity.value == pytest.approx(1.0)
    assert dg.persona_diversity.level == "HIGH"


def test_persona_diversity_single_persona_zero(db_session) -> None:
    node = _intent(0)
    _episode(db_session, "EP1", node, persona="p1")
    _episode(db_session, "EP2", node, persona="p1")  # 한 종류만 → 엔트로피 0
    db_session.flush()
    dg = diagnose_node(db_session, node, CFG)
    assert dg.persona_diversity.value == pytest.approx(0.0)
    assert dg.persona_diversity.level == "LOW"


def test_persona_diversity_skewed_is_real_entropy(db_session) -> None:
    """비대칭 분포(p1×3,p2×1) → 정규화 섀넌 엔트로피 ≈0.811 (distinct-count 아님)."""
    node = _intent(0)
    for i in range(3):
        _episode(db_session, f"EP_p1_{i}", node, persona="p1")
    _episode(db_session, "EP_p2", node, persona="p2")
    db_session.flush()
    dg = diagnose_node(db_session, node, CFG)
    assert dg.persona_diversity.value == pytest.approx(0.8113, abs=1e-3)  # [0.75,0.25] 정규화 H
    assert dg.persona_diversity.level == "HIGH"  # 0.811 ≥ 0.6


# --- Gold Data (§7-3: GOLD 절대량) ---


def test_gold_data_absolute_count(db_session) -> None:
    node = _intent(0)
    _episode(db_session, "EPG1", node, gold=True)
    _episode(db_session, "EPG2", node, gold=True)
    _episode(db_session, "EPN", node)  # 비 GOLD — 미집계
    _episode(db_session, "EPGX", _intent(1), gold=True)  # 다른 intent
    db_session.flush()
    dg = diagnose_node(db_session, node, CFG)
    assert dg.gold_data.value == 2
    assert dg.gold_data.level == "LOW"  # 2 < gold_low(3)


def test_gold_data_zero_when_empty(db_session) -> None:
    dg = diagnose_node(db_session, _intent(0), CFG)
    assert dg.gold_data.value == 0 and dg.gold_data.level == "LOW"
    # 나머지 축은 데이터 없음 → None (정직성)
    assert dg.ambiguous_language.value is None
    assert dg.screen_context_coverage.value is None
    assert dg.persona_diversity.value is None


# --- 귀속 규칙: 최상위 라벨(막대 membership 아님) ---


def test_attribution_by_top_label_not_membership(db_session) -> None:
    """다중 intent 분포는 최상위 intent에만 귀속 — 하위 참여 intent엔 안 센다."""
    node, other = _intent(0), _intent(1)
    # node가 최상위(0.7) → node에 귀속
    db_session.add(Episode(
        episode_id="EP_TOP", ontology_version="onto-1.0", lang="ko", dataset_split="TRAIN",
        reliability_tier="GOLD", label_state="LABELED", origin_channel="FOUNDRY_SYNTHETIC",
        episode_creator_type="FOUNDRY_PIPELINE", primary_subject_type="SIMULATED_TEACHER",
        teacher_prompt="발화", label_distribution={node: 0.7, other: 0.3}, persona_lens_used="p1",
    ))
    # node가 하위(0.3) → node에 귀속 안 됨(최상위는 other)
    db_session.add(Episode(
        episode_id="EP_LOW", ontology_version="onto-1.0", lang="ko", dataset_split="TRAIN",
        reliability_tier="GOLD", label_state="LABELED", origin_channel="FOUNDRY_SYNTHETIC",
        episode_creator_type="FOUNDRY_PIPELINE", primary_subject_type="SIMULATED_TEACHER",
        teacher_prompt="발화", label_distribution={other: 0.7, node: 0.3}, persona_lens_used="p9",
    ))
    db_session.flush()
    dg = diagnose_node(db_session, node, CFG)
    assert dg.gold_data.value == 1                      # 최상위인 EP_TOP만
    assert dg.persona_diversity.value == pytest.approx(0.0)  # persona p1 하나만(EP_LOW 제외)
