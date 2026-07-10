#!/usr/bin/env python3
"""Fast Update 배치 러너 (§6-5, T4.4) — 트레이너 개인 prior 미세 조정 + 주간 decay.

사용:
  python scripts/run_fast_update.py                 # dry-run (롤백 — DB 미반영)
  python scripts/run_fast_update.py --commit        # fast update 배치 적용 (한 버전)
  python scripts/run_fast_update.py --decay TR_x --commit   # 특정 트레이너 주간 decay

Fast Update는 요청 경로(gym submit)가 아니라 이 배치로 돈다 — state_version은 population·모든
teacher가 공유하는 전역 스냅샷이라, 조정은 나머지를 이월한 완결 스냅샷 한 개로만 발급한다(§5-3).
로직은 app/brain/fast_update.py. 이 스크립트는 세션 조립 + 리포트만.
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

from app.brain.fast_update import run_fast_update_batch, weekly_decay_teacher_prior  # noqa: E402
from app.core.config import get_config  # noqa: E402


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL이 없습니다 (.env 확인)")
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Fast Update batch (§6-5)")
    parser.add_argument("--commit", action="store_true", help="DB에 커밋 (기본: 롤백 dry-run)")
    parser.add_argument("--decay", metavar="TRAINER", help="지정 트레이너의 주간 decay만 적용")
    args = parser.parse_args()

    config = get_config()
    engine = create_engine(_database_url(), poolclass=NullPool)
    with Session(engine) as session:
        if args.decay:
            result = weekly_decay_teacher_prior(session, args.decay, config)
            print(f"weekly_decay trainer={args.decay} version={result.state_version} "
                  f"updated={len(result.updated)}")
        else:
            report = run_fast_update_batch(session, config)
            print(f"fast_update_batch version={report.state_version} "
                  f"trainers_updated={report.trainers_updated}")
        if args.commit:
            session.commit()
            print("COMMITTED")
        else:
            session.rollback()
            print("DRY-RUN (rolled back) — 적재하려면 --commit")
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
