#!/usr/bin/env python3
"""시험지(KTIB) 커버리지 추적기 — 의도별 문항이 게이트 하한 대비 몇 개인가 (§8-2·§10-2).

사용:
  python scripts/ktib_coverage.py           # 사람용 표
  python scripts/ktib_coverage.py --json     # 기계용 JSON

집계 로직은 app/observatory/aggregate.py(대시보드와 공유)에 있다 — 이 파일은 CLI 출력만.
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
from app.observatory.aggregate import ktib_coverage_report as build_report  # noqa: E402


def _database_url() -> str:
    import os

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL이 없습니다 (.env 확인)")
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def _print_human(rep: dict) -> None:
    floor = rep["floor_critical"]
    crit = rep["critical"]
    print("시험지(KTIB) 커버리지 — 출제 진척 (읽기 전용 · 점수 아님)")
    print("=" * 64)
    print()
    print(f"CRITICAL {crit['total']}개  (게이트 필수 · 하한 {floor}문항/의도)")
    print(f"  {'등록':>4} {'검수중':>5} {'갭':>6}  의도")
    for r in crit["rows"]:
        mark = "✓" if r["meets_floor"] else "✗"
        gap = "충족" if r["meets_floor"] else f"-{r['gap_to_floor']}"
        print(f"  {r['registered']:>4} {r['pending']:>5} {gap:>6}  {mark} {r['intent']}")
    verdict = "게이트 충족" if crit["ready"] else "게이트 미충족"
    print(f"  → CRITICAL 표면: {crit['met']}/{crit['total']} 의도 하한 도달 — {verdict}")
    print()

    nc = rep["noncritical"]
    print(f"나머지 {nc['total']}개  (게이트 하한 없음 · 측정 여부만)")
    print(f"  측정됨(≥1문항): {nc['measured']} / {nc['total']}")
    print(f"  미측정(0문항):  {len(nc['unmeasured'])}")
    if nc["unmeasured"]:
        head = ", ".join(nc["unmeasured"][:8])
        extra = len(nc["unmeasured"]) - 8
        more = "" if extra <= 0 else f" … (+{extra}, 전체는 --json)"
        print(f"  미측정 의도: {head}{more}")
    print()

    print("전체")
    print(f"  등록 벤치마크 문항: {rep['registered_total']}    검수 중: {rep['pending_total']}")
    ktib = rep["current_ktib"]
    ktib_str = "없음" if ktib is None else f"{ktib['version']} ({ktib['episode_count']}문항)"
    print(f"  현재 KTIB: {ktib_str}")
    if rep["ambiguous_gold"]:
        print(f"  정답 모호(집계 제외): {len(rep['ambiguous_gold'])} — {rep['ambiguous_gold']}")
    print()
    if not crit["ready"]:
        print("다음 할 일: CRITICAL 7개부터 채우세요.")
        print("  1) seeds/ktib_critical7_template.csv 작성 (혼동 이웃과 구별되게)")
        print("  2) 웹 ExamUpload 또는 scripts/ingest_expert_episodes.py 로 등록")
        print("  3) scripts/run_ktib_build.py 로 동결 → scripts/run_arena.py 로 채점")


def main() -> int:
    parser = argparse.ArgumentParser(description="KTIB 시험문항 커버리지 (읽기 전용)")
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
