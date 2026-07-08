"""persona_state_versions 레지스트리 — prior 스냅샷 버전 발급·계보 (T2.4, §5-3, replay).

population/teacher prior는 state_version으로 스냅샷된다. 이 테이블이 버전 발급(단조 seq)과
계보(parent_version)를 기록해 Arena replay(arena_runs.persona_state_version)를 지지한다.

Revision ID: 0008
Revises: 0007
"""
from alembic import op

revision = "0008"
down_revision = "0007"
branch_labels = None
depends_on = None

_UPGRADE = """
CREATE TABLE persona_state_versions (
  version        TEXT PRIMARY KEY,
  seq            INTEGER NOT NULL UNIQUE,
  reason         TEXT,
  parent_version TEXT,
  created_at     TIMESTAMPTZ DEFAULT now()
);
"""

_DOWNGRADE = "DROP TABLE IF EXISTS persona_state_versions CASCADE;"


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWNGRADE)
