"""초기 스키마 — db/migrations/001_init.sql을 그대로 반영 (절대 규칙 2 CHECK 포함).

Revision ID: 0001
Revises:
"""
from pathlib import Path

from alembic import op

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None

SQL_FILE = Path(__file__).resolve().parents[1] / "001_init.sql"

# 001_init.sql의 테이블들 — downgrade용 (FK 역순)
TABLES = [
    "governance_events",
    "ontology_versions",
    "arena_runs",
    "brain_versions",
    "gym_sessions",
    "challenge_packs",
    "teacher_priors",
    "population_priors",
    "persona_clusters",
    "confusion_edges",
    "brain_nodes",
    "evidence",
    "episodes",
    "canonical_scenarios",
    "atlas_entries",
    "situation_frames",
    "sources",
]


def upgrade() -> None:
    # op.execute()는 문자열을 text()로 감싸 :name 바인드 파라미터를 파싱하므로
    # (예: JSON 리터럴 '{"a":1}'이 팬텀 파라미터가 됨) 드라이버 레벨로 실행한다.
    op.get_bind().exec_driver_sql(SQL_FILE.read_text(encoding="utf-8"))


def downgrade() -> None:
    for table in TABLES:
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")
