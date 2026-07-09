"""T4.2 AC (§6-1·§6-3·§6-4): Challenge Pack 생성기.

진단(§7-3 실계산) + confusion_edges → 강화 전략(A/B/C/D, 복합) → target_edges(우선순위) → pack.

AC:
- COVERAGE_LOW → A형(Data Coverage)은 사람 세션 없이 Foundry 작업 큐(foundry_work_queue)로 발행
- CONFUSION_HIGH → target_edges 포함 pack (confusion_rate 내림차순, trigger 미만 제외)
- 생성된 pack이 challenge_pack.schema.json 왕복 통과
전략 임계·우선순위 가중치는 전부 config(절대 규칙 1). 진단 코드는 서버가 실계산(프론트 미신뢰).
"""
import json
from pathlib import Path

import jsonschema
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.core.config import get_config
from app.core.db import get_session
from app.core.ontology import load_ontology
from app.gym.challenge import (
    NodeSignals,
    derive_diagnosis_codes,
    generate_pack,
    pack_to_dict,
    priority_score,
    rank_target_edges,
)
from app.main import app
from app.models.brain import ConfusionEdge, Exemplar
from app.models.episodes import Episode, Evidence
from app.models.foundry import AtlasEntry, CanonicalScenario, FoundryWorkOrder
from app.models.gym import ChallengePack, GymSession
from app.models.persona import PersonaCluster, PopulationPrior

CFG = get_config()
REPO_ROOT = Path(__file__).resolve().parents[2]
PACK_SCHEMA = json.loads(
    (REPO_ROOT / "schemas" / "challenge_pack.schema.json").read_text(encoding="utf-8")
)


@pytest.fixture(autouse=True)
def _empty(db_session):
    """빈 슬레이트 — 실 DB에 쌓인 행이 있어도 이 테스트의 계산 전제를 깨지 않게 세이브포인트
    안에서 비운다(FK 순서: 자식 → 부모). db_session 롤백으로 원복.

    persona_clusters까지 비운다 — _persona_mix가 이를 읽어 남겨두면 persona_mix가 실 DB
    상태를 반영해 재현 불가해진다. population_priors가 clusters를 FK 참조하므로 먼저 지운다."""
    for model in (
        Evidence, Exemplar, FoundryWorkOrder, GymSession, ChallengePack,
        Episode, CanonicalScenario, AtlasEntry, ConfusionEdge,
        PopulationPrior, PersonaCluster,
    ):
        db_session.execute(delete(model))
    db_session.flush()


def _domain_intents() -> list[str]:
    return [i.intent_id for i in load_ontology().intents if i.domain]


def _atlas(db, aid, intents):
    db.add(AtlasEntry(
        atlas_id=aid, surface_form=f"발화 {aid}", pattern_cluster="pc",
        ambiguity_types=[], possible_intents=intents, resolution_signals=[],
    ))


def _scenario(db, sid, axis):
    db.add(CanonicalScenario(
        scenario_id=sid, frame_id=None, workspace_state={"objects": [axis]}, variation_axis=axis,
    ))


def _episode(db, epid, intent, *, scenario=None, persona=None, gold=False):
    db.add(Episode(
        episode_id=epid, ontology_version="onto-1.0", lang="ko", dataset_split="TRAIN",
        reliability_tier="GOLD" if gold else "UNVERIFIED",
        label_state="LABELED" if gold else "EVIDENCE_ACCUMULATING",
        origin_channel="FOUNDRY_SYNTHETIC", episode_creator_type="FOUNDRY_PIPELINE",
        primary_subject_type="SIMULATED_TEACHER", teacher_prompt="발화",
        label_distribution={intent: 1.0}, scenario_id=scenario, persona_lens_used=persona,
    ))


def _edge(db, eid, from_true, to_pred, rate, *, contrast=None):
    db.add(ConfusionEdge(
        edge_id=eid, from_true=from_true, to_predicted=to_pred, confusion_rate=rate,
        state="observed", origin="GYM_CORRECTION", contrast_exemplars=contrast,
    ))


# --- AC 1: COVERAGE_LOW → A형 Foundry 작업 큐 발행(사람 세션 없음) ---


def test_coverage_low_publishes_foundry_order_without_session(db_session) -> None:
    node = _domain_intents()[0]
    # 전체 변형축 4종, 노드는 1종만 커버 → coverage 0.25 < screen_coverage_low(0.3) = LOW
    for ax in ("ax1", "ax2", "ax3", "ax4"):
        _scenario(db_session, f"SC_{ax}", ax)
    db_session.flush()
    _episode(db_session, "EP1", node, scenario="SC_ax1")
    db_session.flush()

    result = generate_pack(db_session, node_intent=node, trigger="observatory_click", config=CFG)

    assert "COVERAGE_LOW" in result.diagnosis_codes
    assert "A_DATA_COVERAGE" in result.pack.strategy
    # Foundry 작업 큐로 발행됨 — 사람 세션 없이
    orders = db_session.scalars(
        select(FoundryWorkOrder).where(FoundryWorkOrder.pack_id == result.pack.pack_id)
    ).all()
    assert len(orders) == 1
    assert orders[0].order_type == "SCENARIO_COVERAGE"
    assert orders[0].status == "PENDING"
    assert orders[0].intent_id == node
    # 사람 세션(GymSession)은 생성되지 않는다 — A형은 사람 불필요(§6-1)
    assert db_session.scalar(select(func.count()).select_from(GymSession)) == 0


# --- AC 2: CONFUSION_HIGH → target_edges 포함 (rate 내림차순, trigger 미만 제외) ---


def test_confusion_high_includes_ordered_target_edges(db_session) -> None:
    node, b, c, d = _domain_intents()[:4]
    trig = CFG.growth.confusion_trigger
    # 삽입 순서를 일부러 오름차순으로 → 정렬 없는(filter-only) 회귀면 [c,b]라 실패한다
    _edge(db_session, "CE_hot2", node, c, trig + 0.10)   # 중간 (먼저 삽입)
    _edge(db_session, "CE_hot1", node, b, trig + 0.30)   # 최고 (나중 삽입)
    _edge(db_session, "CE_cold", node, d, trig - 0.10)   # trigger 미만 → 제외
    db_session.flush()

    result = generate_pack(db_session, node_intent=node, trigger="observatory_click", config=CFG)

    assert "CONFUSION_HIGH" in result.diagnosis_codes
    assert "C_CONFUSION" in result.pack.strategy
    edges = result.pack.target_edges
    assert [e["to_predicted"] for e in edges] == [b, c]  # rate desc(삽입순 아님), cold 제외
    assert all(e["from_true"] == node for e in edges)


def test_no_confusion_edges_means_no_target_edges(db_session) -> None:
    node = _domain_intents()[0]
    result = generate_pack(db_session, node_intent=node, trigger="observatory_click", config=CFG)
    assert "CONFUSION_HIGH" not in result.diagnosis_codes
    assert result.pack.target_edges is None


# --- AC 3: pack 스키마 왕복 ---


def test_generated_pack_roundtrips_schema(db_session) -> None:
    node, b = _domain_intents()[:2]
    _edge(db_session, "CE_x", node, b, CFG.growth.confusion_trigger + 0.2,
          contrast=[{"utterance": "이거 치워줄래?", "true_intent": node}])
    for ax in ("ax1", "ax2"):
        _scenario(db_session, f"SC_{ax}", ax)
    db_session.flush()
    _episode(db_session, "EPc", node, scenario="SC_ax1", persona="p1")
    db_session.flush()

    result = generate_pack(db_session, node_intent=node, trigger="observatory_click", config=CFG)
    d = pack_to_dict(result.pack)
    jsonschema.validate(d, PACK_SCHEMA)
    # 스키마엔 additionalProperties:false가 없어 왕복만으론 optional 필드 누락/오타를 못 잡는다
    # → 직렬화기가 필드명·존재를 지키는지 직접 고정한다.
    assert [e["to_predicted"] for e in d["target_edges"]] == [b]
    assert d["target_edges"][0]["from_true"] == node
    assert d["difficulty_curve"] == "hard"                    # CONFUSION_HIGH → hard
    assert d["expected_yield"]["contrast_pairs"] == 1         # contrast exemplar 1건 반영
    assert "node_priority" in d["expected_yield"]


# --- §6-3 우선순위 실제 배선 (dead-code 아님) ---


def test_priority_score_is_wired_into_generated_pack(db_session) -> None:
    """generate_pack이 priority_score를 실제 호출해 pack·응답에 node_priority를 남긴다."""
    node = _domain_intents()[0]
    result = generate_pack(db_session, node_intent=node, trigger="observatory_click", config=CFG)
    assert isinstance(result.node_priority, float)
    assert result.pack.expected_yield["node_priority"] == result.node_priority
    # 빈 노드(heldout 미측정=1.0, evidence 0=1.0, persona None=0.5) → 가중합이 양수
    assert result.node_priority > 0.0


# --- 복합 전략(§6-1: A+C, GOLD_LOW가 늘 함께 → B) ---


def test_composite_strategy_a_and_c(db_session) -> None:
    node, b = _domain_intents()[:2]
    for ax in ("ax1", "ax2", "ax3", "ax4"):
        _scenario(db_session, f"SC_{ax}", ax)
    db_session.flush()
    _episode(db_session, "EP1", node, scenario="SC_ax1")  # coverage 0.25 → LOW
    _edge(db_session, "CE_1", node, b, CFG.growth.confusion_trigger + 0.2)  # CONFUSION_HIGH
    db_session.flush()

    result = generate_pack(db_session, node_intent=node, trigger="observatory_click", config=CFG)
    # A(coverage) + C(confusion) + B(gold 0 < gold_low_threshold) 복합
    assert {"A_DATA_COVERAGE", "C_CONFUSION", "B_HUMAN_EVIDENCE"} <= set(result.pack.strategy)


def test_empty_node_falls_back_to_gold_low_b(db_session) -> None:
    """데이터 전무 노드: gold 0 < threshold → GOLD_LOW → B(human evidence) 폴백, 사람 필요."""
    node = _domain_intents()[0]
    result = generate_pack(db_session, node_intent=node, trigger="observatory_click", config=CFG)
    assert result.diagnosis_codes == ["GOLD_LOW"]
    assert result.pack.strategy == ["B_HUMAN_EVIDENCE"]
    assert result.needs_human is True


# --- 우선순위 샘플링(§6-3) 단위 ---


def test_rank_target_edges_orders_desc_and_filters(db_session) -> None:
    node, b, c, d = _domain_intents()[:4]
    e_hi = ConfusionEdge(edge_id="E1", from_true=node, to_predicted=b,
                         confusion_rate=0.9, state="observed")
    e_mid = ConfusionEdge(edge_id="E2", from_true=node, to_predicted=c,
                          confusion_rate=CFG.growth.confusion_trigger, state="observed")
    e_lo = ConfusionEdge(edge_id="E3", from_true=node, to_predicted=d,
                         confusion_rate=0.0, state="hypothesized")
    e_null = ConfusionEdge(edge_id="E4", from_true=node, to_predicted=b,
                           confusion_rate=None, state="hypothesized")
    # 입력에서 자격 edge를 오름차순(E2 먼저, E1 나중)으로 둔다 → 정렬 없는 회귀면 [E2,E1]이라 실패
    ranked = rank_target_edges([e_lo, e_null, e_mid, e_hi], CFG)
    assert [e.edge_id for e in ranked] == ["E1", "E2"]  # desc, trigger 이상만, null 제외


def test_a_or_d_only_needs_no_human_delivery() -> None:
    """§6-1: A/D형만이면 사람 배달 모드가 없다([]) → 사람 세션 불필요(needs_human False 원천)."""
    from app.gym.challenge import delivery_modes_for
    assert delivery_modes_for(["A_DATA_COVERAGE"], ["COVERAGE_LOW"]) == []
    assert delivery_modes_for(["D_MODEL"], ["PERFORMANCE_DROP"]) == []
    # B/C가 섞이면 사람 배달이 생긴다
    mixed = delivery_modes_for(
        ["A_DATA_COVERAGE", "B_HUMAN_EVIDENCE"], ["COVERAGE_LOW", "GOLD_LOW"]
    )
    assert mixed == ["choose_right_meaning"]


def test_priority_score_ranks_weaker_node_higher(db_session) -> None:
    """§6-3: heldout 낮고·confusion 높고·evidence 적을수록 우선순위 점수가 높다."""
    weak = NodeSignals(
        heldout=0.30, confusion_rate=0.60, performance_drop=0.10,
        evidence_ratio=0.05, persona_entropy=0.10, service_importance=0.9,
    )
    strong = NodeSignals(
        heldout=0.95, confusion_rate=0.02, performance_drop=0.0,
        evidence_ratio=0.95, persona_entropy=0.95, service_importance=0.1,
    )
    assert priority_score(weak, CFG) > priority_score(strong, CFG)


def test_derive_codes_persona_and_ambiguous(db_session) -> None:
    node, b, c, d = _domain_intents()[:4]
    # persona 단일 → 엔트로피 0 = LOW; Atlas 경쟁 intent 3 ≥ ambiguous_competitors_high(2.5) = HIGH
    _episode(db_session, "EP1", node, persona="p1")
    _episode(db_session, "EP2", node, persona="p1")
    _atlas(db_session, "A1", [node, b, c, d])  # 경쟁 3
    _atlas(db_session, "A2", [node, b, c, d])
    db_session.flush()
    from app.brain.diagnosis import diagnose_node
    dg = diagnose_node(db_session, node, CFG)
    codes = derive_diagnosis_codes(dg, [], CFG)
    assert "PERSONA_DIVERSITY_LOW" in codes
    assert "AMBIGUOUS_LANGUAGE_HIGH" in codes


# --- API (POST /v1/gym/pack) ---


@pytest.fixture()
def api(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_generate_pack_endpoint_returns_pack(api, db_session) -> None:
    node, b = _domain_intents()[:2]
    _edge(db_session, "CE_api", node, b, CFG.growth.confusion_trigger + 0.2)
    db_session.flush()
    r = api.post("/v1/gym/pack", json={"node_intent": node})
    assert r.status_code == 200
    body = r.json()
    assert body["pack"]["pack_id"].startswith("CP_")
    assert "C_CONFUSION" in body["strategy"]
    assert body["needs_human"] is True
    jsonschema.validate(body["pack"], PACK_SCHEMA)


def test_generate_pack_endpoint_unknown_intent_404(api) -> None:
    assert api.post("/v1/gym/pack", json={"node_intent": "NOPE"}).status_code == 404
