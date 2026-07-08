"""evidence.reliability를 [0,1]로 제약 (evidence.schema.json과 정합).

001의 evidence.strength는 CHECK BETWEEN 0 AND 1이나 reliability는 무제약이었다.
집계 가중치 _weight = strength × reliability의 부호반전·과대 가중을 물리적으로 막는다.

Revision ID: 0005
Revises: 0004
"""
from alembic import op

revision = "0005"
down_revision = "0004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        "ALTER TABLE evidence ADD CONSTRAINT evidence_reliability_range "
        "CHECK (reliability IS NULL OR reliability BETWEEN 0 AND 1)"
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        "ALTER TABLE evidence DROP CONSTRAINT IF EXISTS evidence_reliability_range"
    )
