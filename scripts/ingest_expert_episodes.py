#!/usr/bin/env python3
"""전문가 저작 에피소드 유입 — KTIB(§8-2)에 데이터를 넣는 유일한 경로.

사용:
  python scripts/ingest_expert_episodes.py --template ktib_seed.yaml       # 빈 양식 생성
  python scripts/ingest_expert_episodes.py --file ktib_seed.yaml           # dry-run
  python scripts/ingest_expert_episodes.py --file ktib_seed.yaml --commit  # 적재

## ★ 이 스크립트는 발화를 생성하지 않는다

입력 파일은 **사람이 쓰거나 사람이 수집·검수한 비합성 발화**여야 한다. LLM이 만든 문장을
`EXPERT_AUTHORED`로 찍어 넣으면 그 순간 KTIB는 합성 분포가 되고, Arena 점수는 뇌가 자기가
만든 문장을 얼마나 외웠는지의 측정치가 되어 **아무것도 뜻하지 않는다.** 코드는 이것을 탐지할
수 없다 — 그래서 `authored_by`를 필수로 받아 거버넌스 이벤트에 남긴다.

합성 뱅크(FOUNDRY_SYNTHETIC)를 승격시켜 벤치마크를 만드는 길은 `benchmark_integrity` CHECK가
물리적으로 막는다(절대 규칙 2). 그 CHECK를 우회하지 말 것.
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
from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.exc import IntegrityError  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402
from sqlalchemy.pool import NullPool  # noqa: E402

from app.core.config import get_config  # noqa: E402
from app.foundry.expert_ingest import (  # noqa: E402
    BenchmarkNeedsReview,
    ExpertEpisode,
    SyntheticChannelRejected,
    TrainBenchmarkContamination,
    UnknownIngestIntent,
    ingest_expert_episodes,
)

TEMPLATE = {
    "_주의": (
        "발화(teacher_prompt)는 반드시 사람이 쓰거나 사람이 수집한 실제 표현이어야 합니다. "
        "LLM으로 생성한 문장을 넣으면 KTIB가 합성 분포가 되어 Arena 점수가 무의미해집니다."
    ),
    "authored_by": "<저작자: 이름·소속·경력>",
    "approved_by": "<승인자>",
    "origin_channel": "EXPERT_AUTHORED",   # 또는 OFFICIAL_CORPUS / COMMUNITY_DERIVED
    "dataset_split": "BENCHMARK_HOLDOUT",  # 또는 TRAIN / VALIDATION / TEST
    "episodes": [
        {
            "episode_id": "EP_KTIB_0001",
            "teacher_prompt": "<교사가 실제로 한 짧고 애매한 발화>",
            "intent": "<온톨로지 intent_id>",
            "lang": "ko",
            "reviewers": ["<검수자1>", "<검수자2>"],  # BENCHMARK_HOLDOUT은 2인 이상 필수(§3-3)
            "agreement_kappa": 1.0,
        }
    ],
}


def _database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise SystemExit("DATABASE_URL이 없습니다 (.env 확인)")
    return url.replace("postgresql://", "postgresql+psycopg://", 1)


def _load(path: Path) -> tuple[dict, list[ExpertEpisode]]:
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    for key in ("authored_by", "approved_by", "origin_channel", "dataset_split"):
        value = str(doc.get(key, ""))
        if not value or value.startswith("<"):
            raise SystemExit(f"{key}를 채우십시오")
    episodes = []
    for e in doc.get("episodes", []):
        for key in ("episode_id", "teacher_prompt", "intent"):
            if not e.get(key) or str(e[key]).startswith("<"):
                raise SystemExit(f"episodes[{e.get('episode_id')}].{key}를 채우십시오")
        episodes.append(ExpertEpisode(
            episode_id=e["episode_id"], teacher_prompt=e["teacher_prompt"], intent=e["intent"],
            lang=e.get("lang", "ko"), reviewers=tuple(e.get("reviewers") or ()),
            agreement_kappa=e.get("agreement_kappa"),
        ))
    if not episodes:
        raise SystemExit("episodes가 비어 있습니다")
    return doc, episodes


def main() -> int:
    parser = argparse.ArgumentParser(description="Expert episode ingest (§8-2 KTIB)")
    parser.add_argument("--template", type=Path, help="빈 양식을 이 경로에 생성")
    parser.add_argument("--file", type=Path, help="사람이 채운 에피소드 파일")
    parser.add_argument("--commit", action="store_true", help="DB에 커밋 (기본: 롤백 dry-run)")
    args = parser.parse_args()

    if args.template:
        args.template.write_text(
            yaml.safe_dump(TEMPLATE, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        print(f"양식 생성 → {args.template}")
        print("★ 발화는 사람이 씁니다. LLM 생성물을 넣지 마십시오.")
        return 0
    if not args.file:
        parser.error("--template 또는 --file 중 하나가 필요합니다")

    doc, episodes = _load(args.file)
    config = get_config()
    engine = create_engine(_database_url(), poolclass=NullPool)
    try:
        with Session(engine) as session:
            try:
                report = ingest_expert_episodes(
                    session, episodes, config,
                    origin_channel=doc["origin_channel"], dataset_split=doc["dataset_split"],
                    authored_by=doc["authored_by"], approved_by=doc["approved_by"],
                )
            except (SyntheticChannelRejected, BenchmarkNeedsReview, UnknownIngestIntent,
                    TrainBenchmarkContamination) as exc:
                print(f"거부 — {exc}", file=sys.stderr)
                session.rollback()
                return 3
            except IntegrityError as exc:
                # benchmark_integrity CHECK 등 DB 레벨 백스톱
                print(f"DB constraint 위반 — {exc.orig}", file=sys.stderr)
                session.rollback()
                return 4

            print(f"inserted={report.inserted} skipped_duplicate={report.skipped_duplicate} "
                  f"split={doc['dataset_split']} origin={doc['origin_channel']}")
            if args.commit:
                session.commit()
                print("COMMITTED — 다음: python scripts/run_ktib_build.py --commit")
            else:
                session.rollback()
                print("DRY-RUN (rolled back) — 적재하려면 --commit")
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
