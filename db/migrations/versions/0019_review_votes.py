"""review_votes — 공부 데이터 2인 검수의 웹 표(votes) 저장소 (§3-3·§3-6).

기존 GOLD 승격 경로(YAML → run_human_review --apply)의 표를 웹으로 옮긴다.
검수자별 판정을 여기 모으고, 적용 시 aggregator.review.apply_review_batch(유일문)에
그대로 넣는다 — 승격 규칙(2인·만장일치·배치 kappa)은 이 표가 아니라 그 문이 강제한다.

- (episode_id, reviewer_canonical) 유니크: 한 사람이 한 에피소드에 한 표(재제출=갱신).
  canonical은 정규화 신원 — 별칭 두 개로 2인을 위장 못 하게(§3-3, review.py와 동일 규칙).
- chosen_intent NULL = 폐기 표.
- 적용 후에도 행은 남는다(감사 추적) — 큐·상태 질의가 label_state로 자연 제외한다.

추가만 하는 마이그레이션. 새 표이므로 RLS ON(0016 규칙, test_rls 강제). downgrade는 DROP.

Revision ID: 0019
Revises: 0018
"""
from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None

_UPGRADE = """
CREATE TABLE review_votes (
  vote_id            TEXT PRIMARY KEY,
  episode_id         TEXT NOT NULL REFERENCES episodes(episode_id) ON DELETE CASCADE,
  reviewer_canonical TEXT NOT NULL,
  reviewer_ref       TEXT NOT NULL,
  chosen_intent      TEXT,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (episode_id, reviewer_canonical)
);
CREATE INDEX idx_review_votes_episode ON review_votes(episode_id);
CREATE INDEX idx_review_votes_reviewer ON review_votes(reviewer_canonical);

ALTER TABLE review_votes ENABLE ROW LEVEL SECURITY;
"""

_DOWNGRADE = "DROP TABLE IF EXISTS review_votes CASCADE;"


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWNGRADE)
