#!/usr/bin/env python3
"""로컬 → Supabase 증분 동기화 (append-only + 노드 훈련 가시화 필드).

pre-push 훅이 매 푸시마다 호출한다(수동 실행도 가능). 안전 규칙:
- **추가만 한다.** 각 테이블에서 Supabase에 없는 PK 행만 넣는다(ON CONFLICT DO NOTHING).
  로컬에 없는 Supabase 행은 절대 삭제하지 않는다.
- **brightness 계열은 만지지 않는다**(heldout_accuracy·calibration_ece·last_arena_run —
  절대 규칙 3). 노드는 pending_evaluation·evidence_stats·exemplar_stats만 UPDATE 한다.
- 활성 DATABASE_URL이 Supabase면(로컬 분리 안 됨) 아무것도 하지 않고 종료한다.
- Supabase가 로컬보다 앞선 테이블(외부 쓰기 등)은 경고만 하고 건드리지 않는다.

URL 원천: .env의 DATABASE_URL(활성=로컬) / #SUPABASE_DATABASE_URL(보존된 원격).
"""
import re
import sys
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

_ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

# 노드에서 절대 밀어내지 않는 밝기 계열(§8 · 절대 규칙 3) — Arena만 쓴다.
BRIGHTNESS_COLS = frozenset({"heldout_accuracy", "calibration_ece", "last_arena_run"})
# 로컬에서 Supabase로 동기화하는 노드 필드(훈련 가시화). 나머지는 부트스트랩 시 고정.
NODE_SYNC_COLS = ("pending_evaluation", "evidence_stats", "exemplar_stats")


def _load_env() -> dict[str, str]:
    env: dict[str, str] = {}
    for line in (_ROOT / ".env").read_text(encoding="utf-8").splitlines():
        m = re.match(r"^(DATABASE_URL|#SUPABASE_DATABASE_URL)=(.*)$", line)
        if m:
            env[m.group(1)] = m.group(2).strip()
    return env


def _norm(url: str) -> str:
    """드라이버 접두어를 벗겨 host/db 비교용으로 정규화."""
    return re.sub(r"^postgresql\+\w+://", "postgresql://", url)


def _tables(cur) -> list[str]:
    cur.execute("select tablename from pg_tables where schemaname='public' order by 1")
    return [r[0] for r in cur.fetchall()]


def _has_pk(cur, table: str) -> bool:
    cur.execute(
        "select 1 from pg_index i where i.indrelid = %s::regclass and i.indisprimary limit 1",
        (f'public."{table}"',),
    )
    return cur.fetchone() is not None


def _counts(url: str) -> dict[str, int]:
    with psycopg.connect(url, connect_timeout=30) as c:
        cur = c.cursor()
        out = {}
        for t in _tables(cur):
            cur.execute(f'select count(*) from "{t}"')
            out[t] = cur.fetchone()[0]
        return out


def main() -> int:
    env = _load_env()
    local = env.get("DATABASE_URL")
    supa = env.get("#SUPABASE_DATABASE_URL")
    if not local:
        print("DATABASE_URL이 없다 — .env 확인", file=sys.stderr)
        return 2
    if not supa:
        print("동기화 대상 없음: #SUPABASE_DATABASE_URL 미설정 (Supabase 미사용) — 건너뜀")
        return 0
    if _norm(local) == _norm(supa):
        print("활성 DB가 Supabase다 — 밀어낼 별도 로컬이 없어 건너뜀")
        return 0

    with (
        psycopg.connect(local, connect_timeout=30) as lc,
        psycopg.connect(supa, connect_timeout=30, autocommit=False) as sc,
    ):
        lcur, scur = lc.cursor(), sc.cursor()
        tables = _tables(lcur)
        inserted: dict[str, int] = {}
        try:
            scur.execute("SET session_replication_role = replica")  # FK/트리거 off (superuser)
            for t in tables:
                if not _has_pk(scur, t):
                    continue  # PK 없으면 충돌 판정 불가 — 건너뜀(해당 없음)
                # 로컬 전량을 임시 테이블로 스트리밍 → PK 충돌 없는 행만 본 테이블에 삽입.
                # 구조 동일(같은 마이그레이션)이라 컬럼 순서·타입이 일치한다.
                scur.execute(f'CREATE TEMP TABLE _sync (LIKE "{t}") ON COMMIT DROP')
                with lcur.copy(f'COPY "{t}" TO STDOUT') as out:
                    with scur.copy("COPY _sync FROM STDIN") as cin:
                        for block in out:
                            cin.write(block)
                scur.execute(f'INSERT INTO "{t}" SELECT * FROM _sync ON CONFLICT DO NOTHING')
                inserted[t] = scur.rowcount
                scur.execute("DROP TABLE _sync")

            # 노드 훈련 가시화 필드만 UPDATE (밝기 계열 제외 — 규칙 3)
            lcur.execute(
                f"select intent_id, {', '.join(NODE_SYNC_COLS)} from brain_nodes"
            )
            node_rows = lcur.fetchall()
            for intent, pending, estats, xstats in node_rows:
                scur.execute(
                    "update brain_nodes set pending_evaluation=%s, evidence_stats=%s, "
                    "exemplar_stats=%s where intent_id=%s",
                    (
                        pending,
                        Jsonb(estats) if estats is not None else None,
                        Jsonb(xstats) if xstats is not None else None,
                        intent,
                    ),
                )
            sc.commit()
        except Exception:
            sc.rollback()
            raise

    # 검증 + 리포트
    lc2, sc2 = _counts(local), _counts(supa)
    pushed = {t: n for t, n in inserted.items() if n}
    diverged = {t: (lc2.get(t, 0), sc2[t]) for t in sc2 if sc2[t] > lc2.get(t, 0)}
    still_off = {t: (lc2.get(t, 0), sc2.get(t, 0)) for t in set(lc2) | set(sc2)
                 if lc2.get(t) != sc2.get(t)}

    if pushed:
        print("삽입:", ", ".join(f"{t}+{n}" for t, n in sorted(pushed.items())))
    else:
        print("삽입할 신규 행 없음")
    print(f"노드 필드 동기화: {len(node_rows)}건 (pending/evidence_stats/exemplar_stats)")
    if diverged:
        print("⚠ Supabase가 앞선 테이블(외부 쓰기?) — 건드리지 않음:",
              {t: f"local {a} < supa {b}" for t, (a, b) in diverged.items()})
    print("결과:", "로컬⊆Supabase 완전 반영" if not still_off
          else f"불일치 잔존(대부분 divergence): {still_off}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
