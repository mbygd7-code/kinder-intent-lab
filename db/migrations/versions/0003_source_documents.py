"""source_documents(원문 저장) + 절대 규칙 7 트리거 백스톱 (§1-S2).

원문은 ALLOW 소스만 저장 가능. 앱 가드(store_raw_document)를 우회한 직접 INSERT/UPDATE도
트리거가 check_violation으로 차단한다 — TRANSFORM_ONLY/PENDING/DENY 소스 원문 저장 금지.

Revision ID: 0003
Revises: 0002
"""
from alembic import op

revision = "0003"
down_revision = "0002"
branch_labels = None
depends_on = None

_UPGRADE = """
CREATE TABLE source_documents (
  doc_id     TEXT PRIMARY KEY,
  source_id  TEXT NOT NULL REFERENCES sources(source_id),
  content    TEXT NOT NULL,
  created_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_source_documents_source ON source_documents(source_id);

CREATE FUNCTION enforce_raw_storage_allow() RETURNS trigger AS $$
BEGIN
  IF (SELECT governance_status FROM sources WHERE source_id = NEW.source_id) <> 'ALLOW' THEN
    RAISE EXCEPTION 'raw storage forbidden: source %% is not ALLOW (rule 7)', NEW.source_id
      USING ERRCODE = 'check_violation';
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_source_documents_allow
  BEFORE INSERT OR UPDATE ON source_documents
  FOR EACH ROW EXECUTE FUNCTION enforce_raw_storage_allow();
"""

_DOWNGRADE = """
DROP TRIGGER IF EXISTS trg_source_documents_allow ON source_documents;
DROP FUNCTION IF EXISTS enforce_raw_storage_allow();
DROP TABLE IF EXISTS source_documents CASCADE;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWNGRADE)
