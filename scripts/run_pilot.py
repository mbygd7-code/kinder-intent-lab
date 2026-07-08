#!/usr/bin/env python3
"""Pilot 500 러너 CLI (§1-14).

사용:
  python scripts/run_pilot.py            # dry-run (n=500, 롤백 — DB 미반영)
  python scripts/run_pilot.py --n 50 --kappa 0.7 --commit

로직은 app/foundry/pilot.py. 이 스크립트는 DB 세션·LLM 클라이언트 조립 + 리포트 출력만 한다.
Phase 1 게이트: 리포트가 consensus_min·judge_reject_max·pilot_kappa_min을 통과해야 스케일 진입.
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
from app.foundry.pilot import SyntheticFoundryProvider, run_pilot  # noqa: E402
from app.llm.base import EmbeddingRequest  # noqa: E402
from app.llm.client import LLMClient, get_llm_client  # noqa: E402
from app.llm.mock import MockProvider  # noqa: E402


def _completion_client(config):
    """LLM_PROVIDER로 완성 클라이언트 선택: mock/synthetic → 오프라인 합성(stage-aware),
    그 외(anthropic 등) → env 주입 실 provider. 임베딩은 별도(embed_fn=mock 유지)."""
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
    parser = argparse.ArgumentParser(description="Kinder Intent Foundry Pilot runner")
    parser.add_argument("--n", type=int, default=500, help="생성할 에피소드 수 (기본 500)")
    parser.add_argument("--kappa", type=float, default=None, help="사람 스팟 검수 kappa (선택)")
    parser.add_argument("--commit", action="store_true", help="DB에 커밋 (기본: 롤백 dry-run)")
    args = parser.parse_args()

    config = get_config()
    run_id = uuid.uuid4().hex[:8]
    engine = create_engine(_database_url(), poolclass=NullPool)

    with Session(engine) as session:
        client = _completion_client(config)
        result = run_pilot(
            session, n=args.n, llm_client=client, embed_fn=_embed_fn(),
            config=config, run_id=run_id, human_kappa=args.kappa,
        )
        if args.commit:
            session.commit()
        else:
            session.rollback()

    manifest = result.manifest
    sample = result.episode_ids[0] if result.episode_ids else None
    out = {
        "run_id": run_id,
        "committed": args.commit,
        "episodes_generated": len(result.episode_ids),
        "sources": manifest.source_ids,
        "lineage_sample": {
            "episode": sample,
            "source": manifest.trace_source(sample) if sample else None,
        },
        "tokens_total": manifest.total_tokens(),
        "cost_usd_total": round(manifest.total_cost(), 6),
        "gate_report": result.report.as_dict(),
    }
    print(json.dumps(out, ensure_ascii=False, indent=2))
    engine.dispose()

    passed = result.report.passed()
    # 게이트 판정 보류(kappa 미입력)는 실패로 취급하지 않되 명시적으로 구분
    return 0 if passed in (True, None) else 1


if __name__ == "__main__":
    raise SystemExit(main())
