#!/usr/bin/env python3
"""Version Gate 배치 러너 (§6-6, T4.5) — 조건 충족 시 candidate 뇌 버전 빌드.

사용:
  python scripts/run_version_gate.py                # dry-run (상태만, 롤백)
  python scripts/run_version_gate.py --commit       # 조건 충족 시 candidate 빌드·적재

candidate는 brain_versions에 새 행으로 기록될 뿐 현행 promote 버전을 건드리지 않는다(§6-6 불변).
Arena 시험·promote/reject는 T4.6. 로직은 app/brain/version_gate.py.
"""
import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "backend"))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_ROOT / ".env")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.brain.version_gate import build_candidate, version_gate_status  # noqa: E402
from app.core.config import get_config  # noqa: E402


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL이 없습니다 (.env 확인)")
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Version Gate candidate build (§6-6)")
    parser.add_argument("--commit", action="store_true", help="DB에 커밋 (기본: 롤백 dry-run)")
    args = parser.parse_args()

    config = get_config()
    engine = create_engine(_database_url(), poolclass=NullPool)
    with Session(engine) as session:
        status = version_gate_status(session, config)
        print(f"base={status.base_version} new_gold={status.new_gold} "
              f"min_new_gold={status.min_new_gold} condition_met={status.condition_met} "
              f"pending={status.pending_candidate}")
        cand = build_candidate(session, config)
        if cand is None:
            print("no candidate (조건 미달 또는 pending 없음)")
        else:
            print(f"candidate={cand.version} base={cand.base} delta={cand.delta}")
        if args.commit:
            session.commit()
            print("COMMITTED")
        else:
            session.rollback()
            print("DRY-RUN (rolled back) — 빌드하려면 --commit")
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
