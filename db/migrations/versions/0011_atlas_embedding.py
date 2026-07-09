"""atlas_entries.embedding — surface_form 임베딩 영속화 (retrieval 요청당 재임베딩 제거).

retrieve_candidates(§5-4[1])가 요청마다 전체 Atlas surface_form을 재임베딩하던 것을 제거한다.
S4(mine_atlas_entry)가 적재 시 대표형 임베딩을 함께 저장하고, 0011 이전에 쌓인 기존 뱅크는
backfill_atlas_embeddings로 채운다. retrieval은 exemplar와 동일하게 pgvector 코사인으로 비교한다.

nullable — 아직 임베딩이 없는 행은 retrieval에서 제외한다(재임베딩 대신). HNSW 인덱스는 두지
않는다: atlas retrieval은 임계값 범위질의(sim ≥ atlas.map_min_similarity, LIMIT 없음)라 HNSW가
관여하지 않으며 온라인 적재 쓰기비용만 늘린다. 향후 top-k 질의를 도입하면 그때 별도 추가한다.

Revision ID: 0011
Revises: 0010
"""
from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None

_UPGRADE = "ALTER TABLE atlas_entries ADD COLUMN embedding vector(1536);"
_DOWNGRADE = "ALTER TABLE atlas_entries DROP COLUMN IF EXISTS embedding;"


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWNGRADE)
