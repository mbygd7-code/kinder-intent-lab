"""benchmark_candidate_batches / _items — 시험지 2차 검수 대기열 스테이징 (§3-3·§8-2).

교사 A가 문항+1~5 평점을 웹에서 제출하면 여기 대기하고, 다른 컴퓨터의 교사 B가 blind로 2차
평점을 매긴다. 서로 다른 2명 ∧ 가중 kappa ≥ 임계면 등록 가능 → 등록은 ingest_expert_episodes로만
episodes에 들어간다(benchmark_integrity CHECK가 최종 방어). 여기엔 tier/label/brightness 없음.

추가만 하는 마이그레이션 — 기존 테이블·데이터 무변경. downgrade는 두 표 DROP.

Revision ID: 0015
Revises: 0014
"""
from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None

_UPGRADE = """
CREATE TABLE benchmark_candidate_batches (
  batch_id        TEXT PRIMARY KEY,
  created_by      TEXT NOT NULL,
  status          TEXT NOT NULL DEFAULT 'AWAITING_SECOND'
    CHECK (status IN ('AWAITING_SECOND','SECOND_DONE','REGISTERED')),
  agreement_kappa DOUBLE PRECISION,
  reviewer_second TEXT,
  ktib_version    TEXT,
  created_at      TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_benchmark_candidate_batches_status ON benchmark_candidate_batches(status);

CREATE TABLE benchmark_candidate_items (
  item_id        TEXT PRIMARY KEY,
  batch_id       TEXT NOT NULL
    REFERENCES benchmark_candidate_batches(batch_id) ON DELETE CASCADE,
  intent_id      TEXT NOT NULL,
  teacher_prompt TEXT NOT NULL,
  rating_a       INTEGER NOT NULL CHECK (rating_a BETWEEN 1 AND 5),
  rating_b       INTEGER CHECK (rating_b IS NULL OR rating_b BETWEEN 1 AND 5)
);
CREATE INDEX idx_benchmark_candidate_items_batch ON benchmark_candidate_items(batch_id);
"""

_DOWNGRADE = """
DROP TABLE IF EXISTS benchmark_candidate_items CASCADE;
DROP TABLE IF EXISTS benchmark_candidate_batches CASCADE;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWNGRADE)
