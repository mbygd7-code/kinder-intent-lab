"""채점(Arena) 웹 트리거 — 운영자 PIN 게이트 + 백그라운드 실행 + 상태 폴링.

경로는 scripts/run_arena.py의 base 채점(candidate 없음)과 동일하다:
latest_ktib → run_arena → reflect_arena_run(promoted=False) → commit.
brightness는 여기서도 reflect(Arena 반영 경로)만 만진다 — 절대 규칙 3 우회 없음.

가드:
- PIN(기본 2341, env ARENA_PIN로 교체 가능) — 보안장치가 아니라 **오클릭 방지 자물쇠**다.
  실 배포에서 바꾸려면 서버 env에 ARENA_PIN을 설정한다.
- LLM_PROVIDER가 mock이면 409 — 가짜 응답으로 매긴 점수는 무의미하고, arena_runs 기록을
  영구 오염시킨다(정직성). 실 provider에서만 채점한다.
- 동시 실행 1개(모듈 락) — 채점은 분 단위 작업이라 중복 실행을 막는다.
"""
from __future__ import annotations

import hmac
import os
import threading
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.arena.ktib import latest_ktib
from app.arena.reflect import reflect_arena_run
from app.arena.runner import run_arena
from app.brain.version_gate import current_base, current_brain_version
from app.core.config import get_config
from app.core.db import get_session, open_session
from app.llm.base import EmbeddingRequest
from app.llm.client import get_embedding_client, get_llm_client
from app.models.arena import RUN_TYPE_BRAIN, ArenaRun

router = APIRouter(prefix="/v1/observatory", tags=["observatory"])

_MOCK_PROVIDERS = ("mock", "synthetic", "synth")

# 실행 상태(프로세스 로컬) — 완료된 run 자체는 DB(arena_runs)가 진실이고 이건 진행 표시용이다.
_state: dict = {"running": False, "started_at": None, "error": None}
_lock = threading.Lock()


def _pin() -> str:
    return os.environ.get("ARENA_PIN", "2341")


def _embed_fn():
    client = get_embedding_client()
    model = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
    return lambda texts: client.embed(EmbeddingRequest(inputs=texts, model=model)).vectors


def _execute() -> None:
    """백그라운드 채점 잡 — scripts/run_arena.py base 경로와 동일. 실패는 상태로 보고한다."""
    session = open_session()
    try:
        config = get_config()
        ktib = latest_ktib(session)
        if ktib is None:
            raise RuntimeError("동결된 시험지(ktib_version)가 없어요 — 문항 등록이 먼저예요")
        base = current_base(session)
        model_version = base.version if base else "seed-v0"
        result = run_arena(
            session, get_llm_client(), _embed_fn(), config,
            model_version=model_version, ktib=ktib,
        )
        reflect_arena_run(session, result.run, config, promoted=False)
        session.commit()
        with _lock:
            _state.update(running=False, error=None)
    except Exception as exc:  # 배경 잡 — 삼키지 않고 상태로 정직하게 노출한다
        session.rollback()
        with _lock:
            _state.update(running=False, error=f"{type(exc).__name__}: {exc}")
    finally:
        session.close()


class ArenaRunIn(BaseModel):
    pin: str


class ArenaStartOut(BaseModel):
    started: bool
    message: str


class LastRunOut(BaseModel):
    run_id: str
    accuracy: float | None
    item_count: int | None
    created_at: datetime | None


class ArenaStatusOut(BaseModel):
    running: bool
    started_at: str | None
    error: str | None
    last_run: LastRunOut | None  # DB 원천 — 현행 뇌의 최신 brain run


@router.post("/arena/run", response_model=ArenaStartOut, status_code=202)
def start_arena_run(payload: ArenaRunIn, background: BackgroundTasks) -> ArenaStartOut:
    if not hmac.compare_digest(payload.pin, _pin()):
        raise HTTPException(status_code=401, detail="비밀번호가 달라요")
    provider = (os.environ.get("LLM_PROVIDER") or "mock").lower()
    if provider in _MOCK_PROVIDERS:
        raise HTTPException(
            status_code=409,
            detail="LLM_PROVIDER가 mock이라 채점하지 않아요 — 가짜 응답으로 매긴 점수는 "
                   "무의미해서 기록을 오염시켜요. 서버 .env에 실 provider를 설정하세요.",
        )
    with _lock:
        if _state["running"]:
            raise HTTPException(status_code=409, detail="이미 채점이 실행 중이에요")
        _state.update(
            running=True, started_at=datetime.now(UTC).isoformat(), error=None
        )
    background.add_task(_execute)
    return ArenaStartOut(
        started=True,
        message="채점을 시작했어요 — 문항 수에 따라 몇 분 걸려요. 끝나면 점수가 바로 반영돼요.",
    )


@router.get("/arena/status", response_model=ArenaStatusOut)
def arena_status(session: Session = Depends(get_session)) -> ArenaStatusOut:
    run = session.scalar(
        select(ArenaRun)
        .where(
            ArenaRun.run_type == RUN_TYPE_BRAIN,
            ArenaRun.model_version == current_brain_version(session),
        )
        .order_by(ArenaRun.created_at.desc())
        .limit(1)
    )
    last = None
    if run is not None:
        metrics = run.metrics or {}
        last = LastRunOut(
            run_id=run.run_id,
            accuracy=metrics.get("first_intent_accuracy"),
            item_count=metrics.get("item_count"),
            created_at=run.created_at,
        )
    with _lock:
        snapshot = dict(_state)
    return ArenaStatusOut(
        running=snapshot["running"],
        started_at=snapshot["started_at"],
        error=snapshot["error"],
        last_run=last,
    )
