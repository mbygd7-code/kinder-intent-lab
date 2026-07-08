#!/usr/bin/env python3
"""10k~30k 생성 캠페인 러너 CLI (T2.5, §10-2 Phase 2).

사용:
  python scripts/run_campaign.py                       # dry-run (n=1000, 롤백 — DB 미반영)
  python scripts/run_campaign.py --n 10000 --commit    # 실제 적재 (재시작 멱등)
  python scripts/run_campaign.py --baseline-n 500      # 기준선 Pilot 규모 조정

로직은 app/foundry/campaign.py. 이 스크립트는 세션·LLM 조립 + 기준선 Pilot + 리포트 출력만 한다.
기준선은 먼저 Pilot(--baseline-n)을 돌려 만든다 — 캠페인 품질(합의도·reject율·단가)이 이 기준선
대비 악화하면(§1-14) 자동 중단되고 exit 2로 알린다. 도메인 배분·주간 리포트는 config.campaign.
"""
import argparse
import json
import sys
import uuid
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
from app.foundry.campaign import PilotBaseline, run_campaign  # noqa: E402
from app.foundry.pilot import SyntheticFoundryProvider, run_pilot  # noqa: E402
from app.llm.base import EmbeddingRequest  # noqa: E402
from app.llm.client import LLMClient, get_llm_client  # noqa: E402
from app.llm.mock import MockProvider  # noqa: E402


def _completion_client(config):
    """LLM_PROVIDER로 완성 클라이언트를 고른다: mock/synthetic → 오프라인 합성(stage-aware)
    provider, 그 외(anthropic 등) → env 주입 실 provider. 임베딩은 별도(embed_fn=mock 유지)."""
    import os

    provider = (os.environ.get("LLM_PROVIDER") or "mock").lower()
    if provider in ("mock", "synthetic", "synth"):
        return LLMClient(SyntheticFoundryProvider(), config.llm)
    return get_llm_client()


def _database_url() -> str:
    import os

    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL이 없습니다 (.env 확인)")
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def _embed_fn(dim: int = 256):
    provider = MockProvider(embed_dim=dim)
    return lambda texts: provider.embed(EmbeddingRequest(inputs=texts, model="embed")).vectors


def main() -> int:
    parser = argparse.ArgumentParser(description="Kinder Intent Foundry generation campaign")
    parser.add_argument("--n", type=int, default=1000, help="생성할 에피소드 수 (기본 1000)")
    parser.add_argument("--baseline-n", type=int, default=200, help="기준선 Pilot 규모 (기본 200)")
    parser.add_argument("--commit", action="store_true", help="DB에 커밋 (기본: 롤백 dry-run)")
    args = parser.parse_args()

    config = get_config()
    run_id = "camp_" + uuid.uuid4().hex[:8]
    engine = create_engine(_database_url(), poolclass=NullPool)

    with Session(engine) as session:
        client = _completion_client(config)
        # 1) 기준선 Pilot
        pilot = run_pilot(
            session, n=args.baseline_n, llm_client=client, embed_fn=_embed_fn(),
            config=config, run_id=run_id + "_base",
        )
        baseline = PilotBaseline.from_pilot(pilot)
        # 2) 캠페인 (품질 게이트로 자동 중단 가능)
        report = run_campaign(
            session, run_id=run_id, target_n=args.n, llm_client=client,
            embed_fn=_embed_fn(), config=config, baseline=baseline,
        )
        if args.commit:
            session.commit()
        else:
            session.rollback()

    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    engine.dispose()

    # 품질 악화는 exit 2로 구분 — 조기 중단(stopped) 뿐 아니라 서브윈도/마지막 부분 윈도의
    # 악화(stopped를 못 켜는 경우)까지 report.degraded로 잡아 스케줄러/CI에 알린다.
    return 2 if report.degraded else 0


if __name__ == "__main__":
    raise SystemExit(main())
