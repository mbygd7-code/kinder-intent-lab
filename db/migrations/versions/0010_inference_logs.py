"""inference_logs — 추론 전건 로그, 4단계 기여 분리 기록 (T3.2, §5-4·§5-5).

stages JSONB에 [1]retrieval [2]scorer [3]prior [4]normalize 각 단계 기여를 분리 저장한다.
신호별 기여를 남겨 이후 학습형 결합(소형 scorer)의 훈련 데이터로 쓴다(§5-5). persona 조회
실패 여부(fallback_used)와 replay용 persona_state_version을 함께 기록한다.

Revision ID: 0010
Revises: 0009
"""
from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None

_UPGRADE = """
CREATE TABLE inference_logs (
  inference_id          TEXT PRIMARY KEY,
  request_id            TEXT NOT NULL,
  mode                  TEXT NOT NULL,
  top_intent            TEXT,
  confidence            REAL,
  margin                REAL,
  persona_state_version TEXT,
  fallback_used         BOOLEAN NOT NULL DEFAULT FALSE,
  stages                JSONB NOT NULL,
  created_at            TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX idx_inference_logs_request ON inference_logs(request_id);
"""

_DOWNGRADE = "DROP TABLE IF EXISTS inference_logs CASCADE;"


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWNGRADE)
