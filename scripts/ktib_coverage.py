#!/usr/bin/env python3
"""시험지(KTIB) 커버리지 추적기 — 의도별 문항이 게이트 하한 대비 몇 개인가 (§8-2·§10-2).

사용:
  python scripts/ktib_coverage.py           # 사람용 표
  python scripts/ktib_coverage.py --json     # 기계용 JSON

"다음에 무슨 문항을 써야 하는가"를 사람에게 알려주는 **읽기 전용** 리포트다. 점수(brightness)나
시험 결과가 아니라 **출제 진척**만 본다 — CRITICAL 7개를 먼저, 게이트 하한(config)까지.

원천:
- 등록: eligible_episodes (BENCHMARK_HOLDOUT∧GOLD∧LABELED∧비합성)를 gold_intent별 집계
- 검수 중: benchmark_candidate_items 중 아직 REGISTERED 안 된 배치 → intent_id별 집계

하한은 config뿐(절대 규칙 1): CRITICAL = gate.critical_surface_min_items. 나머지 56개는 게이트
하한이 없어 "측정 가능 여부(문항 ≥ 1)"만 본다 — 없는 숫자를 지어내지 않는다.
"""
import argparse
import json
import sys
from collections import Counter
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "backend"))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_ROOT / ".env")

from sqlalchemy import create_engine, func, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.arena.ktib import (  # noqa: E402
    AmbiguousGoldLabel,
    _gold_intent,
    eligible_episodes,
    latest_ktib,
)
from app.core.config import get_config  # noqa: E402
from app.core.ontology import load_ontology  # noqa: E402
from app.models.benchmark_candidates import (  # noqa: E402
    BenchmarkCandidateBatch,
    BenchmarkCandidateItem,
)


def _database_url() -> str:
    import os

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL이 없습니다 (.env 확인)")
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def _registered_counts(session: Session) -> tuple[Counter, list[str]]:
    """등록된 벤치마크 문항을 gold_intent별로 집계. 정답 동률(모호)은 따로 모은다.

    gold intent 판정은 ktib 구성기와 동일한 _gold_intent(유일 최댓값)를 재사용한다 — 커버리지가
    실제 KTIB 구성과 다른 기준으로 세면 안 되기 때문. 동률이면 여기서도 세지 않는다(정직).
    """
    counts: Counter = Counter()
    ambiguous: list[str] = []
    for ep in eligible_episodes(session):
        try:
            counts[_gold_intent(ep)] += 1
        except AmbiguousGoldLabel:
            ambiguous.append(ep.episode_id)
    return counts, ambiguous


def _pending_counts(session: Session) -> dict[str, int]:
    """아직 등록(REGISTERED)되지 않은 후보 배치의 문항을 intent별로 — 작성/검수 중 진행 물량."""
    rows = session.execute(
        select(BenchmarkCandidateItem.intent_id, func.count())
        .join(
            BenchmarkCandidateBatch,
            BenchmarkCandidateItem.batch_id == BenchmarkCandidateBatch.batch_id,
        )
        .where(BenchmarkCandidateBatch.status != "REGISTERED")
        .group_by(BenchmarkCandidateItem.intent_id)
    ).all()
    return {intent: int(n) for intent, n in rows}


def build_report(session: Session, config) -> dict:
    """의도별 등록/검수중 문항을 게이트 하한 대비로 정리한 순수 리포트(DB 읽기만)."""
    onto = load_ontology()
    domain_of = {i.intent_id: i.domain for i in onto.intents}
    real_intents = [i.intent_id for i in onto.intents if i.domain]  # UNKNOWN 제외 = 63
    critical = list(config.arena.critical_intents)
    critical_set = set(critical)
    floor = config.gate.critical_surface_min_items

    registered, ambiguous = _registered_counts(session)
    pending = _pending_counts(session)

    def row(intent: str) -> dict:
        reg = registered.get(intent, 0)
        return {
            "intent": intent,
            "domain": domain_of.get(intent),
            "registered": reg,
            "pending": pending.get(intent, 0),
            "gap_to_floor": max(0, floor - reg),
            "meets_floor": reg >= floor,
        }

    crit_rows = [row(i) for i in critical]
    crit_met = sum(1 for r in crit_rows if r["meets_floor"])
    noncrit_rows = [row(i) for i in real_intents if i not in critical_set]
    measured = sum(1 for r in noncrit_rows if r["registered"] >= 1)

    latest = latest_ktib(session)
    return {
        "floor_critical": floor,
        "critical": {
            "floor": floor,
            "met": crit_met,
            "total": len(crit_rows),
            "ready": crit_met == len(crit_rows),
            "rows": sorted(crit_rows, key=lambda r: (r["registered"], r["intent"])),
        },
        "noncritical": {
            "measured": measured,
            "total": len(noncrit_rows),
            "unmeasured": [r["intent"] for r in noncrit_rows if r["registered"] == 0],
            "rows": sorted(noncrit_rows, key=lambda r: (r["registered"], r["intent"])),
        },
        "registered_total": int(sum(registered.values())),
        "pending_total": int(sum(pending.values())),
        "ambiguous_gold": ambiguous,
        "current_ktib": (
            None
            if latest is None
            else {"version": latest.ktib_version, "episode_count": latest.episode_count}
        ),
    }


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
