#!/usr/bin/env python3
"""Risk Model 적용 거버넌스 스텝 (rm-1.x) — 위험 등급 지정·개정을 승인 흔적으로 남긴다.

사용:
  python scripts/apply_risk_model.py --approved-by "이름"            # dry-run
  python scripts/apply_risk_model.py --approved-by "이름" --commit   # governance_events 기록

**최초 지정(빈 목록 → 7종)은 promote 거동을 바꾼다:** 이전에 통과하던 candidate가 §6-6의
'critical 악화 없음' 절에 걸려 새로 차단될 수 있다(의도된 안전 강화). 그래서 승인 흔적이
선행해야 한다(원칙 9의 정신).

seeds/risk_model_v1.yaml의 CRITICAL 집합과 config.arena.critical_intents가 어긋나면 loud-fail한다.
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

from sqlalchemy import create_engine, select  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_config  # noqa: E402
from app.core.risk_model import (  # noqa: E402
    RISK_MODEL_EVENT,
    assert_config_coherence,
    get_risk_model,
    record_risk_model_update,
)
from app.models.governance import GovernanceEvent  # noqa: E402


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL이 없습니다 (.env 확인)")
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Risk Model governance step")
    parser.add_argument("--approved-by", required=True, help="승인자 (거버넌스 이벤트에 기록)")
    parser.add_argument("--commit", action="store_true", help="DB에 커밋 (기본: 롤백 dry-run)")
    args = parser.parse_args()

    config = get_config()
    rm = get_risk_model()
    try:
        assert_config_coherence(config.arena.critical_intents, rm)
    except ValueError as exc:
        print(f"FAIL {exc}", file=sys.stderr)
        return 2

    print(f"risk_model_version={rm.risk_model_version}")
    print(f"critical({len(rm.critical_intents)}): {', '.join(rm.critical_intents)}")
    print("★ 이 지정은 §6-6 promote의 'critical 악화 없음' 절을 실동시킨다 — "
          "이전에 통과하던 candidate가 새로 차단될 수 있다(의도된 안전 강화).")

    engine = create_engine(_database_url(), poolclass=NullPool)
    try:
        with Session(engine) as session:
            existing = session.scalar(
                select(GovernanceEvent).where(
                    GovernanceEvent.event_type == RISK_MODEL_EVENT,
                    GovernanceEvent.event_id
                    == f"GOV_RM_{rm.risk_model_version.replace('.', '_')}",
                )
            )
            if existing is not None:
                print(f"이미 기록됨: {existing.event_id} (approved_by={existing.approved_by})")
                return 0
            event = record_risk_model_update(session, approved_by=args.approved_by, model=rm)
            print(f"event_id={event.event_id} approved_by={event.approved_by}")
            if args.commit:
                session.commit()
                print("COMMITTED")
            else:
                session.rollback()
                print("DRY-RUN (rolled back) — 기록하려면 --commit")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
