#!/usr/bin/env python3
"""출제 대기열 blind 2차 검수 (§3-3·§8-2) — 즉석 문답이 쌓은 시험 후보의 독립 검증.

사용:
  python scripts/run_benchmark_review.py --queue blind.yaml       # 2차 검수용 blind 파일 생성
  python scripts/run_benchmark_review.py --apply blind.yaml       # 대조 리포트 (dry-run)
  python scripts/run_benchmark_review.py --apply blind.yaml --write   # 대기열 파일 확정 갱신

## 왜 blind인가

출제 대기열(seeds/benchmark_candidates.yaml)에는 1차 검수자(출제자)의 intent가 있다.
2차가 그 라벨을 보고 "확인"만 하면 독립 검수가 아니라 앵커링이다. 그래서 --queue가 만드는
파일에는 **발화만** 있다 — 1차 라벨·뇌 추측·후보 순위·confidence 전부 의도적으로 없다.

2차가 독립적으로 라벨한 뒤 --apply 하면: 배치 Cohen's kappa가
config.review.min_agreement_kappa 미만이면 **아무것도 확정하지 않는다.** 통과 시 일치
항목만 reviewers 2인 + kappa가 기록되어 ingest_expert_episodes 자격을 갖춘다. 불일치는
rejected 목록으로 옮겨 정직하게 남긴다(조용히 버리지 않는다).

이 스크립트는 DB에 접근하지 않는다 — 파일에서 파일로만. KTIB 적재는 여전히
scripts/ingest_expert_episodes.py 한 곳뿐이다(§8-2).
"""
import argparse
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "backend"))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

import yaml  # noqa: E402

from app.core.config import get_config  # noqa: E402
from app.gym.live import (  # noqa: E402
    BENCHMARK_QUEUE_PATH,
    BlindBatchRejected,
    BlindReviewerInvalid,
    apply_blind_review,
    build_blind_review_file,
)


def main() -> int:
    parser = argparse.ArgumentParser(description="출제 대기열 blind 2차 검수 (§3-3)")
    parser.add_argument("--queue", metavar="OUT", help="2차 검수용 blind 파일을 이 경로에 생성")
    parser.add_argument("--apply", metavar="FILE", help="2차가 채운 blind 파일을 대조 적용")
    parser.add_argument("--write", action="store_true",
                        help="--apply 결과를 대기열 파일에 확정 (기본: dry-run)")
    parser.add_argument("--candidates", default=str(BENCHMARK_QUEUE_PATH),
                        help="출제 대기열 경로 (기본: seeds/benchmark_candidates.yaml)")
    args = parser.parse_args()
    candidates = Path(args.candidates)

    if args.queue:
        doc = build_blind_review_file(candidates)
        if not doc["labels"]:
            print("2차 검수 대기 항목이 없다 — 즉석 문답의 '출제'가 먼저 쌓여야 한다",
                  file=sys.stderr)
            return 2
        Path(args.queue).write_text(
            yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
        print(f"blind 검수 파일 {len(doc['labels'])}건 → {args.queue}")
        print("★ 발화만 보고 독립적으로 라벨하세요 — 1차 라벨은 의도적으로 없습니다.")
        return 0

    if args.apply:
        blind = yaml.safe_load(Path(args.apply).read_text(encoding="utf-8")) or {}
        try:
            report = apply_blind_review(
                blind, get_config(), queue_path=candidates, write=args.write
            )
        except (BlindBatchRejected, BlindReviewerInvalid) as exc:
            print(f"거부: {exc}", file=sys.stderr)
            return 3
        print(f"배치 kappa={report.kappa:.4f}  일치(확정)={len(report.kept)}  "
              f"불일치(반려)={len(report.rejected)}  보류={len(report.skipped)}")
        if not args.write:
            print("DRY-RUN — 확정하려면 --write")
        else:
            print(f"대기열 갱신됨: {candidates}")
            print("다음: approved_by를 채운 뒤 scripts/ingest_expert_episodes.py "
                  f"--file {candidates} --commit")
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
