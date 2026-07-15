"""region CHECK를 8도메인으로 — STUDIO(자료 만들기) 신설 (onto-2.0, 마스터 문서 v1.5 §5-10 v2).

region 신설은 온톨로지 major 이벤트다(사용자 승인 2026-07-15). 물리 제약은
brain_nodes.region · situation_frames.domain 두 곳의 컬럼 CHECK — 001의 인라인 CHECK가
자동 명명(`<table>_<column>_check`)으로 존재함을 실DB에서 확인하고 교체한다.
노드 생성·이동은 이 마이그레이션이 하지 않는다(절대 규칙 4 — governance 플로우 소관).

Revision ID: 0017
Revises: 0016
"""
from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None

_OLD = "('PLAY','OBSERVATION','DOCUMENT','VISUAL','COMMUNICATION','OPERATION','REFLECTION')"
_NEW = (
    "('PLAY','OBSERVATION','DOCUMENT','VISUAL','COMMUNICATION','OPERATION','REFLECTION',"
    "'STUDIO')"
)

_TARGETS = [
    ("brain_nodes", "brain_nodes_region_check", "region"),
    ("situation_frames", "situation_frames_domain_check", "domain"),
]


def _swap(check_values: str, downgrade: bool = False) -> None:
    bind = op.get_bind()
    for table, conname, column in _TARGETS:
        bind.exec_driver_sql(f'ALTER TABLE {table} DROP CONSTRAINT "{conname}"')
        bind.exec_driver_sql(
            f'ALTER TABLE {table} ADD CONSTRAINT "{conname}" '
            f"CHECK ({column} IN {check_values})"
        )


def upgrade() -> None:
    _swap(_NEW)


def downgrade() -> None:
    # STUDIO 행이 남아 있으면 ADD CONSTRAINT가 실패한다 — 의도된 가드
    # (노드를 먼저 거버넌스 플로우로 제거해야 좁힐 수 있다).
    _swap(_OLD)
