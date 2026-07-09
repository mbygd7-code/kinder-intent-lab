"""DB 세션 팩토리 + FastAPI 의존성 (프로덕션 경로).

엔진/세션 팩토리는 지연 생성(lru_cache) — import 시점엔 DATABASE_URL이 없어도 되고(mock 오프라인
환경), 첫 요청에서만 접속한다. 테스트는 get_session을 savepoint 세션으로 override한다.
"""
from __future__ import annotations

import os
from collections.abc import Iterator
from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL이 설정되지 않았습니다 (.env 참고)")
    # Supabase 등에서 복사한 postgresql:// URL을 psycopg 드라이버로 고정 (conftest와 동일 규칙)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@lru_cache(maxsize=1)
def _engine() -> Engine:
    return create_engine(_database_url(), pool_pre_ping=True)


@lru_cache(maxsize=1)
def _session_factory() -> sessionmaker[Session]:
    return sessionmaker(bind=_engine(), expire_on_commit=False)


def get_session() -> Iterator[Session]:
    """요청 스코프 세션. 성공 시 commit(inference_log 등 영속), 예외 시 rollback, 항상 close."""
    session = _session_factory()()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
