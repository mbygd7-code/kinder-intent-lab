"""arena_runs.created_at를 clock_timestamp()로 — 트랜잭션 내 '최신 run'을 결정 가능하게.

`now()`는 **트랜잭션 시작 시각**이라, 한 트랜잭션에서 arena run을 여러 번 기록하면 모든 행의
created_at이 동일해진다. 그러면 "최신 brain run"(ktib_global·baseline_run·Stage 4 추세 윈도)의
정렬이 비결정적이 된다. run 로그는 **행 삽입 시각**이어야 한다 → `clock_timestamp()`.

기존 행은 그대로 둔다(과거 시각을 다시 쓰지 않는다). 기본값만 바꾼다.

Revision ID: 0014
Revises: 0013
"""
from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None

_UPGRADE = "ALTER TABLE arena_runs ALTER COLUMN created_at SET DEFAULT clock_timestamp();"
_DOWNGRADE = "ALTER TABLE arena_runs ALTER COLUMN created_at SET DEFAULT now();"


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWNGRADE)
