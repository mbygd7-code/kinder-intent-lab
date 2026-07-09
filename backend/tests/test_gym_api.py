"""T3.7 API AC: POST /v1/gym/session → submit → evidence 적재 (§8-1, Phase 3 게이트 클릭스루).

- session 열기: origin+mode → pack + items(온톨로지 발화)
- submit: 트레이너 응답 → evidence 생성 리포트
- Correction Drill submit → HUMAN_CORRECTION 카운트
- 없는 세션 submit → 404
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.db import get_session
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.main import app
from app.models.brain import Exemplar
from app.models.episodes import Episode, Evidence


@pytest.fixture(autouse=True)
def _empty_bank(db_session):
    """전역 evidence 카운트 단언은 빈 뱅크 전제 — 실DB gym 산출에 면역(세이브포인트, 롤백)."""
    db_session.execute(delete(Evidence))
    db_session.execute(delete(Exemplar))
    db_session.execute(delete(Episode))
    db_session.flush()


@pytest.fixture()
def api(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        yield client, db_session
    app.dependency_overrides.clear()


def _real_intent(idx=0):
    return [i.intent_id for i in load_ontology().intents if i.domain][idx]


def _open(client, mode, node):
    return client.post("/v1/gym/session", json={
        "trainer_ref": "TR_API", "mode": mode,
        "origin": {
            "node": node, "diagnosis": ["CONFUSION_HIGH"], "target_confusion": _real_intent(1),
        },
    })


def test_open_session_returns_pack_and_items(api) -> None:
    client, _ = api
    r = _open(client, "guess_my_intent", _real_intent())
    assert r.status_code == 200
    body = r.json()
    assert body["session_id"].startswith("GS_") and body["pack_id"].startswith("CP_")
    assert len(body["items"]) >= 1
    it = body["items"][0]
    assert it["utterance"] and _real_intent() in it["candidate_intents"]


def test_submit_creates_evidence(api) -> None:
    client, db = api
    node = _real_intent()
    body = _open(client, "guess_my_intent", node).json()
    sid, items = body["session_id"], body["items"]
    r = client.post(f"/v1/gym/session/{sid}/submit", json={
        "results": [{"item_id": items[0]["item_id"], "chosen_intent": node, "recovery_turns": 0}],
    })
    assert r.status_code == 200
    rep = r.json()
    assert rep["evidence_created"] == 1 and rep["episodes_created"] == 1
    assert rep["by_type"]["HUMAN_CONFIRMATION"] == 1
    ev = db.scalars(select(Evidence)).all()
    assert len(ev) == 1 and ev[0].actor_type == "TEACHER_TRAINER" and ev[0].adversarial is False


def test_correction_drill_submit_human_correction(api) -> None:
    client, _ = api
    node, wrong = _real_intent(), _real_intent(1)
    body = _open(client, "correction_drill", node).json()
    items = body["items"]
    r = client.post(f"/v1/gym/session/{body['session_id']}/submit", json={
        "results": [{"item_id": items[0]["item_id"], "chosen_intent": node,
                     "brain_guess": wrong, "recovery_turns": 3}],
    })
    assert r.json()["by_type"] == {"HUMAN_CORRECTION": 1}


def test_submit_unknown_session_404(api) -> None:
    client, _ = api
    r = client.post("/v1/gym/session/GS_nope/submit", json={"results": []})
    assert r.status_code == 404


def test_open_session_no_items_422(api) -> None:
    """온톨로지 밖 노드(UNKNOWN)는 훈련 아이템을 못 만든다 → 422 (지어내지 않음)."""
    client, _ = api
    r = client.post("/v1/gym/session", json={
        "trainer_ref": "TR_API", "mode": "guess_my_intent",
        "origin": {"node": UNKNOWN_INTENT_ID},
    })
    assert r.status_code == 422
