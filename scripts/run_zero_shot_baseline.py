#!/usr/bin/env python3
"""Zero-shot 베이스라인 배치 러너 (§8-2 베이스라인 규칙, T5.2).

사용:
  python scripts/run_zero_shot_baseline.py                      # dry-run (롤백, 리포트만 출력)
  python scripts/run_zero_shot_baseline.py --commit             # arena_runs 적재
  python scripts/run_zero_shot_baseline.py --commit --write-report

"첫 KTIB 완성 직후 범용 LLM zero-shot 베이스라인을 측정하고, 그 위에서 80% 목표의 난이도를
재확정한다"(§8-2). 이 스크립트는 측정하고 **제안서를 쓸 뿐**, config나 설계 문서의 수치를
자동으로 바꾸지 않는다 — 확정은 사람 승인 소관(CLAUDE.md 작업 방식 5).

run_type='zero_shot_baseline'로 기록되므로 3D 뇌의 밝기·ktib_global에 절대 반영되지 않는다.
실 LLM_PROVIDER를 쓰면 과금된다. KTIB가 없으면 exit 2.
"""
import argparse
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "backend"))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_ROOT / ".env")

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.arena.baseline import baseline_report, run_zero_shot_baseline  # noqa: E402
from app.arena.ktib import EmptyKtib, latest_ktib  # noqa: E402
from app.core.config import get_config  # noqa: E402
from app.llm.client import get_llm_client  # noqa: E402

REPORT_DIR = _ROOT / "docs" / "05-arena"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL이 없습니다 (.env 확인)")
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="KTIB zero-shot baseline (§8-2)")
    parser.add_argument("--commit", action="store_true", help="DB에 커밋 (기본: 롤백 dry-run)")
    parser.add_argument("--model", default=os.environ.get("LLM_MODEL", "mock"),
                        help="zero-shot에 쓸 범용 LLM 모델 id")
    parser.add_argument("--write-report", action="store_true",
                        help=f"{REPORT_DIR}/ 에 리포트 파일 기록")
    args = parser.parse_args()

    config = get_config()
    engine = create_engine(_database_url(), poolclass=NullPool)
    try:
        with Session(engine) as session:
            ktib = latest_ktib(session)
            if ktib is None:
                print("발급된 ktib_version이 없다 — 먼저 scripts/run_ktib_build.py --commit",
                      file=sys.stderr)
                return 2
            print(f"ktib={ktib.ktib_version} episodes={ktib.episode_count} model={args.model}")
            try:
                result = run_zero_shot_baseline(
                    session, get_llm_client(), config, model=args.model, ktib=ktib
                )
            except EmptyKtib as exc:
                print(f"EMPTY KTIB — {exc}", file=sys.stderr)
                return 2

            report = baseline_report(result, config)
            print()
            print(report)

            if args.write_report:
                REPORT_DIR.mkdir(parents=True, exist_ok=True)
                path = REPORT_DIR / f"ktib-baseline-{ktib.ktib_version}.md"
                path.write_text(report, encoding="utf-8")
                print(f"\nreport -> {path.relative_to(_ROOT)}")

            if args.commit:
                session.commit()
                print(f"COMMITTED run_id={result.run.run_id}")
            else:
                session.rollback()
                print("DRY-RUN (rolled back) — 적재하려면 --commit")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
