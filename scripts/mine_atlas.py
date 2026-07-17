#!/usr/bin/env python3
"""수동 원문 → Atlas 채굴 (§2 원료 주입구, 2026-07-17 감사 후속).

사용:
  python scripts/mine_atlas.py 원문.txt --title "교사 커뮤니티 Q&A 7월"            # dry-run(롤백)
  python scripts/mine_atlas.py 원문.txt --title "..." --commit                    # 실제 적재
  python scripts/mine_atlas.py 원문.txt --title "..." --source-class PRACTICE --commit

- 원문 파일의 **비어 있지 않은 줄마다 실 LLM 1회**가 호출된다(패러프레이즈 채굴).
- 원문은 S2 raw 저장까지만, Atlas에는 패러프레이즈 대표형만(절대 규칙 7 가드).
- Atlas가 자라면 S6 재보정 통계·coverage 확장 큐가 다음 증산부터 자동으로 살아난다.
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

from app.core.config import get_config  # noqa: E402
from app.foundry.atlas_ingest import mine_text  # noqa: E402
from app.llm.base import EmbeddingRequest  # noqa: E402
from app.llm.client import get_embedding_client, get_llm_client  # noqa: E402


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL이 없습니다 (.env 확인)")
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="원문 → Atlas 채굴 (줄당 LLM 1회)")
    parser.add_argument("file", help="원문 텍스트 파일 (줄 단위 채굴)")
    parser.add_argument("--title", required=True, help="소스 제목 (거버넌스 기록)")
    parser.add_argument("--source-class", default="TEACHER_LANGUAGE",
                        help="소스 분류 (기본 TEACHER_LANGUAGE)")
    parser.add_argument("--commit", action="store_true", help="DB에 커밋 (기본: 롤백 dry-run)")
    args = parser.parse_args()

    text = Path(args.file).read_text(encoding="utf-8")
    lines = [ln for ln in text.splitlines() if ln.strip()]
    print(f"원문 {len(lines)}줄 — 줄당 실 LLM 1회 호출됩니다 (dry-run도 LLM 비용 발생)")

    config = get_config()
    llm = get_llm_client()
    embed_client = get_embedding_client()
    embed_model = os.environ.get("EMBEDDING_MODEL", "embed")
    embed_fn = lambda texts: embed_client.embed(  # noqa: E731
        EmbeddingRequest(inputs=texts, model=embed_model)
    ).vectors

    engine = create_engine(_database_url(), poolclass=NullPool)
    with Session(engine) as session:
        report = mine_text(
            session, llm_client=llm, embed_fn=embed_fn, config=config,
            text=text, title=args.title, source_class=args.source_class,
            model=os.environ.get("LLM_MODEL", "s4-mine"),
        )
        print(report.as_dict())
        if args.commit:
            session.commit()
            print("✓ 커밋 완료 — Atlas가 자랐습니다. 다음 증산부터 S6 통계·coverage가 살아납니다.")
        else:
            session.rollback()
            print("dry-run 롤백 (적재하려면 --commit)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
