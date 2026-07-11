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
from app.models.arena import RUN_TYPE_BRAIN, ArenaRun, KtibItem, KtibVersion
from app.models.brain import BrainNode, ConfusionEdge, Exemplar
from app.models.episodes import Episode, Evidence
from app.models.guards import arena_brightness_write


@pytest.fixture(autouse=True)
def _empty_bank(db_session):
    """정확 카운트 단언은 빈 뱅크 전제 — 실 DB에 에피소드·evidence가 쌓여도 깨지지 않게
    세이브포인트 안에서 비운다(FK 순서: evidence·exemplar → episode → node. 롤백으로 원복)."""
    db_session.execute(delete(ArenaRun))
    db_session.execute(delete(KtibItem))
    db_session.execute(delete(KtibVersion))
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
    db.add(KtibVersion(  # arena_runs.ktib_version FK (마이그레이션 0013)
        ktib_version="ktib-1", seq=1, extractor_versions={}, episode_count=1, content_hash="h",
    ))
    db.flush()
    node = db.query(BrainNode).filter_by(intent_id=ints[0]).one()
    # 밝기 쓰기는 Arena 반영 경로에서만 — 그 밖의 대입은 BrightnessWriteBlocked (T5.4 가드)
    with arena_brightness_write("AR_1"):
        node.heldout_accuracy = 0.62
        node.last_arena_run = "AR_1"
        db.flush()
    db.add(ArenaRun(run_id="AR_1", model_version="seed-v0", ontology_version="onto-1.0",
                    persona_state_version="ps-1", extractor_versions={}, ktib_version="ktib-1",
                    run_type=RUN_TYPE_BRAIN, metrics={"first_intent_accuracy": 0.618}))
    db.flush()
    body = client.get("/v1/observatory/brain").json()
    assert body["ktib_global"] == pytest.approx(0.618)
    n = next(x for x in body["nodes"] if x["intent_id"] == ints[0])
    assert n["heldout_accuracy"] == pytest.approx(0.62)
    region = next(r for r in body["regions"] if r["region"] == n["region"])
    assert region["reliability"] == pytest.approx(0.62)  # 비null 노드 평균
    assert region["measured_count"] == 1                 # §7-6 — 측정된 노드 1개
    assert region["stage"] == 1                          # Spark (측정 1건, 비율·신뢰도 미달)


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


def test_node_diagnosis_endpoint(api) -> None:
    """T4.1: 노드 4축 진단 — Gold Data는 GOLD 에피소드 절대량, 데이터 없는 축은 null(정직)."""
    client, db = api
    ints = _seed_brain(db)  # ints[0]은 GOLD 에피소드 1건(EP_OBS_1)
    r = client.get(f"/v1/observatory/node/{ints[0]}/diagnosis")
    assert r.status_code == 200
    body = r.json()
    assert body["intent_id"] == ints[0]
    assert body["gold_data"]["value"] == 1  # GOLD 1건
    assert body["gold_data"]["level"] == "LOW"  # 1 < gold_low(3)
    assert body["ambiguous_language"]["value"] is None   # Atlas 없음 → 계산 불가
    assert body["persona_diversity"]["value"] is None    # persona_lens 없음


def test_node_diagnosis_unknown_intent_404(api) -> None:
    client, _ = api
    assert client.get("/v1/observatory/node/NOT_A_REAL_INTENT/diagnosis").status_code == 404


def test_node_confusions_endpoint(api) -> None:
    """§5-6: from_true=intent인 방향성 혼동 edge를 대표 순서로. 측정 전이면 rate null·가설."""
    client, db = api
    ints = _seed_brain(db)
    # 실 DB의 기존 confusion_edges는 savepoint 안에서 비운다 — 정확 순서/개수 단언 전제
    db.execute(delete(ConfusionEdge))
    db.add(ConfusionEdge(edge_id="CE_HYP", from_true=ints[0], to_predicted=ints[1],
                         state="hypothesized", origin="SKEPTIC"))
    db.add(ConfusionEdge(edge_id="CE_MEAS", from_true=ints[0], to_predicted="ZZ_measured",
                         confusion_rate=0.4, state="confirmed", origin="ARENA_MATRIX"))
    db.add(ConfusionEdge(edge_id="CE_OTHER", from_true=ints[1], to_predicted=ints[0],
                         state="hypothesized", origin="SKEPTIC"))  # 다른 노드 — 안 나와야
    db.flush()
    body = client.get(f"/v1/observatory/node/{ints[0]}/confusions").json()
    assert body["intent_id"] == ints[0]
    assert body["measured"] is True  # 측정된 edge(0.4) 존재
    tos = [e["to_predicted"] for e in body["edges"]]
    assert tos == ["ZZ_measured", ints[1]]  # 측정된(confirmed 0.4)이 가설보다 먼저
    assert body["edges"][0]["confusion_rate"] == pytest.approx(0.4)
    assert body["edges"][0]["state"] == "confirmed"
    assert body["edges"][1]["confusion_rate"] is None  # 가설은 미측정 — 지어내지 않음


def test_node_confusions_none_measured(api) -> None:
    """가설만 있으면 measured=False, rate 전부 null (mock 아님 — 실 가설 edge)."""
    client, db = api
    ints = _seed_brain(db)
    db.execute(delete(ConfusionEdge))
    db.add(ConfusionEdge(edge_id="CE_H1", from_true=ints[0], to_predicted=ints[1],
                         state="hypothesized", origin="SKEPTIC"))
    db.flush()
    body = client.get(f"/v1/observatory/node/{ints[0]}/confusions").json()
    assert body["measured"] is False
    assert body["edges"][0]["confusion_rate"] is None
    assert body["edges"][0]["state"] == "hypothesized"


def test_node_confusions_unknown_intent_404(api) -> None:
    client, _ = api
    assert client.get("/v1/observatory/node/NOT_A_REAL_INTENT/confusions").status_code == 404


def test_brain_nodes_include_evidence_buckets(api) -> None:
    """§3-1 버킷이 노드에 그대로 노출 — 3D evidence 파티클 원천. 합 = evidence_total."""
    client, db = api
    ints = _seed_brain(db)
    body = client.get("/v1/observatory/brain").json()
    node = next(n for n in body["nodes"] if n["intent_id"] == ints[0])
    b = node["evidence_buckets"]
    assert set(b) == {"synthetic", "weak_behavioral", "human_confirmed", "gold", "expert"}
    assert sum(b.values()) == node["evidence_total"]
    # _seed_brain: ints[0] = synthetic 1 + human_confirmed 1 + gold 1(에피소드)
    assert b["synthetic"] == 1 and b["human_confirmed"] == 1 and b["gold"] == 1
    # 빈 노드도 버킷 키는 전부 있고 전부 0
    empty = next(n for n in body["nodes"] if n["intent_id"] not in ints)
    assert sum(empty["evidence_buckets"].values()) == 0


def test_global_confusion_edges(api) -> None:
    """§5-6 전체 edge 목록 — 측정 우선 정렬 + 정직 카운트(total/measured)."""
    client, db = api
    ints = _seed_brain(db)
    db.execute(delete(ConfusionEdge))
    db.add(ConfusionEdge(edge_id="CE_G1", from_true=ints[0], to_predicted=ints[1],
                         state="hypothesized", origin="SKEPTIC"))
    db.add(ConfusionEdge(edge_id="CE_G2", from_true=ints[1], to_predicted=ints[0],
                         confusion_rate=0.25, state="confirmed", origin="ARENA_MATRIX"))
    db.flush()
    body = client.get("/v1/observatory/confusion-edges").json()
    assert body["total"] == 2
    assert body["measured_count"] == 1
    assert body["edges"][0]["edge_id"] == "CE_G2"   # 측정된 edge 먼저
    assert body["edges"][0]["confusion_rate"] == pytest.approx(0.25)
    assert body["edges"][0]["from_intent"] == ints[1]
    assert body["edges"][0]["to_intent"] == ints[0]
    assert body["edges"][1]["confusion_rate"] is None  # 가설 — 지어내지 않음
    assert body["edges"][1]["state"] == "hypothesized"


def test_global_confusion_edges_empty(api) -> None:
    client, db = api
    db.execute(delete(ConfusionEdge))
    db.flush()
    body = client.get("/v1/observatory/confusion-edges").json()
    assert body == {"total": 0, "measured_count": 0, "edges": []}


def _upload_yaml(intent: str, prompt: str, *, kappa: float = 1.0) -> str:
    return f"""
authored_by: "테스트 전문가"
approved_by: "테스트 승인자"
origin_channel: EXPERT_AUTHORED
dataset_split: BENCHMARK_HOLDOUT
episodes:
  - episode_id: EP_UP_1
    teacher_prompt: "{prompt}"
    intent: {intent}
    lang: ko
    reviewers: ["검수가", "검수나"]
    agreement_kappa: {kappa}
"""


def test_ktib_upload_dry_run_then_commit(api) -> None:
    """시험지 업로드: dry-run은 저장 안 함, commit은 적재 + KTIB 동결 (§8-2 웹 진입점)."""
    from app.models.episodes import Episode
    client, db = api
    ints = _seed_brain(db)
    yaml_text = _upload_yaml(ints[0], "업로드 검증용 유일 발화 zzq")

    # dry-run: 검증만 — DB 미변경
    r = client.post("/v1/observatory/ktib/upload", json={"yaml_text": yaml_text, "commit": False})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["dry_run"] is True and body["inserted"] == 1
    assert db.query(Episode).filter_by(episode_id="EP_UP_1").first() is None  # 저장 안 됨

    # commit: 실제 적재 + KTIB 발급
    r2 = client.post("/v1/observatory/ktib/upload", json={"yaml_text": yaml_text, "commit": True})
    b2 = r2.json()
    assert b2["ok"] is True and b2["dry_run"] is False
    assert b2["ktib_version"] and b2["eligible_total"] == 1
    assert db.query(Episode).filter_by(episode_id="EP_UP_1").first() is not None


def test_ktib_upload_rejects_unknown_intent(api) -> None:
    client, db = api
    _seed_brain(db)
    yaml_text = _upload_yaml("NOT_A_REAL_INTENT", "미지 의도 발화")
    r = client.post("/v1/observatory/ktib/upload", json={"yaml_text": yaml_text, "commit": True})
    assert r.status_code == 200
    assert r.json()["ok"] is False  # 거부 — 온톨로지에 없는 intent


def test_ktib_upload_rejects_single_reviewer(api) -> None:
    """BENCHMARK는 2인 이상 검수 필수 (§3-3) — 1인이면 거부."""
    client, db = api
    ints = _seed_brain(db)
    yaml_text = f"""
authored_by: "x"
approved_by: "y"
origin_channel: EXPERT_AUTHORED
dataset_split: BENCHMARK_HOLDOUT
episodes:
  - {{episode_id: EP_SOLO, teacher_prompt: "한명검수 발화", intent: {ints[0]}, lang: ko, reviewers: ["혼자"], agreement_kappa: 1.0}}
"""
    r = client.post("/v1/observatory/ktib/upload", json={"yaml_text": yaml_text, "commit": True})
    assert r.json()["ok"] is False


def test_ktib_upload_missing_field_400(api) -> None:
    client, _ = api
    r = client.post("/v1/observatory/ktib/upload",
                    json={"yaml_text": "episodes: []", "commit": False})
    assert r.status_code == 400


def test_ktib_upload_structured_rows(api) -> None:
    """CSV/시트 경로: 구조화 episodes + 작성자/승인자로 등록 (episode_id 자동생성)."""
    from app.models.episodes import Episode
    client, db = api
    ints = _seed_brain(db)
    payload = {
        "commit": True,
        "authored_by": "시트 작성자",
        "approved_by": "시트 승인자",
        "episodes": [
            {"teacher_prompt": "시트 업로드 유일 발화 qpz", "intent": ints[0],
             "reviewers": ["검수가", "검수나"], "agreement_kappa": 1.0},
        ],
    }
    r = client.post("/v1/observatory/ktib/upload", json=payload)
    body = r.json()
    assert body["ok"] is True and body["ktib_version"] and body["eligible_total"] == 1
    # episode_id 자동생성 → 저장됐는지 dedup_hash 기준으로 확인
    assert db.query(Episode).filter_by(dataset_split="BENCHMARK_HOLDOUT").count() == 1


def test_ktib_upload_structured_requires_author(api) -> None:
    client, db = api
    ints = _seed_brain(db)
    r = client.post("/v1/observatory/ktib/upload", json={
        "commit": False, "approved_by": "y",
        "episodes": [{"teacher_prompt": "작성자 없음", "intent": ints[0],
                      "reviewers": ["a", "b"], "agreement_kappa": 1.0}],
    })
    assert r.status_code == 400  # 작성자 미입력
