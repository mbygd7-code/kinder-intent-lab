"""exemplars — 노드별 대표 에피소드 임베딩 스토어 + pgvector 인덱스 (T3.1, §5-1·§5-7).

추론 retrieval(§5-4[1])의 근거. exemplar는 GOLD 확정 라벨 에피소드에서만 선정하며(§5-7),
node_id·episode_id 유일(중복 채택 방지). hnsw 인덱스는 코사인 유사도 최근접 검색용.

Revision ID: 0009
Revises: 0008
"""
from alembic import op

revision = "0009"
down_revision = "0008"
branch_labels = None
depends_on = None

_UPGRADE = """
CREATE TABLE exemplars (
  exemplar_id TEXT PRIMARY KEY,
  node_id     TEXT NOT NULL REFERENCES brain_nodes(node_id),
  intent_id   TEXT NOT NULL,
  episode_id  TEXT NOT NULL REFERENCES episodes(episode_id),
  embedding   vector(1536) NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT now(),
  UNIQUE (node_id, episode_id)
);
CREATE INDEX idx_exemplars_node ON exemplars(node_id);
CREATE INDEX exemplars_embedding_hnsw ON exemplars USING hnsw (embedding vector_cosine_ops);
"""

_DOWNGRADE = "DROP TABLE IF EXISTS exemplars CASCADE;"


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWNGRADE)
