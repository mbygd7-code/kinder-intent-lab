"""Atlas 확장 큐 — 미매핑 발화 자동 적재 (T2.2, §2-4).

Revision ID: 0007
Revises: 0006
"""
from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None

_UPGRADE = """
CREATE TABLE atlas_expansion_queue (
  queue_id   TEXT PRIMARY KEY,
  utterance  TEXT NOT NULL,
  status     TEXT NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING','CLUSTERED','DISMISSED')),
  source_run TEXT,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_atlas_expansion_status ON atlas_expansion_queue(status);
"""

_DOWNGRADE = "DROP TABLE IF EXISTS atlas_expansion_queue CASCADE;"


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWNGRADE)
