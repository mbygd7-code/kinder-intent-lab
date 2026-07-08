"""GOLD ⇒ label_state=LABELED 백스톱 CHECK (§3-3·§3-4 v1.2, 사용자 승인 2026-07-08).

앱 레벨 가드(promote_tier + before_flush)를 우회하는 statement 레벨 쓰기
(bulk UPDATE/INSERT)까지 물리적으로 차단한다.

Revision ID: 0002
Revises: 0001
"""
from alembic import op

revision = "0002"
down_revision = "0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().exec_driver_sql(
        "ALTER TABLE episodes ADD CONSTRAINT gold_requires_labeled "
        "CHECK (reliability_tier <> 'GOLD' OR label_state = 'LABELED')"
    )


def downgrade() -> None:
    op.get_bind().exec_driver_sql(
        "ALTER TABLE episodes DROP CONSTRAINT IF EXISTS gold_requires_labeled"
    )
