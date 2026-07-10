#!/usr/bin/env python3
"""KTIB 구성 배치 러너 (§8-2, T5.1) — 격리 벤치마크 스냅샷 발급.

사용:
  python scripts/run_ktib_build.py                 # dry-run (자격 집계만, 롤백)
  python scripts/run_ktib_build.py --commit        # ktib_version 발급·동결 적재

자격: BENCHMARK_HOLDOUT ∧ GOLD ∧ LABELED ∧ 비합성 (절대 규칙 2 — DB CHECK가 물리 강제).
같은 내용이면 기존 버전을 그대로 반환하고, extractor가 바뀌면 새 ktib_version이 강제된다.
자격 0건이면 EmptyKtib로 실패한다 — 빈 벤치마크를 0%로 보고하지 않는다.
"""
import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "backend"))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")  # 실패 메시지(한글)가 cp949 콘솔에서 깨지지 않도록

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_ROOT / ".env")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.arena.ktib import EmptyKtib, build_ktib, freeze_items  # noqa: E402
from app.core.config import get_config  # noqa: E402


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL이 없습니다 (.env 확인)")
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="KTIB build (§8-2)")
    parser.add_argument("--commit", action="store_true", help="DB에 커밋 (기본: 롤백 dry-run)")
    parser.add_argument("--notes", default=None, help="ktib_versions.notes")
    args = parser.parse_args()

    config = get_config()
    engine = create_engine(_database_url(), poolclass=NullPool)
    try:
        with Session(engine) as session:
            try:
                items = freeze_items(session)
                print(f"eligible={len(items)}")
                ktib = build_ktib(session, config, notes=args.notes)
            except EmptyKtib as exc:
                print(f"EMPTY KTIB — {exc}", file=sys.stderr)
                return 2
            print(f"ktib_version={ktib.ktib_version} seq={ktib.seq} "
                  f"episodes={ktib.episode_count} extractors={ktib.extractor_versions}")
            if args.commit:
                session.commit()
                print("COMMITTED")
            else:
                session.rollback()
                print("DRY-RUN (rolled back) — 발급하려면 --commit")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
