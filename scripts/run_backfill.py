#!/usr/bin/env python3
"""S13 Seed Brain Backfill 러너 CLI (§5-7) — 실 DB에 노드·exemplar·evidence_stats 적재.

사용:
  python scripts/run_backfill.py                    # dry-run (롤백 — DB 미반영)
  python scripts/run_backfill.py --commit           # 실제 적재
  EMBEDDING_PROVIDER=openai python scripts/run_backfill.py --commit   # 실 임베딩

로직은 app/brain/backfill.py(run_backfill). 이 스크립트는 세션·임베딩 조립 + 리포트만.
- 노드 부트스트랩은 governance_events를 남기는 승인 플로우(절대 규칙 4) — approved_by 필수
- brightness(heldout 등)는 건드리지 않는다(원칙 8) — Observatory에는 null(Dormant)로 보인다
- EMBEDDING_PROVIDER 미설정/mock이면 mock 임베딩(1536) — exemplar 다양성 판정만 근사
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

from app.brain.backfill import run_backfill  # noqa: E402
from app.core.config import get_config  # noqa: E402
from app.llm.base import EmbeddingRequest  # noqa: E402
from app.llm.client import get_embedding_client  # noqa: E402
from app.llm.mock import MockProvider  # noqa: E402


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL이 없습니다 (.env 확인)")
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def _embed_fn():
    provider = (os.environ.get("EMBEDDING_PROVIDER") or "mock").lower()
    if provider in ("", "mock"):
        p = MockProvider(embed_dim=1536)
        return lambda texts: p.embed(EmbeddingRequest(inputs=texts, model="embed")).vectors
    client = get_embedding_client()
    model = os.environ.get("EMBEDDING_MODEL", "embed")
    return lambda texts: client.embed(EmbeddingRequest(inputs=texts, model=model)).vectors


def main() -> int:
    parser = argparse.ArgumentParser(description="Seed Brain backfill (S13)")
    parser.add_argument("--commit", action="store_true", help="DB에 커밋 (기본: 롤백 dry-run)")
    parser.add_argument("--approved-by", default="lab_operator", help="governance 승인 주체")
    args = parser.parse_args()

    engine = create_engine(_database_url(), poolclass=NullPool)
    with Session(engine) as session:
        report = run_backfill(
            session, get_config(), approved_by=args.approved_by, embed_fn=_embed_fn()
        )
        print(
            f"nodes_created={report.nodes_created} "
            f"exemplars_selected={report.exemplars_selected}"
        )
        if args.commit:
            session.commit()
            print("COMMITTED")
        else:
            session.rollback()
            print("DRY-RUN (rolled back) — 적재하려면 --commit")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
