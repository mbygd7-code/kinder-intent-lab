"""dataset_split 경계 — 벤치마크 격리 (§8-2, 절대 규칙 2).

> "KTIB: … 로 구성된 **격리 벤치마크**. 학습 파이프라인이 접근할 수 없다." (§8-2)

`BENCHMARK_HOLDOUT` 에피소드는 GOLD∧LABELED이므로, split을 보지 않는 모든 GOLD 질의가
자기도 모르게 벤치마크를 학습에 끌어들인다. 그러면 Arena 점수는 암기의 측정치가 되고
아무 의미가 없다.

**학습·성장 쪽에서 GOLD 에피소드를 읽는 코드는 반드시 `training_gold()`를 통과시킨다:**

- `brain.backfill.select_exemplars` — exemplar(= 추론 retrieval의 재료)
- `brain.backfill.aggregate_evidence_stats` — 노드 size/gold_count(= 3D Size)
- `brain.diagnosis` — GOLD_LOW 진단 축
- `brain.version_gate` — new_gold(= candidate 생성 트리거)

역방향(벤치마크가 학습분을 끌어오는 것)은 episodes의 `benchmark_integrity` CHECK가 막는다.
"""
from sqlalchemy import ColumnElement, and_

from app.models.episodes import Episode

BENCHMARK_SPLIT = "BENCHMARK_HOLDOUT"


def not_benchmark() -> ColumnElement[bool]:
    """학습 파이프라인이 볼 수 있는 분할 (= 벤치마크가 아닌 것)."""
    return Episode.dataset_split != BENCHMARK_SPLIT


def training_gold() -> ColumnElement[bool]:
    """학습에 쓸 수 있는 확정 라벨: GOLD ∧ LABELED ∧ 비벤치마크 (§3-3 + §8-2)."""
    return and_(
        Episode.reliability_tier == "GOLD",
        Episode.label_state == "LABELED",
        not_benchmark(),
    )


def is_training_gold(episode: Episode) -> bool:
    """ORM 객체용 동일 술어 (이미 로드된 행을 거를 때)."""
    return (
        episode.reliability_tier == "GOLD"
        and episode.label_state == "LABELED"
        and episode.dataset_split != BENCHMARK_SPLIT
    )
