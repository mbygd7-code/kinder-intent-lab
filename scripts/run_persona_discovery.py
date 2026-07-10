#!/usr/bin/env python3
"""Persona Discovery 배치 러너 (§4-1, T2.3·T2.4).

사용:
  python scripts/run_persona_discovery.py                 # dry-run (클러스터 리포트만, 롤백)
  python scripts/run_persona_discovery.py --commit        # 클러스터·prior 적재 + state_version 발급

Gym에서 트레이너들이 남긴 human evidence(자연 분포, adversarial 제외)로 행동 벡터를 만들고
HDBSCAN(파라미터 config)으로 클러스터링한다. 발견된 클러스터는 `persona_clusters`로,
클러스터별 intent prior는 `population_priors`로 적재되며, **새 `persona_state_version`이 발급**된다.

## replay 무결성

prior가 바뀌면 새 state_version이다(§5-3). Arena run은 자신이 쓴 state_version을 stamp하므로,
과거 run이 오늘의 prior로 다시 채점되는 일이 없다. 그래서 이 스크립트는 기존 버전을 덮어쓰지 않고
**항상 새 버전을 발급**한다.

## 실행 전제

- 실제 트레이너가 Gym을 플레이해 `TEACHER_TRAINER`/`STAFF_TRAINER` evidence가 쌓여 있어야 한다.
- `config.persona.min_interactions` 미만인 트레이너는 제외된다 — 상호작용 두세 건으로 성향을
  주장하면 그 prior가 추론을 오염시킨다.
- 클러스터가 하나도 발견되지 않으면(전부 노이즈) **아무것도 적재하지 않고 exit 2**. 없는 성향을
  지어내지 않는다.

Arena의 Persona Lift/Harm(§4-2)은 이 클러스터가 생긴 뒤에야 null을 벗어난다.
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

from app.brain.priors import issue_state_version  # noqa: E402
from app.core.config import get_config  # noqa: E402
from app.foundry.persona import (  # noqa: E402
    build_behavior_vectors,
    build_cluster_report,
    cluster_trainers,
    persist_clusters,
    report_lines,
)
from app.foundry.persona_source import eligible_interactions, load_interactions  # noqa: E402


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL이 없습니다 (.env 확인)")
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def main() -> int:
    parser = argparse.ArgumentParser(description="Persona Discovery (§4-1)")
    parser.add_argument("--commit", action="store_true", help="DB에 커밋 (기본: 롤백 dry-run)")
    parser.add_argument("--version", default=None, help="persona_clusters.version (기본: 자동)")
    args = parser.parse_args()

    config = get_config()
    engine = create_engine(_database_url(), poolclass=NullPool)
    try:
        with Session(engine) as session:
            raw = load_interactions(session)
            if not raw:
                print("사람 트레이너 상호작용이 0건이다 — 실제 트레이너가 Gym을 플레이해야 한다. "
                      "(TEACHER_TRAINER/STAFF_TRAINER evidence 없음)", file=sys.stderr)
                return 2

            kept, counts = eligible_interactions(raw, config)
            floor = config.persona.min_interactions
            thin = sorted(ref for ref, n in counts.items() if n < floor)
            print(f"상호작용 {len(raw)}건 · 트레이너 {len(counts)}명 "
                  f"(표본 하한 {floor} 미달로 제외: {len(thin)}명)")
            if not kept:
                print(f"모든 트레이너가 상호작용 {floor}건 미만 — 성향을 주장할 표본이 없다",
                      file=sys.stderr)
                return 2

            vectors = build_behavior_vectors(kept)
            result = cluster_trainers(vectors, config)
            print(f"행동 벡터 {len(vectors)}개 → 클러스터 {result.n_clusters}개 "
                  f"(노이즈 {sum(1 for v in result.labels.values() if v == -1)}명)")

            if result.n_clusters == 0:
                print("클러스터가 발견되지 않았다(전부 노이즈) — 없는 성향을 지어내지 않는다",
                      file=sys.stderr)
                return 2

            print("\n=== 8축 가설 대조표 (§4) ===")
            for line in report_lines(build_cluster_report(result, vectors)):
                print(f"  {line}")

            # prior가 바뀌면 새 버전이다 — 기존 버전을 덮어쓰지 않는다(§5-3 replay)
            state_version = issue_state_version(session, reason="persona_discovery")
            version = args.version or state_version
            clusters, priors = persist_clusters(
                session, result, kept, version=version, state_version=state_version, config=config,
            )
            print(f"\nstate_version={state_version} clusters={len(clusters)} priors={len(priors)}")

            if args.commit:
                session.commit()
                print("COMMITTED — Arena의 Persona Lift/Harm이 다음 run부터 측정된다")
            else:
                session.rollback()
                print("DRY-RUN (rolled back) — 적재하려면 --commit")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
