#!/usr/bin/env python3
"""훈련 데이터 커버리지 추적기 — 의도·도메인별 훈련 문항이 얼마나 쌓였나 (부트스트랩 진척).

사용:
  python scripts/train_coverage.py           # 사람용 표
  python scripts/train_coverage.py --json     # 기계용 JSON

시험지 커버리지(ktib_coverage.py)의 **훈련 쪽 짝**이다. "부트스트랩이 어느 의도를 아직 못
덮었나"를 알려줘, 시나리오 기반 campaign을 그 방향으로 몰 수 있게 한다(도메인 가중치 조정).

경계(설계 준수):
- **TRAIN split만** 센다 — 벤치마크(BENCHMARK_HOLDOUT)는 학습 데이터가 아니다(절대 규칙 2).
- **역방향 생성 금지**(s6 원칙): 의도로부터 발화를 만들어 그 의도로 라벨링하지 않는다. 합성 훈련의
  유일한 경로는 시나리오 기반 campaign이며 라벨은 blind 합의(S7~S10)가 붙인다. 이 스크립트는
  **아무것도 생성하지 않고** 이미 쌓인 것을 셀 뿐이다(읽기 전용, brightness 무관).

의도 귀속 = label_distribution의 유일 최댓값(top intent). 동률은 '모호'로 따로 빼 지어내지 않는다.
하한은 config뿐(절대 규칙 1): GOLD 목표는 growth.gold_low_threshold.
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

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_config  # noqa: E402
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology  # noqa: E402
from app.models.episodes import Episode  # noqa: E402

TRAIN_SPLIT = "TRAIN"
REJECTED = "REJECTED"


def _database_url() -> str:
    import os

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL이 없습니다 (.env 확인)")
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def _top_intent(dist: dict | None) -> str | None:
    """label_distribution의 유일 최댓값. 비었거나 동률이면 None(모호 — 귀속하지 않는다)."""
    if not dist:
        return None
    top = max(dist.values())
    winners = [i for i, v in dist.items() if v == top]
    return winners[0] if len(winners) == 1 else None


def build_report(session: Session, config) -> dict:
    """TRAIN 에피소드를 의도·도메인별로 집계한 순수 리포트 (임베딩 컬럼은 읽지 않는다)."""
    onto = load_ontology()
    domain_of = {i.intent_id: i.domain for i in onto.intents}
    real_intents = [i.intent_id for i in onto.intents if i.domain]  # UNKNOWN 제외 = 63
    gold_target = config.growth.gold_low_threshold

    # 임베딩(Vector 1536)을 끌어오지 않도록 필요한 컬럼만 select
    rows = session.execute(
        select(
            Episode.label_distribution,
            Episode.reliability_tier,
            Episode.label_state,
            Episode.origin_channel,
        ).where(Episode.dataset_split == TRAIN_SPLIT)
    ).all()

    train = Counter()      # 의도별 사용 가능 훈련 문항 (REJECTED 제외)
    gold = Counter()       # 그중 GOLD (검수 확정)
    channels = Counter()   # origin_channel 구성 (REJECTED 제외)
    ambiguous = 0          # top intent 동률 — 귀속 불가
    unknown_pool = 0       # top intent가 UNKNOWN — 미분류 pool
    rejected = 0

    for dist, tier, state, channel in rows:
        if state == REJECTED:
            rejected += 1
            continue
        channels[channel] += 1
        top = _top_intent(dist)
        if top is None:
            ambiguous += 1
            continue
        if top == UNKNOWN_INTENT_ID:
            unknown_pool += 1
            continue
        train[top] += 1
        if tier == "GOLD":
            gold[top] += 1

    def row(intent: str) -> dict:
        return {
            "intent": intent,
            "domain": domain_of.get(intent),
            "train": train.get(intent, 0),
            "gold": gold.get(intent, 0),
        }

    intent_rows = [row(i) for i in real_intents]
    uncovered = [r["intent"] for r in intent_rows if r["train"] == 0]
    gold_low = [r["intent"] for r in intent_rows if r["gold"] < gold_target]

    domains: dict[str, dict] = {}
    for d in {r["domain"] for r in intent_rows}:
        drows = [r for r in intent_rows if r["domain"] == d]
        domains[d] = {
            "train": sum(r["train"] for r in drows),
            "gold": sum(r["gold"] for r in drows),
            "intents": len(drows),
            "covered": sum(1 for r in drows if r["train"] > 0),
        }

    return {
        "gold_target": gold_target,
        "intents": sorted(intent_rows, key=lambda r: (r["train"], r["intent"])),
        "uncovered": uncovered,
        "gold_low": gold_low,
        "domains": dict(sorted(domains.items())),
        "train_total": int(sum(train.values())),
        "gold_total": int(sum(gold.values())),
        "channels": dict(channels),
        "ambiguous": ambiguous,
        "unknown_pool": unknown_pool,
        "rejected": rejected,
    }


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
