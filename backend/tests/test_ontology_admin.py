"""의도 목록·표시 수정·변경 제안 AC — /v1/ontology (2026-07-17).

계층 분리 불변식: 표시 수정(PIN)은 즉시 반영되지만 온톨로지 버전·의미(YAML)는 불변.
의미·구조 변경은 대기열로만 — 승인해도 '반영 예약'일 뿐 온톨로지는 안 바뀐다.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.db import get_session
from app.core.ontology import load_ontology
from app.main import app
from app.models.governance import GovernanceEvent
from app.models.intent_admin import IntentChangeRequest, IntentDisplay

PIN = "2341"


@pytest.fixture(autouse=True)
def _clean(db_session, monkeypatch):
    monkeypatch.delenv("ONTOLOGY_PIN", raising=False)
    monkeypatch.delenv("ARENA_PIN", raising=False)
    db_session.execute(delete(IntentDisplay))
    db_session.execute(delete(IntentChangeRequest))
    db_session.flush()


@pytest.fixture()
def api(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        yield client, db_session
    app.dependency_overrides.clear()


def test_catalog_lists_all_intents_with_definition(api) -> None:
    client, _ = api
    body = client.get("/v1/ontology/intents").json()
    assert body["total"] == len(
        [i for i in load_ontology().intents if i.intent_id != "UNKNOWN"]
    )
    first = body["items"][0]
    assert set(first.keys()) == {
        "intent_id", "domain", "definition", "example_count", "name_ko", "description_ko",
    }
    assert first["definition"]  # 의미 계층이 그대로 보인다(읽기 전용)


def test_display_edit_needs_pin_and_leaves_ontology_untouched(api) -> None:
    """★ PIN 확인 후 즉시 수정 — 그러나 온톨로지 버전·정의(YAML)는 불변(replay 축 보존)."""
    client, db = api
    intent = load_ontology().intents[0].intent_id
    version_before = load_ontology().version

    r = client.put(f"/v1/ontology/intents/{intent}/display",
                   json={"pin": "0000", "edited_by": "명배영", "name_ko": "새 이름"})
    assert r.status_code == 401  # 오클릭 방지 자물쇠

    r2 = client.put(f"/v1/ontology/intents/{intent}/display",
                    json={"pin": PIN, "edited_by": "명배영", "name_ko": "새 이름",
                          "description_ko": "화면용 쉬운 설명"})
    assert r2.status_code == 200
    assert r2.json()["name_ko"] == "새 이름"

    # 목록에 병합돼 보인다
    items = client.get("/v1/ontology/intents").json()["items"]
    mine = next(i for i in items if i["intent_id"] == intent)
    assert mine["name_ko"] == "새 이름" and mine["description_ko"] == "화면용 쉬운 설명"

    # 불변식: 버전 그대로, 거버넌스 기록 존재
    assert load_ontology().version == version_before
    ev = db.scalars(select(GovernanceEvent).where(
        GovernanceEvent.event_type == "INTENT_DISPLAY_EDIT")).all()
    assert len(ev) == 1 and ev[-1].payload["intent_id"] == intent

    assert client.put("/v1/ontology/intents/NOT_REAL/display",
                      json={"pin": PIN, "edited_by": "명", "name_ko": "x"}).status_code == 404


def test_change_request_queue_and_pin_decision(api) -> None:
    """제안은 누구나 접수(PENDING) — 판정은 PIN. 승인은 '반영 예약'일 뿐 온톨로지 불변."""
    client, _ = api
    intent = load_ontology().intents[0].intent_id
    version_before = load_ontology().version

    r = client.post("/v1/ontology/change-requests", json={
        "kind": "DEFINITION", "intent_id": intent,
        "proposal": "정의가 관찰 기록과 헷갈려요 — 경계 문구를 명확히", "proposed_by": "조선생",
    })
    assert r.status_code == 200
    rid = r.json()["request_id"]
    pending = client.get("/v1/ontology/change-requests", params={"status": "PENDING"}).json()
    assert any(x["request_id"] == rid for x in pending["requests"])

    assert client.post(f"/v1/ontology/change-requests/{rid}/decide",
                       json={"pin": "0000", "decision": "approve",
                             "decided_by": "운영자"}).status_code == 401

    ok = client.post(f"/v1/ontology/change-requests/{rid}/decide",
                     json={"pin": PIN, "decision": "approve", "decided_by": "운영자"})
    assert ok.status_code == 200
    assert ok.json()["request"]["status"] == "APPROVED"
    assert "반영 예약" in ok.json()["message"]  # 승인 ≠ 자동 반영(정직)
    assert load_ontology().version == version_before

    # 재판정 금지
    assert client.post(f"/v1/ontology/change-requests/{rid}/decide",
                       json={"pin": PIN, "decision": "reject",
                             "decided_by": "운영자"}).status_code == 409


def test_bulk_display_applies_known_skips_unknown(api) -> None:
    """★ CSV 일괄: 이름·설명은 즉시 반영, 목록에 없는 id는 건너뜀. 버전 불변, PIN 필수."""
    client, _ = api
    real = [i.intent_id for i in load_ontology().intents if i.intent_id != "UNKNOWN"]
    version_before = load_ontology().version
    rows = [
        {"intent_id": real[0], "name_ko": "일괄 새이름", "description_ko": "일괄 새설명"},
        {"intent_id": real[1], "name_ko": "이름만 변경"},  # 설명 필드 생략 → 설명 미변경
        {"intent_id": "NOT_REAL_INTENT", "name_ko": "무시될 것"},
    ]

    assert client.post("/v1/ontology/intents/display/bulk",
                       json={"pin": "0000", "edited_by": "명배영", "rows": rows}).status_code == 401

    r = client.post("/v1/ontology/intents/display/bulk",
                    json={"pin": PIN, "edited_by": "명배영", "rows": rows})
    assert r.status_code == 200
    body = r.json()
    assert body["applied"] == 2
    assert [s["intent_id"] for s in body["skipped"]] == ["NOT_REAL_INTENT"]

    items = {i["intent_id"]: i for i in client.get("/v1/ontology/intents").json()["items"]}
    assert items[real[0]]["name_ko"] == "일괄 새이름"
    assert items[real[0]]["description_ko"] == "일괄 새설명"
    assert items[real[1]]["name_ko"] == "이름만 변경"
    assert items[real[1]]["description_ko"] is None  # 생략한 필드는 그대로
    assert load_ontology().version == version_before  # 의미·버전 불변


def test_bulk_display_empty_clears_override(api) -> None:
    """빈 문자열은 오버레이 해제(원래 값으로 복귀) — 다운로드→편집→업로드 왕복 일관성."""
    client, _ = api
    intent = load_ontology().intents[0].intent_id
    client.post("/v1/ontology/intents/display/bulk",
                json={"pin": PIN, "edited_by": "명", "rows": [
                    {"intent_id": intent, "name_ko": "임시이름"}]})
    client.post("/v1/ontology/intents/display/bulk",
                json={"pin": PIN, "edited_by": "명", "rows": [
                    {"intent_id": intent, "name_ko": ""}]})  # 해제
    items = {i["intent_id"]: i for i in client.get("/v1/ontology/intents").json()["items"]}
    assert items[intent]["name_ko"] is None


def test_blank_proposal_rejected(api) -> None:
    client, _ = api
    r = client.post("/v1/ontology/change-requests",
                    json={"kind": "OTHER", "proposal": "  ", "proposed_by": "x"})
    assert r.status_code == 422
