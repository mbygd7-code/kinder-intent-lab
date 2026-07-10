#!/usr/bin/env python3
"""인간 검수 배치 적용 (§3-3) — GOLD를 만드는 유일한 경로.

사용:
  python scripts/run_human_review.py --queue --limit 20        # 검수 대기 목록을 파일로 뽑는다
  python scripts/run_human_review.py --apply reviews.yaml               # dry-run
  python scripts/run_human_review.py --apply reviews.yaml --commit      # 확정

## 이 스크립트는 검수하지 않는다. **사람이 채운 판정 파일을 적용할 뿐이다.**

`--queue`가 뽑아준 파일을 서로 다른 검수자 2명 이상이 각자 채운 뒤, 합쳐서 `--apply`한다.

```yaml
approved_by: 김OO (검수 총괄)
votes:
  - {episode_id: EP_xxx, reviewer_ref: HR_kim, chosen_intent: play_expand}
  - {episode_id: EP_xxx, reviewer_ref: HR_lee, chosen_intent: play_expand}   # 일치 → GOLD
  - {episode_id: EP_yyy, reviewer_ref: HR_kim, chosen_intent: null}          # 폐기표
  - {episode_id: EP_yyy, reviewer_ref: HR_lee, chosen_intent: null}          # 만장일치 폐기
```

배치 kappa가 `config.review.min_agreement_kappa` 미만이거나 계산 불가면 **아무것도 확정하지
않는다**. 에피소드별로도 만장일치가 아니면 상태가 변하지 않는다 — 강제 확정은 없다.

**주의:** 합성 에피소드(`FOUNDRY_SYNTHETIC`)도 GOLD가 될 수 있고, 그것은 exemplar와 Version
Gate의 new_gold에 쓰인다. 그러나 `benchmark_integrity` CHECK 때문에 **KTIB에는 영원히 못
들어간다**(절대 규칙 2). KTIB용 비합성 에피소드는 `scripts/ingest_expert_episodes.py`로 넣는다.
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

import yaml  # noqa: E402
from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.aggregator.review import (  # noqa: E402
    REVIEWABLE_STATES,
    ReviewBatchRejected,
    ReviewVote,
    UnknownReviewIntent,
    apply_review_batch,
)
from app.aggregator.state_machine import IllegalTransition  # noqa: E402
from app.core.config import get_config  # noqa: E402
from app.models.episodes import Episode  # noqa: E402


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL이 없습니다 (.env 확인)")
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def _emit_queue(session: Session, limit: int, out: Path) -> int:
    rows = session.scalars(
        select(Episode)
        .where(Episode.label_state.in_(sorted(REVIEWABLE_STATES)))
        .order_by(Episode.episode_id)
        .limit(limit)
    ).all()
    if not rows:
        print("검수 대기 에피소드가 없다", file=sys.stderr)
        return 2

    doc = {
        "_주의": "검수자 2명 이상이 각자 chosen_intent를 채운 뒤 votes를 합쳐 --apply 하십시오. "
                 "chosen_intent: null 은 '폐기' 표입니다.",
        "approved_by": "<검수 총괄 이름>",
        "votes": [
            {"episode_id": e.episode_id, "reviewer_ref": "<검수자 id>", "chosen_intent": None,
             "_teacher_prompt": e.teacher_prompt,
             "_aggregator_suggests": max(e.label_distribution, key=e.label_distribution.get)
             if e.label_distribution else None,
             "_tier": e.reliability_tier, "_origin": e.origin_channel}
            for e in rows
        ],
    }
    out.write_text(yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    print(f"검수 대기 {len(rows)}건 → {out}")
    print("★ aggregator 제안(_aggregator_suggests)은 참고용이다. 그대로 베끼면 검수가 아니다.")
    return 0


def _load_votes(path: Path) -> tuple[str, list[ReviewVote]]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    approved_by = (doc or {}).get("approved_by")
    if not approved_by or str(approved_by).startswith("<"):
        raise SystemExit("approved_by(검수 총괄)를 채우십시오")
    votes = []
    for v in (doc or {}).get("votes", []):
        reviewer = v.get("reviewer_ref")
        if not reviewer or str(reviewer).startswith("<"):
            raise SystemExit(f"reviewer_ref 미기입: {v.get('episode_id')}")
        votes.append(ReviewVote(v["episode_id"], reviewer, v.get("chosen_intent")))
    if not votes:
        raise SystemExit("votes가 비어 있습니다")
    return str(approved_by), votes


def main() -> int:
    parser = argparse.ArgumentParser(description="Human review → GOLD (§3-3)")
    parser.add_argument("--queue", action="store_true", help="검수 대기 목록을 파일로 출력")
    parser.add_argument("--limit", type=int, default=20, help="--queue 출력 건수")
    parser.add_argument("--out", type=Path, default=Path("review_queue.yaml"))
    parser.add_argument("--apply", type=Path, help="사람이 채운 판정 파일")
    parser.add_argument("--commit", action="store_true", help="DB에 커밋 (기본: 롤백 dry-run)")
    args = parser.parse_args()

    if not args.queue and not args.apply:
        parser.error("--queue 또는 --apply 중 하나가 필요합니다")

    config = get_config()
    engine = create_engine(_database_url(), poolclass=NullPool)
    try:
        with Session(engine) as session:
            if args.queue:
                return _emit_queue(session, args.limit, args.out)

            approved_by, votes = _load_votes(args.apply)
            try:
                report = apply_review_batch(session, votes, config, approved_by=approved_by)
            except (ReviewBatchRejected, UnknownReviewIntent, IllegalTransition) as exc:
                print(f"배치 거부 — {exc}", file=sys.stderr)
                session.rollback()
                return 3

            print(f"kappa={report.kappa} reviewers={report.reviewers}")
            print(f"LABELED(→GOLD)={report.labeled} REJECTED={report.rejected} "
                  f"UNCHANGED={report.unchanged}")
            for o in report.episodes:
                if o.outcome == "UNCHANGED":
                    print(f"  - {o.episode_id}: {o.reason}")

            if args.commit:
                session.commit()
                print("COMMITTED")
            else:
                session.rollback()
                print("DRY-RUN (rolled back) — 확정하려면 --commit")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
