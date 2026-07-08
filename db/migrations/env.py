"""Alembic 환경. URL 우선순위: alembic.ini sqlalchemy.url(conftest가 주입) > DATABASE_URL.

CLI(`alembic upgrade head`)는 항상 DATABASE_URL을 대상으로 한다 —
TEST_DATABASE_URL은 여기서 읽지 않는다(테스트는 conftest가 URL을 직접 주입).
"""
import os
from pathlib import Path

from alembic import context
from dotenv import load_dotenv
from sqlalchemy import create_engine, pool

load_dotenv(Path(__file__).resolve().parents[2] / ".env")


def _url() -> str:
    url = (
        context.config.get_main_option("sqlalchemy.url")
        or os.environ.get("DATABASE_URL")
    )
    if not url:
        raise RuntimeError(
            "DB URL이 없습니다 — DATABASE_URL 환경 변수 또는 alembic.ini sqlalchemy.url 필요"
        )
    if url.startswith("postgresql://"):  # psycopg 드라이버로 고정
        url = url.replace("postgresql://", "postgresql+psycopg://", 1)
    return url


def run_migrations_offline() -> None:
    context.configure(url=_url(), literal_binds=True)
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    engine = create_engine(_url(), poolclass=pool.NullPool)
    with engine.connect() as connection:
        context.configure(connection=connection)
        with context.begin_transaction():
            context.run_migrations()
    engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
