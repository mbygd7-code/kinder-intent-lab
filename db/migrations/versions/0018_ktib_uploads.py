"""ktib_uploads — 시험지 업로드 이력(기록 + 원문 문서 보관).

교사가 시험지를 등록(commit)할 때마다 한 줄을 남긴다: 누가·언제·몇 문항·어떤 버전으로
등록됐는지 + **올린 원문 그대로**(source_document). 나중에 목록에서 보고, 그 문서를 다시
열어 확인할 수 있게 하는 감사·회수용 표다.

governance_events(승인 감사)와 분리한다 — 이건 사람이 열람하는 '업로드한 문서 보관함'이다.
episodes/tier/label/brightness는 여기 없다(자료 삭제해도 채점 축은 불변).

추가만 하는 마이그레이션 — 기존 표·데이터 무변경. 새 표이므로 RLS를 켠다(마이그레이션 0016 규칙,
tests/test_rls.py가 강제). downgrade는 표 DROP.

Revision ID: 0018
Revises: 0017
"""
from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None

_UPGRADE = """
CREATE TABLE ktib_uploads (
  upload_id         TEXT PRIMARY KEY,
  created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
  authored_by       TEXT NOT NULL,
  approved_by       TEXT NOT NULL,
  reviewers         JSONB NOT NULL DEFAULT '[]'::jsonb,
  origin_channel    TEXT NOT NULL,
  dataset_split     TEXT NOT NULL,
  inserted          INTEGER NOT NULL,
  skipped_duplicate INTEGER NOT NULL DEFAULT 0,
  agreement_rate    DOUBLE PRECISION,
  agreement_kappa   DOUBLE PRECISION,
  ktib_version      TEXT,
  eligible_total    INTEGER NOT NULL DEFAULT 0,
  source_document   TEXT
);
CREATE INDEX idx_ktib_uploads_created ON ktib_uploads(created_at DESC);

-- 새 public 테이블은 RLS ON(무정책=전부 거부) — 소유자(백엔드 직결)만 접근(§ 마이그레이션 0016).
ALTER TABLE ktib_uploads ENABLE ROW LEVEL SECURITY;
"""

_DOWNGRADE = "DROP TABLE IF EXISTS ktib_uploads CASCADE;"


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWNGRADE)
