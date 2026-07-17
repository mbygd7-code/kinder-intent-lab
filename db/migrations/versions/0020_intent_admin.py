"""intent_display + intent_change_requests — 의도 목록의 표시 수정·변경 제안 (§5-9 운영 보조).

- intent_display: **표시 계층 오버레이**(한글 이름·화면 설명). 온톨로지 YAML(의미 계층)과
  ontology_version은 절대 건드리지 않는다 — 표시를 고칠 때마다 replay 축이 흔들리면 안 된다
  (리스크 모델을 온톨로지 밖에 둔 것과 같은 원리). PIN 확인 후 즉시 수정, 거버넌스 기록.
- intent_change_requests: 의미·구조 변경(정의·추가·이동·삭제 등) **제안 대기열**.
  승인은 '반영 예약' 표시일 뿐 — 실제 반영은 운영자의 거버넌스 경로(버전 규칙 준수)로만.

추가만 하는 마이그레이션. 새 표 RLS ON(0016 규칙). downgrade는 DROP.

Revision ID: 0020
Revises: 0019
"""
from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None

_UPGRADE = """
CREATE TABLE intent_display (
  intent_id      TEXT PRIMARY KEY,
  name_ko        TEXT,
  description_ko TEXT,
  updated_by     TEXT NOT NULL,
  updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
);
ALTER TABLE intent_display ENABLE ROW LEVEL SECURITY;

CREATE TABLE intent_change_requests (
  request_id  TEXT PRIMARY KEY,
  intent_id   TEXT,
  kind        TEXT NOT NULL
    CHECK (kind IN ('DEFINITION','ADD','MOVE','DELETE','OTHER')),
  proposal    TEXT NOT NULL,
  proposed_by TEXT NOT NULL,
  status      TEXT NOT NULL DEFAULT 'PENDING'
    CHECK (status IN ('PENDING','APPROVED','REJECTED')),
  decided_by  TEXT,
  decided_at  TIMESTAMPTZ,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_intent_change_requests_status ON intent_change_requests(status);
ALTER TABLE intent_change_requests ENABLE ROW LEVEL SECURITY;
"""

_DOWNGRADE = """
DROP TABLE IF EXISTS intent_change_requests CASCADE;
DROP TABLE IF EXISTS intent_display CASCADE;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWNGRADE)
