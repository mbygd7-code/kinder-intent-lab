"""T1.1 AC: uvicorn 기동 후 GET /healthz 200.

TestClient로 앱 레벨 검증. 실제 uvicorn 기동 검증은 티켓 완료 절차에서 수행.
"""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_healthz_returns_200() -> None:
    resp = client.get("/healthz")
    assert resp.status_code == 200


def test_healthz_body_reports_ok() -> None:
    assert client.get("/healthz").json() == {"status": "ok"}
