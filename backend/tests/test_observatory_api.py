"""Observatory API AC (§7-1·§7-5·원칙 8): GET /v1/observatory/brain.

- 실 노드(governance 부트스트랩)가 region 집계와 함께 반환된다
- Arena 미실행이면 heldout/reliability/ktib_global 전부 null — 값을 지어내지 않는다
- evidence_total=버킷 합, diversity∈[0,1] (단일 버킷=0, 고른 분포일수록 큼)
- 훈련(evidence 추가)은 evidence_total만 바꾸고 heldout_accuracy는 못 바꾼다 (원칙 8)
- 응답이 observatory_brain.schema.json 왕복 통과
"""
import json
from pathlib import Path

import jsonschema
import pytest
from brain_helpers import _gold, _real_intents
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.brain.backfill import aggregate_evidence_stats, bootstrap_nodes
from app.core.db import get_session
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.main import app
from app.models.arena import ArenaRun
from app.models.brain import BrainNode, Exemplar
from app.models.episodes import Episode, Evidence


@pytest.fixture(autouse=True)
def _empty_bank(db_session):
    """정확 카운트 단언은 빈 뱅크 전제 — 실 DB에 에피소드·evidence가 쌓여도 깨지지 않게
    세이브포인트 안에서 비운다(FK 순서: evidence·exemplar → episode → node. 롤백으로 원복)."""
    db_session.execute(delete(Evidence))
    db_session.execute(delete(Exemplar))
    db_session.execute(delete(Episode))
    db_session.execute(delete(BrainNode))
    db_session.flush()

REPO_ROOT = Path(__file__).resolve().parents[2]
SCHEMA = json.loads(
    (REPO_ROOT / "schemas" / "observatory_brain.schema.json").read_text(encoding="utf-8")
)


@pytest.fixture()
def api(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        yield client, db_session
    app.dependency_overrides.clear()


def _evidence(db, eid, ep, intent, etype, *, adversarial=False, polarity="supports") -> None:
    db.add(Evidence(
        evidence_id=eid, episode_id=ep, intent_id=intent, polarity=polarity,
        strength=0.9, evidence_type=etype, actor_type="LLM_ANALYST",
        adversarial=adversarial,
    ))


def _seed_brain(db) -> list[str]:
    """노드 부트스트랩 + 에피소드/evidence 시드 + 집계."""
    bootstrap_nodes(db, approved_by="lab")
    ints = _real_intents(2)
    _gold(db, "EP_OBS_1", ints[0], "관찰 발화 하나")
    _gold(db, "EP_OBS_2", ints[1], "관찰 발화 둘")
    db.flush()
    _evidence(db, "EV_O1", "EP_OBS_1", ints[0], "SYNTHETIC_CONSENSUS")
    _evidence(db, "EV_O2", "EP_OBS_1", ints[0], "HUMAN_CONFIRMATION")
    _evidence(db, "EV_O3", "EP_OBS_2", ints[1], "SYNTHETIC_CONSENSUS")
    db.flush()
    aggregate_evidence_stats(db)
    db.flush()
    return ints


def test_returns_all_bootstrapped_nodes_with_regions(api) -> None:
    client, db = api
    _seed_brain(db)
    r = client.get("/v1/observatory/brain")
    assert r.status_code == 200
    body = r.json()
    real = [i for i in load_ontology().intents if i.intent_id != UNKNOWN_INTENT_ID]
    assert len(body["nodes"]) == len(real)  # 온톨로지 실 intent 전부 = 노드
    assert {n["region"] for n in body["nodes"]} == {r["region"] for r in body["regions"]}
    node_counts = {r["region"]: r["node_count"] for r in body["regions"]}
    assert sum(node_counts.values()) == len(real)


def test_no_arena_means_all_brightness_fields_null(api) -> None:
    """원칙 8: Arena 미실행 → ktib_global·reliability·heldout 전부 null (지어내지 않는다)."""
    client, db = api
    _seed_brain(db)
    body = client.get("/v1/observatory/brain").json()
    assert body["ktib_global"] is None
    assert all(r["reliability"] is None for r in body["regions"])
    assert all(n["heldout_accuracy"] is None for n in body["nodes"])


def test_evidence_total_and_diversity(api) -> None:
    client, db = api
    ints = _seed_brain(db)
    body = client.get("/v1/observatory/brain").json()
    nodes = {n["intent_id"]: n for n in body["nodes"]}
    # ints[0]: synthetic 1 + human_confirmed 1 + gold 1(에피소드) = total 3, 버킷 3종 → 다양
    # ints[1]: synthetic 1 + gold 1 = total 2, 버킷 2종
    assert nodes[ints[0]]["evidence_total"] == 3
    assert nodes[ints[1]]["evidence_total"] == 2
    assert 0.0 < nodes[ints[1]]["evidence_diversity"] < nodes[ints[0]]["evidence_diversity"] <= 1.0
    empty = next(n for n in body["nodes"] if n["intent_id"] not in ints)
    assert empty["evidence_total"] == 0 and empty["evidence_diversity"] == 0.0


def test_training_changes_size_not_brightness(api) -> None:
    """원칙 8 AC: 훈련 이벤트(evidence 적재)는 total만 바꾸고 brightness는 그대로."""
    client, db = api
    ints = _seed_brain(db)
    before = client.get("/v1/observatory/brain").json()
    b_node = next(n for n in before["nodes"] if n["intent_id"] == ints[0])

    _evidence(db, "EV_TRAIN", "EP_OBS_1", ints[0], "HUMAN_CONFIRMATION")  # 훈련 결과 evidence
    db.flush()
    aggregate_evidence_stats(db)
    db.flush()

    after = client.get("/v1/observatory/brain").json()
    a_node = next(n for n in after["nodes"] if n["intent_id"] == ints[0])
    assert a_node["evidence_total"] == b_node["evidence_total"] + 1  # size 원천은 변함
    assert b_node["heldout_accuracy"] is None
    assert a_node["heldout_accuracy"] is None  # brightness 불변 — 훈련이 못 바꾼다
    assert after["ktib_global"] is None


def test_arena_written_fields_flow_through(api) -> None:
    """Arena가 컬럼을 채우면(시뮬레이션) 그대로 흐른다 — reliability=비null 평균, ktib=metrics."""
    client, db = api
    ints = _seed_brain(db)
    node = db.query(BrainNode).filter_by(intent_id=ints[0]).one()
    node.heldout_accuracy = 0.62  # Arena 러너 기록 시뮬레이션 (원천은 Arena)
    node.last_arena_run = "AR_1"
    db.add(ArenaRun(run_id="AR_1", model_version="seed-v0", ontology_version="onto-1.0",
                    persona_state_version="ps-1", extractor_versions={}, ktib_version="ktib-1",
                    metrics={"first_intent_accuracy": 0.618}))
    db.flush()
    body = client.get("/v1/observatory/brain").json()
    assert body["ktib_global"] == pytest.approx(0.618)
    n = next(x for x in body["nodes"] if x["intent_id"] == ints[0])
    assert n["heldout_accuracy"] == pytest.approx(0.62)
    region = next(r for r in body["regions"] if r["region"] == n["region"])
    assert region["reliability"] == pytest.approx(0.62)  # 비null 노드 평균


def test_adversarial_evidence_not_counted(api) -> None:
    """절대 규칙 6: adversarial evidence는 자연 분포 집계(=size 원천)에 안 들어간다."""
    client, db = api
    ints = _seed_brain(db)
    before = client.get("/v1/observatory/brain").json()
    b_total = next(n for n in before["nodes"] if n["intent_id"] == ints[0])["evidence_total"]
    _evidence(db, "EV_ADV", "EP_OBS_1", ints[0], "SYNTHETIC_CONSENSUS", adversarial=True)
    db.flush()
    aggregate_evidence_stats(db)
    db.flush()
    after = client.get("/v1/observatory/brain").json()
    assert next(n for n in after["nodes"] if n["intent_id"] == ints[0])["evidence_total"] == b_total


def test_response_roundtrips_schema(api) -> None:
    client, db = api
    _seed_brain(db)
    r = client.get("/v1/observatory/brain")
    jsonschema.validate(r.json(), SCHEMA)
