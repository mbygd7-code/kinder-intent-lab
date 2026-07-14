"""채점 웹 트리거 AC — POST /arena/run (PIN 게이트) + GET /arena/status.

정직성 AC: mock provider로는 채점을 시작할 수 없다(가짜 점수로 arena_runs 오염 금지).
실행 자체(run_arena)는 LLM 과금 작업이라 여기선 스텁으로 대체 — 게이트·상태만 검증한다.
"""
import uuid
from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.api import arena_ops
from app.core.db import get_session
from app.main import app
from app.models.arena import (
    NO_PERSONA_STATE,
    RUN_TYPE_BRAIN,
    ArenaRun,
    KtibItem,
    KtibVersion,
)
from app.models.brain import BrainVersion

PIN = "2341"  # 기본 PIN — env ARENA_PIN 미설정 시의 계약(오클릭 방지 자물쇠)


@pytest.fixture(autouse=True)
def _reset(db_session, monkeypatch):
    """모듈 상태·env를 테스트마다 초기화 + 관련 테이블 선삭제(FK: run→ktib)."""
    with arena_ops._lock:
        arena_ops._state.update(running=False, started_at=None, error=None)
    monkeypatch.delenv("ARENA_PIN", raising=False)
    for model in (ArenaRun, KtibItem, KtibVersion, BrainVersion):
        db_session.execute(delete(model))
    db_session.flush()


@pytest.fixture()
def api(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        yield client, db_session
    app.dependency_overrides.clear()


def _freeze_ktib(db) -> None:
    """사전 판정(동결 시험지 존재) 통과용 최소 ktib — start 계약이 이제 이를 요구한다."""
    db.add(KtibVersion(ktib_version=f"ktib-{uuid.uuid4().hex[:6]}", seq=1,
                       extractor_versions={}, episode_count=1,
                       content_hash=f"h-{uuid.uuid4().hex}"))
    db.flush()


def test_wrong_pin_is_rejected(api, monkeypatch) -> None:
    client, _ = api
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    res = client.post("/v1/observatory/arena/run", json={"pin": "0000"})
    assert res.status_code == 401
    assert "비밀번호" in res.json()["detail"]


def test_mock_provider_cannot_score(api, monkeypatch) -> None:
    """가짜 응답으로 매긴 점수는 기록 오염 — PIN이 맞아도 시작하지 않는다."""
    client, _ = api
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    res = client.post("/v1/observatory/arena/run", json={"pin": PIN})
    assert res.status_code == 409
    assert "mock" in res.json()["detail"]


# --- 사전 판정(runnable/blocked_reason) — 버튼이 미리 회색+안내로 서게 한다 ---


def test_status_blocked_when_mock_provider(api, monkeypatch) -> None:
    client, db = api
    monkeypatch.setenv("LLM_PROVIDER", "mock")
    _freeze_ktib(db)
    status = client.get("/v1/observatory/arena/status").json()
    assert status["runnable"] is False
    assert "mock" in status["blocked_reason"]
    # 우회 POST도 같은 문구의 409 (방어 이중화)
    res = client.post("/v1/observatory/arena/run", json={"pin": PIN})
    assert res.status_code == 409 and res.json()["detail"] == status["blocked_reason"]


def test_status_blocked_without_frozen_ktib(api, monkeypatch) -> None:
    client, _ = api
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    status = client.get("/v1/observatory/arena/status").json()
    assert status["runnable"] is False
    assert "시험지" in status["blocked_reason"]
    res = client.post("/v1/observatory/arena/run", json={"pin": PIN})
    assert res.status_code == 409 and "시험지" in res.json()["detail"]


def test_status_runnable_with_real_provider_and_ktib(api, monkeypatch) -> None:
    client, db = api
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    _freeze_ktib(db)
    status = client.get("/v1/observatory/arena/status").json()
    assert status["runnable"] is True and status["blocked_reason"] is None


def _brain_run(db, *, ktib_version: str, hours_ago: int = 1) -> None:
    """현행 뇌(seed-v0)의 완료된 채점 run — '새 유입' 판정의 기준 시각."""
    from datetime import timedelta

    db.add(ArenaRun(
        run_id=f"AR_{uuid.uuid4().hex[:8]}", model_version="seed-v0",
        ontology_version="onto-test", persona_state_version=NO_PERSONA_STATE,
        extractor_versions={}, ktib_version=ktib_version, run_type=RUN_TYPE_BRAIN,
        metrics={"first_intent_accuracy": 0.0, "item_count": 1},
        created_at=datetime.now(UTC) - timedelta(hours=hours_ago),
    ))
    db.flush()


def test_blocked_when_nothing_new_since_last_run(api, monkeypatch) -> None:
    """유입 0 재채점은 같은 점수에 비용만 낸다(실측) — 회색+안내로 막는다."""
    from app.models.arena import KtibVersion as KV

    client, db = api
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    db.add(KV(ktib_version="ktib-same", seq=1, extractor_versions={},
              episode_count=1, content_hash=f"h-{uuid.uuid4().hex}"))
    db.flush()
    _brain_run(db, ktib_version="ktib-same")

    status = client.get("/v1/observatory/arena/status").json()
    assert status["runnable"] is False and "새로 배운 것이 없어요" in status["blocked_reason"]
    res = client.post("/v1/observatory/arena/run", json={"pin": PIN})
    assert res.status_code == 409 and res.json()["detail"] == status["blocked_reason"]


def test_new_training_data_reenables_grading(api, monkeypatch) -> None:
    from app.models.arena import KtibVersion as KV
    from app.models.episodes import Episode

    client, db = api
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    db.add(KV(ktib_version="ktib-same", seq=1, extractor_versions={},
              episode_count=1, content_hash=f"h-{uuid.uuid4().hex}"))
    db.flush()
    _brain_run(db, ktib_version="ktib-same")
    # run 이후 새 공부 데이터 1건 — 다시 잴 이유가 생겼다
    db.add(Episode(
        episode_id=f"EP_new_{uuid.uuid4().hex[:8]}", ontology_version="onto-test",
        lang="ko", dataset_split="TRAIN", origin_channel="GYM_HUMAN",
        episode_creator_type="GYM_SESSION", primary_subject_type="TEACHER",
        teacher_prompt="새로 배운 발화", label_distribution={},
    ))
    db.flush()

    status = client.get("/v1/observatory/arena/status").json()
    assert status["runnable"] is True and status["blocked_reason"] is None


def test_new_frozen_exam_reenables_grading(api, monkeypatch) -> None:
    """시험지가 새로 동결되면(문항 추가) 유입 0이어도 다시 잴 가치가 있다."""
    from app.models.arena import KtibVersion as KV

    client, db = api
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    db.add(KV(ktib_version="ktib-old", seq=1, extractor_versions={},
              episode_count=1, content_hash=f"h-{uuid.uuid4().hex}"))
    db.flush()
    _brain_run(db, ktib_version="ktib-old")
    db.add(KV(ktib_version="ktib-new", seq=2, extractor_versions={},
              episode_count=2, content_hash=f"h-{uuid.uuid4().hex}"))
    db.flush()

    status = client.get("/v1/observatory/arena/status").json()
    assert status["runnable"] is True and status["blocked_reason"] is None


def test_start_runs_job_and_clears_state(api, monkeypatch) -> None:
    client, db = api
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    _freeze_ktib(db)  # 사전 판정: 동결 시험지 필요
    calls: list[str] = []

    def fake_execute() -> None:  # 실 채점 대신 — 완료 상태 전이만 재현
        calls.append("ran")
        with arena_ops._lock:
            arena_ops._state.update(running=False, error=None)

    monkeypatch.setattr(arena_ops, "_execute", fake_execute)
    res = client.post("/v1/observatory/arena/run", json={"pin": PIN})
    assert res.status_code == 202 and res.json()["started"] is True
    assert calls == ["ran"]  # TestClient는 응답 후 백그라운드 태스크를 동기 실행한다

    status = client.get("/v1/observatory/arena/status").json()
    assert status["running"] is False and status["error"] is None


def test_double_start_conflicts(api, monkeypatch) -> None:
    client, db = api
    monkeypatch.setenv("LLM_PROVIDER", "anthropic")
    _freeze_ktib(db)  # 사전 판정 통과 후 '이미 실행 중' 가드가 잡혀야 한다
    with arena_ops._lock:
        arena_ops._state.update(running=True, started_at=datetime.now(UTC).isoformat())
    res = client.post("/v1/observatory/arena/run", json={"pin": PIN})
    assert res.status_code == 409
    assert "이미" in res.json()["detail"]


def test_status_reports_last_brain_run_from_db(api) -> None:
    """진행 상태는 프로세스 로컬이지만, 완료된 점수는 DB(arena_runs)가 진실이다."""
    client, db = api
    db.add(KtibVersion(ktib_version="ktib-t1", seq=1, extractor_versions={},
                       episode_count=1, content_hash=f"h-{uuid.uuid4().hex}"))
    db.flush()
    db.add(ArenaRun(
        run_id="AR_OPS", model_version="seed-v0", ontology_version="onto-test",
        persona_state_version=NO_PERSONA_STATE, extractor_versions={},
        ktib_version="ktib-t1", run_type=RUN_TYPE_BRAIN,
        metrics={"first_intent_accuracy": 0.62, "item_count": 185},
    ))
    db.flush()

    status = client.get("/v1/observatory/arena/status").json()
    assert status["last_run"]["run_id"] == "AR_OPS"
    assert status["last_run"]["accuracy"] == 0.62
    assert status["last_run"]["item_count"] == 185
