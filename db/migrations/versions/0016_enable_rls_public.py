"""public 스키마 전 테이블 RLS 활성화 — Supabase PostgREST(anon 키) 노출 차단.

Supabase는 public 스키마를 REST API(PostgREST)로 자동 노출한다. RLS가 꺼진 테이블은
프로젝트 anon 키만 알면 누구나 읽고 쓸 수 있다(Supabase Advisor CRITICAL "RLS Disabled
in Public" 29건, 2026-07-15). 이 시스템의 정당한 접근은 전부 백엔드의 직결
Postgres 연결(테이블 소유자 postgres)뿐이고 supabase-js·anon 키는 어디서도 쓰지 않는다.

→ 전 테이블 ENABLE ROW LEVEL SECURITY, 정책은 만들지 않는다(무정책 RLS = 전부 거부).
  소유자는 FORCE가 아닌 한 RLS를 우회하므로 백엔드·alembic·스크립트는 영향이 없다.

이후 생성되는 테이블도 같은 규칙을 따라야 한다 — tests/test_rls.py가
"public 테이블은 전부 RLS ON"을 실 DB에서 강제한다(새 테이블 마이그레이션이
ENABLE을 빠뜨리면 스위트가 깨진다).

Revision ID: 0016
Revises: 0015
"""
from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None

_LIST_PUBLIC_TABLES = "SELECT tablename FROM pg_tables WHERE schemaname = 'public'"


def upgrade() -> None:
    bind = op.get_bind()
    tables = [r[0] for r in bind.exec_driver_sql(_LIST_PUBLIC_TABLES)]
    for t in tables:
        bind.exec_driver_sql(f'ALTER TABLE public."{t}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    # 대칭 복원 — 이 마이그레이션 이후 생성된 테이블까지 포함해 전부 끈다(과잉이지만
    # downgrade는 개발 편의 경로일 뿐, 노출 상태로 되돌리는 것 자체가 목적이다).
    bind = op.get_bind()
    tables = [r[0] for r in bind.exec_driver_sql(_LIST_PUBLIC_TABLES)]
    for t in tables:
        bind.exec_driver_sql(f'ALTER TABLE public."{t}" DISABLE ROW LEVEL SECURITY')
