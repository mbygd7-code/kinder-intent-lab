#!/usr/bin/env python3
"""훈련 데이터 커버리지 추적기 — 의도·도메인별 훈련 문항이 얼마나 쌓였나 (부트스트랩 진척).

사용:
  python scripts/train_coverage.py           # 사람용 표
  python scripts/train_coverage.py --json     # 기계용 JSON

집계 로직은 app/observatory/aggregate.py(대시보드와 공유)에 있다 — 이 파일은 CLI 출력만.
경계(설계 준수)는 aggregate.train_coverage_report docstring 참고: TRAIN split만, 역방향 생성
금지(s6 원칙 — 이 스크립트는 아무것도 생성하지 않는다), 임베딩 컬럼 미로딩.
"""
import argparse
import json
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

from app.core.config import get_config  # noqa: E402
from app.observatory.aggregate import train_coverage_report as build_report  # noqa: E402


def _database_url() -> str:
    import os

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL이 없습니다 (.env 확인)")
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def _print_human(rep: dict) -> None:
    print("훈련 데이터 커버리지 — 부트스트랩 진척 (읽기 전용 · 점수 아님)")
    print("=" * 64)
    print()
    print("의도별 훈련 문항 (TRAIN · REJECTED 제외) — 적은 순 상위 12")
    print(f"  {'훈련':>6} {'GOLD':>6}  의도 (도메인)")
    for r in rep["intents"][:12]:
        print(f"  {r['train']:>6} {r['gold']:>6}  {r['intent']} ({r['domain']})")
    print(f"  미커버(훈련 0): {len(rep['uncovered'])} / {len(rep['intents'])}")
    print(f"  GOLD 부족(<{rep['gold_target']}): {len(rep['gold_low'])} / {len(rep['intents'])}")
    print()

    print("도메인별 롤업")
    for d, v in rep["domains"].items():
        print(f"  {d:<14} 훈련 {v['train']:>6}  GOLD {v['gold']:>5}  "
              f"(의도 {v['covered']}/{v['intents']} 커버)")
    print()

    print("전체")
    print(f"  TRAIN 에피소드: {rep['train_total']} (REJECTED {rep['rejected']} 제외)"
          f"    GOLD: {rep['gold_total']}")
    ch = ", ".join(f"{k}={v}" for k, v in sorted(rep["channels"].items()))
    print(f"  채널 구성: {ch or '없음'}")
    if rep["ambiguous"] or rep["unknown_pool"]:
        print(f"  정답 모호(동률): {rep['ambiguous']}    UNKNOWN pool: {rep['unknown_pool']}")
    print()
    print("다음 할 일: 미커버·GOLD 부족 의도의 도메인 가중치를 config.campaign.domain_weights에서")
    print("  올린 뒤, 실 LLM provider를 .env에 설정하고:")
    print("    python scripts/run_campaign.py --n 10000 --commit")
    print("  (역방향 생성 금지 — 시나리오 기반 campaign이 유일한 합성 훈련 경로, s6 원칙)")


def main() -> int:
    parser = argparse.ArgumentParser(description="훈련 데이터 커버리지 (읽기 전용)")
    parser.add_argument("--json", action="store_true", help="기계용 JSON 출력")
    args = parser.parse_args()

    config = get_config()
    engine = create_engine(_database_url(), poolclass=NullPool)
    with Session(engine) as session:
        rep = build_report(session, config)
    engine.dispose()

    if args.json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        _print_human(rep)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
