"""foundry_work_queue — A형(Data Coverage) 강화 주문 큐 (T4.2, §6-1).

Observatory 클릭 진단이 COVERAGE_LOW면 Challenge Pack이 이 큐로 발행된다 — 사람 세션 없이
Foundry(S5~S10)에 해당 노드 시나리오 생성을 지시. 상태: PENDING→IN_PROGRESS→DONE|DISMISSED.

Revision ID: 0012
Revises: 0011
"""
from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None

_UPGRADE = """
CREATE TABLE foundry_work_queue (
  order_id        TEXT PRIMARY KEY,
  intent_id       TEXT NOT NULL,
  region          TEXT,
  order_type      TEXT NOT NULL DEFAULT 'SCENARIO_COVERAGE'
    CHECK (order_type IN ('SCENARIO_COVERAGE')),
  status          TEXT NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING','IN_PROGRESS','DONE','DISMISSED')),
  requested_items INTEGER NOT NULL,
  strategy        JSONB,
  diagnosis       JSONB,
  pack_id         TEXT REFERENCES challenge_packs(pack_id),
  payload         JSONB,
  created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_foundry_work_status ON foundry_work_queue(status);
"""

_DOWNGRADE = "DROP TABLE IF EXISTS foundry_work_queue CASCADE;"


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWNGRADE)
