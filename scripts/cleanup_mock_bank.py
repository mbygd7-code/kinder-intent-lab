#!/usr/bin/env python3
"""mock 자리표시자 뱅크 정리 — 검수 불능 에피소드를 REJECTED로 (일회성 위생 작업).

실 LLM 연결 전(mock provider) 시절 생성된 합성 에피소드는 발화가 전부
"이거 좀 해줄 수 있어? (변형 N)" 자리표시자라 사람이 정답을 붙일 수 없다.
검수 큐에 섞이면 가짜 GOLD → 오염된 대표 예문으로 이어지므로 검수 대상에서 뺀다.

- 대상: 발화가 자리표시자 패턴 ∧ label_state ∈ REVIEWABLE_STATES(사람 검수 대기)
- 처리: 합법 전이 → REJECTED (state_machine 경유 — §3-6 그대로, 임의 UPDATE 아님)
- 감사: governance_events 벌크 1건(패턴·건수·사유). tier·evidence·시험지는 불변
- 기본 dry-run(롤백), --commit 시 반영
"""
import argparse
import sys
import uuid
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "backend"))
sys.stdout.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_ROOT / ".env")

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.aggregator.review import REVIEWABLE_STATES  # noqa: E402
from app.aggregator.state_machine import advance_label_state  # noqa: E402
from app.models.episodes import Episode  # noqa: E402
from app.models.governance import GovernanceEvent  # noqa: E402

MOCK_PATTERN = "%(변형 %"  # mock provider 자리표시자: "이거 좀 해줄 수 있어? (변형 N)"
CLEANUP_EVENT = "MOCK_BANK_CLEANUP"


def _database_url() -> str:
    import os

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL이 없습니다 (.env 확인)")
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def main() -> int:
    ap = argparse.ArgumentParser(description="mock 자리표시자 에피소드 → REJECTED")
    ap.add_argument("--commit", action="store_true", help="반영(기본: dry-run 롤백)")
    args = ap.parse_args()

    engine = create_engine(_database_url(), poolclass=NullPool)
    with Session(engine) as session:
        targets = session.scalars(
            select(Episode).where(
                Episode.teacher_prompt.like(MOCK_PATTERN),
                Episode.label_state.in_(sorted(REVIEWABLE_STATES)),
            )
        ).all()

        by_split: dict[str, int] = {}
        for ep in targets:
            by_split[ep.dataset_split] = by_split.get(ep.dataset_split, 0) + 1
            advance_label_state(ep, "REJECTED")  # 합법 전이만 — 아니면 여기서 폭발한다

        if targets:
            session.add(GovernanceEvent(
                event_id="GOV_" + uuid.uuid4().hex[:12],
                event_type=CLEANUP_EVENT,
                payload={
                    "reason": "mock provider 자리표시자 발화 — 사람 검수 불능(가짜 GOLD 방지)",
                    "pattern": MOCK_PATTERN,
                    "rejected": len(targets),
                    "by_split": by_split,
                },
                approved_by="operator",
            ))
        session.flush()

        mode = "반영(commit)" if args.commit else "DRY-RUN(롤백 — 미반영)"
        print(f"=== mock 뱅크 정리 [{mode}] ===")
        print(f"REJECTED 전이: {len(targets)}건 · split별 {by_split or '없음'}")
        if targets:
            print("예시:", targets[0].teacher_prompt[:40])

        if args.commit:
            session.commit()
        else:
            session.rollback()
    engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
