#!/usr/bin/env python3
"""Arena 배치 러너 (§8-2, T5.3) — KTIB 위에서 Seed Brain을 채점한다.

사용:
  python scripts/run_arena.py                        # dry-run: 현행 base 버전을 채점 (롤백)
  python scripts/run_arena.py --commit               # arena_runs + confusion_edges 적재
  python scripts/run_arena.py --candidate --commit   # 대기 중인 candidate를 시험 → promote/reject

실행 시점(§8-2): 주간 정기 + Version Gate 시.

- `--candidate` 없이: 현행 base(promote된 버전, 없으면 seed-v0)의 **기준 점수**를 만든다.
  다음 candidate의 global_delta는 이 run을 기준으로 계산된다.
- `--candidate`: 대기 중인 candidate를 채점하고 §6-6 promote 규칙으로 판정한다.
  promote면 밝기·pending 링·Resonance가 반영 잡(arena.reflect)을 통해 갱신된다.

밝기(heldout_accuracy)는 promote를 통과한 run만이 켠다 — 러너 자체는 쓰지 않는다(절대 규칙 3).
실 LLM_PROVIDER를 쓰면 과금된다.
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

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.arena.ktib import EmptyKtib, latest_ktib  # noqa: E402
from app.arena.reflect import reflect_arena_run  # noqa: E402
from app.arena.runner import KtibAxisMismatch, baseline_run, build_outcome, run_arena  # noqa: E402
from app.brain.promote import resolve_candidate  # noqa: E402
from app.brain.version_gate import current_base, pending_candidate  # noqa: E402
from app.core.config import get_config  # noqa: E402
from app.llm.client import get_embedding_client, get_llm_client  # noqa: E402
from app.llm.base import EmbeddingRequest  # noqa: E402

SEED = "seed-v0"


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL이 없습니다 (.env 확인)")
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def _embed_fn():
    client = get_embedding_client()
    model = os.environ.get("EMBEDDING_MODEL", "text-embedding-3-small")
    return lambda texts: client.embed(EmbeddingRequest(inputs=texts, model=model)).vectors


def main() -> int:
    parser = argparse.ArgumentParser(description="Arena run on KTIB (§8-2)")
    parser.add_argument("--commit", action="store_true", help="DB에 커밋 (기본: 롤백 dry-run)")
    parser.add_argument("--candidate", action="store_true",
                        help="대기 중인 candidate를 시험하고 promote/reject 판정")
    args = parser.parse_args()

    config = get_config()
    engine = create_engine(_database_url(), poolclass=NullPool)
    try:
        with Session(engine) as session:
            ktib = latest_ktib(session)
            if ktib is None:
                print("발급된 ktib_version이 없다 — 먼저 scripts/run_ktib_build.py --commit",
                      file=sys.stderr)
                return 2

            base = current_base(session)
            base_name = base.version if base else SEED

            if args.candidate:
                cand = pending_candidate(session, base_name)
                if cand is None:
                    print(f"base={base_name} 위에 대기 중인 candidate 없음 — "
                          f"scripts/run_version_gate.py --commit 먼저", file=sys.stderr)
                    return 3
                model_version = cand.version
            else:
                model_version = base_name

            print(f"ktib={ktib.ktib_version} items={ktib.episode_count} "
                  f"model_version={model_version}")

            try:
                result = run_arena(
                    session, get_llm_client(), _embed_fn(), config, model_version=model_version,
                    ktib=ktib,
                )
            except EmptyKtib as exc:
                print(f"EMPTY KTIB — {exc}", file=sys.stderr)
                return 2

            m = result.run.metrics
            print(f"run_id={result.run.run_id} "
                  f"first_intent_accuracy={m['first_intent_accuracy']} "
                  f"ece={m['ece']} no_candidate={m['abstain_count']}/{m['item_count']}")
            print(f"decisions={m['decisions']}")   # decision 단계의 abstain은 여기서만 보인다
            crit = m["critical"]
            print(f"CWAR-fire={crit['cwar_fire']} (n={crit['cwar_fire_n']}) "
                  f"CWAR-miss={crit['cwar_miss']} CCC={crit['ccc']} "
                  f"critical_gold={crit['o_count']}")
            print(f"recovery={m['recovery']} persona={m['persona']}")

            if args.candidate:
                try:
                    base_run = baseline_run(session, base_name, ktib.ktib_version)
                except KtibAxisMismatch as exc:
                    print(f"KTIB 축 불일치 — {exc}", file=sys.stderr)
                    return 4
                if base_run is None:
                    print(f"기준 run 없음(base={base_name}) — 먼저 --candidate 없이 1회 실행해 "
                          f"기준 점수를 만들어라. 상승을 입증할 수 없으면 promote되지 않는다.")
                outcome = build_outcome(result.run, base_run, config)
                decision = resolve_candidate(session, cand, outcome, config)
                print(f"decision={decision.decision} version={decision.version} "
                      f"reasons={decision.reasons} nodes_brightened={decision.nodes_brightened}")
                reflected = reflect_arena_run(session, result.run, config,
                                              promoted=decision.decision == "promote")
                print(f"edges_touched={reflected.edges_touched} "
                      f"resonance={reflected.resonance}")
            else:
                reflected = reflect_arena_run(session, result.run, config, promoted=False)
                print(f"edges_touched={reflected.edges_touched} "
                      f"nodes_brightened={reflected.nodes_brightened} (현행 뇌 재측정)")

            if args.commit:
                session.commit()
                print("COMMITTED")
            else:
                session.rollback()
                print("DRY-RUN (rolled back) — 적재하려면 --commit")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
