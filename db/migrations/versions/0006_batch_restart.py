"""배치 재시작 멱등 — episodes.dedup_hash 유니크 인덱스 + failed_episodes 격리 큐 (T2.1).

- dedup_hash 유니크(null 제외): 재시작 시 같은 슬롯 에피소드 중복 생성 물리 차단.
- failed_episodes: 실패 에피소드 격리 큐(한 에피소드 실패가 배치를 중단시키지 않음).

Revision ID: 0006
Revises: 0005
"""
from alembic import op

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None

_UPGRADE = """
CREATE UNIQUE INDEX idx_episodes_dedup_hash ON episodes(dedup_hash)
  WHERE dedup_hash IS NOT NULL;

CREATE TABLE failed_episodes (
  fail_id    TEXT PRIMARY KEY,
  run_id     TEXT NOT NULL,
  slot_index INTEGER NOT NULL,
  stage      TEXT,
  error      TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_failed_episodes_run ON failed_episodes(run_id);
"""

_DOWNGRADE = """
DROP TABLE IF EXISTS failed_episodes CASCADE;
DROP INDEX IF EXISTS idx_episodes_dedup_hash;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWNGRADE)
