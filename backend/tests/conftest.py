"""테스트 DB 픽스처.

TEST_DATABASE_URL 또는 DATABASE_URL(레포 루트 .env 지원)의 PostgreSQL 15+
(+pgvector)를 사용한다. DB 픽스처를 쓰는 테스트만 접속을 요구한다.
"""
import os
from pathlib import Path

import pytest
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import NullPool

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")


def _normalize(url: str) -> str:
    """Supabase 등에서 복사한 postgresql:// URL을 psycopg 드라이버로 고정."""
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


@pytest.fixture(scope="session")
def database_url() -> str:
    url = os.environ.get("TEST_DATABASE_URL") or os.environ.get("DATABASE_URL")
    if not url:
        pytest.fail(
            "DATABASE_URL이 없습니다. 레포 루트 .env에 pgvector 지원 "
            "PostgreSQL 15+ 접속 URL을 설정하세요 (.env.example 참고)."
        )
    if "[YOUR-PASSWORD]" in url:
        pytest.fail(".env의 DATABASE_URL에 [YOUR-PASSWORD] 자리 표시자가 남아 있습니다.")
    return _normalize(url)


@pytest.fixture(scope="session")
def migrated_engine(database_url):
    """alembic upgrade head 적용이 끝난 엔진."""
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(REPO_ROOT / "backend" / "alembic.ini"))
    cfg.set_main_option("script_location", str(REPO_ROOT / "db" / "migrations"))
    # ConfigParser 보간이 URL의 %(percent-encoded 비밀번호 등)를 깨지 않도록 이스케이프
    cfg.set_main_option("sqlalchemy.url", database_url.replace("%", "%%"))
    command.upgrade(cfg, "head")

    engine = create_engine(database_url, poolclass=NullPool)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(migrated_engine):
    """외부 트랜잭션 + SAVEPOINT 세션 — 테스트가 commit()해도 DB에 남지 않는다."""
    with migrated_engine.connect() as conn:
        outer = conn.begin()
        session = Session(bind=conn, join_transaction_mode="create_savepoint")
        try:
            yield session
        finally:
            session.close()
            outer.rollback()
