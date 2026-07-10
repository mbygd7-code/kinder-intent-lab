"""T4.3 AC (§6-7 Trace [0]~[6]): 클릭-투-트레인 E2E — brightness 불변 포함.

어두운 노드 클릭 → 진단(§7-3) → 전략·pack(§6-1·6-4) → Gym 세션 → HUMAN evidence →
Label Aggregator(§3-6: '최소 신호 수 도달'해야 전이 — 미달은 축적 유지, 2인 일치 → SILVER) →
노드 size/density 갱신 + pending_evaluation 링(§6-5).
**절대 규칙 3 / 원칙 8: 훈련은 brightness(heldout_accuracy 등)를 절대 바꾸지 않는다.**
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.brain.backfill import aggregate_evidence_stats, bootstrap_nodes
from app.brain.diagnosis import diagnose_node
from app.core.config import get_config
from app.core.db import get_session
from app.core.ontology import load_ontology
from app.gym.challenge import generate_pack
from app.gym.growth import finalize_session
from app.gym.pack import build_items
from app.gym.session import start_session, submit_results
from app.main import app
from app.models.brain import BrainNode, ConfusionEdge, Exemplar
from app.models.episodes import Episode, Evidence
from app.models.foundry import AtlasEntry, CanonicalScenario, FoundryWorkOrder
from app.models.guards import arena_brightness_write
from app.models.gym import ChallengePack, GymSession
from app.models.persona import PersonaCluster, PopulationPrior

CFG = get_config()
BUCKETS = ("synthetic", "weak_behavioral", "human_confirmed", "gold", "expert")


@pytest.fixture(autouse=True)
def _empty(db_session):
    """빈 슬레이트 — 실 DB 뱅크가 커버리지/카운트 전제를 깨지 않게 세이브포인트 안에서 비운다."""
    for model in (
        Evidence, Exemplar, FoundryWorkOrder, GymSession, ChallengePack,
        Episode, CanonicalScenario, AtlasEntry, ConfusionEdge,
        PopulationPrior, PersonaCluster, BrainNode,
    ):
        db_session.execute(delete(model))
    db_session.flush()


def _domain_intents():
    return [i.intent_id for i in load_ontology().intents if i.domain]


def _size(node_row) -> int:
    stats = node_row.evidence_stats or {}
    return sum(int(stats.get(b, 0) or 0) for b in BUCKETS)


def _live_buckets(node_row) -> set[str]:
    stats = node_row.evidence_stats or {}
    return {b for b in BUCKETS if stats.get(b, 0)}


def _synth_evidence(db, node, n):
    """노드에 합성 evidence n건(에피소드 경유) — 훈련 전 size/density 기준선(단일 버킷)."""
    for k in range(n):
        ep = f"EP_SYN_{node}_{k}"
        db.add(Episode(
            episode_id=ep, ontology_version="onto-1.0", lang="ko", dataset_split="TRAIN",
            reliability_tier="BRONZE", label_state="LABEL_CANDIDATE",
            origin_channel="FOUNDRY_SYNTHETIC", episode_creator_type="FOUNDRY_PIPELINE",
            primary_subject_type="SIMULATED_TEACHER", teacher_prompt="합성 발화",
            label_distribution={node: 1.0},
        ))
        db.add(Evidence(
            evidence_id=f"EV_SYN_{node}_{k}", episode_id=ep, intent_id=node, polarity="supports",
            strength=0.8, evidence_type="SYNTHETIC_CONSENSUS", actor_type="LLM_ANALYST",
            adversarial=False,
        ))


def _run_session(db, *, node, pack, mode, trainer):
    """세션 열기 → 모든 아이템에 node로 응답 → 제출. (items, report) 반환."""
    items = build_items(node_intent=node, mode=mode, config=CFG)
    assert items
    gym = start_session(db, trainer_ref=trainer, mode=mode, pack=pack, items=items)
    responses = [{"item_id": it["item_id"], "chosen_intent": node, "recovery_turns": 0}
                 for it in items]
    report = submit_results(db, gym, responses, CFG)
    db.flush()
    return gym, items, report


def test_click_to_train_trace_0_to_6(db_session) -> None:
    """§6-7 [0]~[6] 재현 — 1인은 축적, 2인 일치가 SILVER. size/density↑·pending, 밝기 불변."""
    node, other = _domain_intents()[:2]
    bootstrap_nodes(db_session, approved_by="lab")
    _synth_evidence(db_session, node, 5)              # 기준선: synthetic 5, density 0(단일 버킷)
    db_session.add(ConfusionEdge(  # CONFUSION_HIGH 유발 → pack C 전략·target_edges
        edge_id="CE_e2e", from_true=node, to_predicted=other,
        confusion_rate=CFG.growth.confusion_trigger + 0.2, state="observed",
        origin="GYM_CORRECTION",
    ))
    db_session.flush()
    aggregate_evidence_stats(db_session)
    db_session.flush()

    node_row = db_session.scalar(select(BrainNode).where(BrainNode.intent_id == node))

    # [0] 관찰: Dormant — brightness(heldout) None, 기준선 size=5, 단일 버킷(density 0)
    assert node_row.heldout_accuracy is None
    assert _size(node_row) == 5
    assert _live_buckets(node_row) == {"synthetic"}

    # [1] 진단 (§7-3 실계산 — 이 fixture에서 결정론: GOLD 0건 → LOW, 나머지 축은 데이터 없음)
    dg = diagnose_node(db_session, node, CFG)
    assert dg.gold_data.value == 0 and dg.gold_data.level == "LOW"
    assert dg.ambiguous_language.value is None      # Atlas 없음 — 지어내지 않음
    assert dg.screen_context_coverage.value is None

    # [2] 전략: generate_pack → C(confusion) 포함 + target_edges
    gp = generate_pack(db_session, node_intent=node, trigger="observatory_click", config=CFG)
    assert "C_CONFUSION" in gp.pack.strategy
    assert gp.pack.target_edges and gp.pack.target_edges[0]["to_predicted"] == other

    # [3][4] 트레이너 1: 세션 → HUMAN evidence (actor TEACHER_TRAINER, adversarial false)
    gym1, items, report1 = _run_session(
        db_session, node=node, pack=gp.pack, mode="choose_right_meaning", trainer="TR_A"
    )
    assert report1.evidence_created == len(items)
    human_ev = db_session.scalars(
        select(Evidence).where(Evidence.evidence_type == "HUMAN_CONFIRMATION")
    ).all()
    assert len(human_ev) == len(items)
    assert all(e.actor_type == "TEACHER_TRAINER" and e.adversarial is False for e in human_ev)

    # [5]-1인: 신호 1 < min_label_functions → §3-6대로 축적 유지(전이 없음), tier 미산출
    min_signals = CFG.label_aggregator.min_label_functions
    assert min_signals > 1  # 이 시나리오의 전제 — 바뀌면 아래 기대도 config에서 다시 유도해야 함
    fin1 = finalize_session(db_session, gym1, CFG)
    db_session.flush()
    assert fin1.episodes_aggregated == 0
    assert fin1.label_states == {"EVIDENCE_ACCUMULATING": len(items)}
    gym_eps = db_session.scalars(
        select(Episode).where(Episode.origin_channel == "GYM_HUMAN")
    ).all()
    assert all(e.label_state == "EVIDENCE_ACCUMULATING" for e in gym_eps)
    assert all(e.reliability_tier == "UNVERIFIED" for e in gym_eps)

    # [6]-1인: 훈련량은 즉시 반영 — size↑, density↑(2버킷), pending ring. 밝기 불변
    db_session.refresh(node_row)
    assert _size(node_row) == 5 + len(items)
    assert _live_buckets(node_row) == {"synthetic", "human_confirmed"}
    assert node_row.pending_evaluation is True and fin1.pending_set is True
    assert node_row.heldout_accuracy is None  # ★ 규칙 3: 훈련이 밝기를 못 바꾼다

    # [5]-2인 일치: 트레이너 2가 같은 발화에 같은 intent → 신호 2 → LABEL_CANDIDATE + SILVER
    gym2, _items2, report2 = _run_session(
        db_session, node=node, pack=gp.pack, mode="choose_right_meaning", trainer="TR_B"
    )
    assert report2.episodes_created == 0        # 새 에피소드 없음 — 기존 에피소드에 신호 부착
    assert report2.evidence_created == len(items)
    fin2 = finalize_session(db_session, gym2, CFG)
    db_session.flush()
    assert fin2.episodes_aggregated == len(items)
    assert fin2.label_states == {"LABEL_CANDIDATE": len(items)}
    for ep in gym_eps:
        db_session.refresh(ep)
        assert ep.label_state == "LABEL_CANDIDATE"   # 2인 일치 — 게이트 통과 (§6-7 [5])
        assert ep.reliability_tier == "SILVER"       # GOLD 아님 — §3-3 사람 검수로만
        assert ep.label_distribution == {node: 1.0}

    # [6]-2인: evidence 총량이 또 늘고, 밝기는 여전히 불변
    db_session.refresh(node_row)
    assert _size(node_row) == 5 + 2 * len(items)
    assert node_row.heldout_accuracy is None
    assert node_row.calibration_ece is None
    assert node_row.last_arena_run is None


def test_correction_drill_counts_into_size(db_session) -> None:
    """§6-5 '교정 20개가 들어오면 … evidence 카운트·density 즉시 변화' — HUMAN_CORRECTION도
    human_confirmed 버킷으로 집계된다 (리뷰 MAJOR: 교정 모드만 size가 안 늘던 결함)."""
    node = _domain_intents()[0]
    bootstrap_nodes(db_session, approved_by="lab")
    db_session.flush()
    gp = generate_pack(db_session, node_intent=node, trigger="observatory_click", config=CFG)
    gym, items, report = _run_session(
        db_session, node=node, pack=gp.pack, mode="correction_drill", trainer="TR_C"
    )
    assert report.by_type == {"HUMAN_CORRECTION": len(items)}
    finalize_session(db_session, gym, CFG)
    db_session.flush()
    node_row = db_session.scalar(select(BrainNode).where(BrainNode.intent_id == node))
    assert (node_row.evidence_stats or {}).get("human_confirmed") == len(items)  # 교정도 size에
    assert _size(node_row) == len(items)
    assert node_row.heldout_accuracy is None  # 규칙 3


def test_finalize_never_changes_brightness(db_session) -> None:
    """규칙 3 핵심: Arena가 기록한 heldout이 있어도 훈련(finalize)은 못 바꾼다 — pending만 켠다."""
    node = _domain_intents()[0]
    bootstrap_nodes(db_session, approved_by="lab")
    node_row = db_session.scalar(select(BrainNode).where(BrainNode.intent_id == node))
    # Arena 반영 경로를 흉내낸다 — 이 컨텍스트 밖의 대입은 BrightnessWriteBlocked(T5.4 가드)
    with arena_brightness_write("AR_prev"):
        node_row.heldout_accuracy = 0.62
        node_row.calibration_ece = 0.1
        node_row.last_arena_run = "AR_prev"
        db_session.flush()

    gp = generate_pack(db_session, node_intent=node, trigger="observatory_click", config=CFG)
    gym, _items, _report = _run_session(
        db_session, node=node, pack=gp.pack, mode="choose_right_meaning", trainer="TR_B"
    )
    finalize_session(db_session, gym, CFG)
    db_session.flush()

    db_session.refresh(node_row)
    assert node_row.heldout_accuracy == 0.62    # 훈련이 밝기를 못 바꾼다
    assert node_row.calibration_ece == 0.1
    assert node_row.last_arena_run == "AR_prev"
    assert node_row.pending_evaluation is True  # 하지만 pending 링은 켜진다


def test_empty_submit_does_not_light_pending(db_session) -> None:
    """정직성(§6-5): 훈련이 전혀 없던 제출(빈 results)은 pending 링을 켜지 않는다."""
    node = _domain_intents()[0]
    bootstrap_nodes(db_session, approved_by="lab")
    db_session.flush()
    gp = generate_pack(db_session, node_intent=node, trigger="observatory_click", config=CFG)
    items = build_items(node_intent=node, mode="choose_right_meaning", config=CFG)
    gym = start_session(
        db_session, trainer_ref="TR_E", mode="choose_right_meaning", pack=gp.pack, items=items
    )
    submit_results(db_session, gym, [], CFG)  # 빈 제출 — evidence 0
    db_session.flush()
    fin = finalize_session(db_session, gym, CFG)
    assert fin.pending_set is False
    node_row = db_session.scalar(select(BrainNode).where(BrainNode.intent_id == node))
    assert node_row.pending_evaluation is False


def test_finalize_without_pack_node_aggregates_but_no_ring(db_session) -> None:
    """pack origin에 node가 없어도 [5] 집계는 수행, 링은 어느 노드에도 안 켠다(추측 금지)."""
    node = _domain_intents()[0]
    bootstrap_nodes(db_session, approved_by="lab")
    db_session.flush()
    from app.gym.pack import build_pack
    pack = build_pack(  # node=None pack — origin에 node 키 없음(exclude_none)
        db_session, trigger="observatory_click", node=None, region=None,
        diagnosis=None, target_confusion=None, config=CFG,
    )
    items = build_items(node_intent=node, mode="choose_right_meaning", config=CFG)
    gym = start_session(
        db_session, trainer_ref="TR_N", mode="choose_right_meaning", pack=pack, items=items
    )
    submit_results(
        db_session, gym,
        [{"item_id": it["item_id"], "chosen_intent": node} for it in items], CFG,
    )
    db_session.flush()
    fin = finalize_session(db_session, gym, CFG)
    assert fin.node_intent is None and fin.pending_set is False
    assert all(
        n.pending_evaluation is False for n in db_session.scalars(select(BrainNode))
    )  # 어느 노드에도 링 없음


def test_invalid_chosen_intent_rejected(db_session) -> None:
    """후보 밖 chosen_intent는 무시 — 임의 문자열이 evidence/label로 새지 않는다(위조 차단)."""
    node = _domain_intents()[0]
    bootstrap_nodes(db_session, approved_by="lab")
    db_session.flush()
    gp = generate_pack(db_session, node_intent=node, trigger="observatory_click", config=CFG)
    items = build_items(node_intent=node, mode="choose_right_meaning", config=CFG)
    gym = start_session(
        db_session, trainer_ref="TR_X", mode="choose_right_meaning", pack=gp.pack, items=items
    )
    report = submit_results(
        db_session, gym,
        [{"item_id": items[0]["item_id"], "chosen_intent": "NOT_AN_INTENT"}], CFG,
    )
    assert report.evidence_created == 0 and report.episodes_created == 0
    assert db_session.scalars(
        select(Evidence).where(Evidence.intent_id == "NOT_AN_INTENT")
    ).first() is None


@pytest.fixture()
def api(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_submit_endpoint_finalizes_and_sets_pending(api, db_session) -> None:
    """POST submit가 [5][6]까지 자동 수행 — 1인 신호는 축적 유지(집계 0), pending 링 점등."""
    node = _domain_intents()[0]
    bootstrap_nodes(db_session, approved_by="lab")
    db_session.flush()
    start = api.post("/v1/gym/session", json={
        "trainer_ref": "TR_API", "mode": "choose_right_meaning",
        "origin": {"node": node, "region": None, "diagnosis": ["GOLD_LOW"]},
    })
    assert start.status_code == 200
    sid = start.json()["session_id"]
    items = start.json()["items"]
    submit = api.post(f"/v1/gym/session/{sid}/submit", json={
        "results": [{"item_id": it["item_id"], "chosen_intent": node} for it in items],
    })
    assert submit.status_code == 200
    body = submit.json()
    assert body["node_intent"] == node
    assert body["pending_set"] is True
    assert body["episodes_aggregated"] == 0  # 1인 신호 — §3-6 축적 유지
    assert body["label_states"] == {"EVIDENCE_ACCUMULATING": len(items)}
    node_row = db_session.scalar(select(BrainNode).where(BrainNode.intent_id == node))
    assert node_row.pending_evaluation is True


def test_double_submit_returns_409_and_no_duplicates(api, db_session) -> None:
    """멱등 가드: 같은 세션 재-POST(재시도·더블클릭)는 409 — 에피소드·evidence 복제 없음."""
    node = _domain_intents()[0]
    bootstrap_nodes(db_session, approved_by="lab")
    db_session.flush()
    start = api.post("/v1/gym/session", json={
        "trainer_ref": "TR_DUP", "mode": "choose_right_meaning",
        "origin": {"node": node},
    })
    sid = start.json()["session_id"]
    items = start.json()["items"]
    payload = {"results": [{"item_id": it["item_id"], "chosen_intent": node} for it in items]}
    first = api.post(f"/v1/gym/session/{sid}/submit", json=payload)
    assert first.status_code == 200
    ev_after_first = db_session.scalar(
        select(Episode.episode_id).where(Episode.origin_channel == "GYM_HUMAN").limit(1)
    )
    assert ev_after_first is not None
    n_ev = len(db_session.scalars(select(Evidence)).all())

    second = api.post(f"/v1/gym/session/{sid}/submit", json=payload)  # 재전송
    assert second.status_code == 409
    assert len(db_session.scalars(select(Evidence)).all()) == n_ev  # 복제 0
