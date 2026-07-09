"""DB 세션 팩토리 + FastAPI 의존성 (프로덕션 경로).

엔진/세션 팩토리는 지연 생성(lru_cache) — import 시점엔 DATABASE_URL이 없어도 되고(mock 오프라인
환경), 첫 요청에서만 접속한다. 테스트는 get_session을 savepoint 세션으로 override한다.
"""
from __future__ import annotations

import os
import threading
from collections.abc import Iterator
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

_REPO_ROOT = Path(__file__).resolve().parents[3]


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        # dev 서버(uvicorn)가 셸 env 없이 떠도 레포 루트 .env를 읽는다 (conftest와 동일 규칙)
        from dotenv import load_dotenv

        load_dotenv(_REPO_ROOT / ".env")
        url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL이 설정되지 않았습니다 (.env 참고)")
    # Supabase 등에서 복사한 postgresql:// URL을 psycopg 드라이버로 고정 (conftest와 동일 규칙)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


# 수동 싱글턴 + Lock — lru_cache는 계산 중 잠그지 않아 첫 동시 요청 N개가 엔진(커넥션풀)을
# N개 만들 수 있다(승자 외에는 dispose되지 않은 채 버려짐). 이중 검사로 정확히 1회 생성.
_init_lock = threading.RLock()  # 재진입: factory 락 안에서 _engine()이 같은 락을 잡는다
_engine_instance: Engine | None = None
_factory_instance: sessionmaker[Session] | None = None


def _engine() -> Engine:
    global _engine_instance
    if _engine_instance is None:
        with _init_lock:
            if _engine_instance is None:
                _engine_instance = create_engine(_database_url(), pool_pre_ping=True)
    return _engine_instance


def _session_factory() -> sessionmaker[Session]:
    global _factory_instance
    if _factory_instance is None:
        with _init_lock:
            if _factory_instance is None:
                _factory_instance = sessionmaker(bind=_engine(), expire_on_commit=False)
    return _factory_instance


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
