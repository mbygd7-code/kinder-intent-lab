"""RLS 가드 — public 테이블은 전부 Row Level Security ON (마이그레이션 0016).

Supabase는 public 스키마를 anon 키 REST API(PostgREST)로 자동 노출한다. RLS가 꺼진
테이블은 키만 알면 누구나 읽고 쓸 수 있다. 이 시스템의 정당한 접근은 백엔드의 직결
연결(테이블 소유자)뿐이므로 전 테이블 무정책 RLS(=전부 거부)가 기준선이다.

새 테이블을 추가하는 마이그레이션이 ENABLE ROW LEVEL SECURITY를 빠뜨리면
이 테스트가 깨진다 — 그 마이그레이션에 ENABLE 한 줄을 추가하라.
"""
from sqlalchemy import text


def test_all_public_tables_have_rls_enabled(db_session):
    exposed = db_session.execute(
        text(
            "SELECT tablename FROM pg_tables "
            "WHERE schemaname = 'public' AND NOT rowsecurity ORDER BY tablename"
        )
    ).scalars().all()
    assert exposed == [], (
        f"RLS가 꺼진 public 테이블 {len(exposed)}개: {exposed} — "
        "해당 테이블을 만든 마이그레이션에 ENABLE ROW LEVEL SECURITY를 추가하세요"
    )
