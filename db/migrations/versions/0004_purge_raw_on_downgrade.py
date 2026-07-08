"""ALLOW→비ALLOW 재판정 시 원문 purge 트리거 (절대 규칙 7 물리 백스톱).

0003의 트리거는 source_documents INSERT/UPDATE만 막아, 소스를 ALLOW로 만들어 원문을 저장한 뒤
TRANSFORM_ONLY/DENY로 재판정하면 원문이 잔존하는 구멍이 있었다. 이 트리거는 sources의
governance_status가 비ALLOW로 바뀌면 해당 소스의 원문을 삭제한다 — 앱 우회(직접 SQL)까지 방어.

Revision ID: 0004
Revises: 0003
"""
from alembic import op

revision = "0004"
down_revision = "0003"
branch_labels = None
depends_on = None

_UPGRADE = """
CREATE FUNCTION purge_raw_on_downgrade() RETURNS trigger AS $$
BEGIN
  DELETE FROM source_documents WHERE source_id = NEW.source_id;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sources_purge_raw
  AFTER UPDATE OF governance_status ON sources
  FOR EACH ROW
  WHEN (NEW.governance_status <> 'ALLOW')
  EXECUTE FUNCTION purge_raw_on_downgrade();
"""

_DOWNGRADE = """
DROP TRIGGER IF EXISTS trg_sources_purge_raw ON sources;
DROP FUNCTION IF EXISTS purge_raw_on_downgrade();
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWNGRADE)
