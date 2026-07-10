"""Arena 지표 — 순수 계산 (§8-2, T5.2·T5.3).

산출 3종:
- **heldout accuracy**: global / region / node. KTIB 첫 의도 정확도(first_intent_accuracy).
- **방향성 confusion matrix**: `P(예측=B | 정답=A) ≠ P(예측=A | 정답=B)` (§5-6).
- **calibration (ECE)**: 등간격 신뢰도 버킷의 |정확도 − 신뢰도| 가중평균. 버킷 수는 config.

정직성 규칙:
- abstain(top_intent=None)은 정답이 아니다 — 오답으로 세되 abstain_count로 따로 남긴다.
- 측정되지 않은 노드는 accuracy 0이 아니라 **by_node에서 아예 빠진다**(§7-6 Stage 0 Dormant =
  '노드 heldout 미측정'). 미측정과 0%를 같은 값으로 만들지 않는다.
- 표본이 0이면 지표는 None이다.

이 모듈은 DB를 모른다. 예측 목록을 받아 숫자만 만든다.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass


@dataclass(frozen=True)
class Prediction:
    """KTIB 아이템 1건의 채점 입력. predicted_intent=None은 abstain."""

    episode_id: str
    gold_intent: str
    predicted_intent: str | None
    confidence: float

    @property
    def correct(self) -> bool:
        return self.predicted_intent is not None and self.predicted_intent == self.gold_intent


def _accuracy(preds: list[Prediction]) -> float | None:
    if not preds:
        return None
    return round(sum(p.correct for p in preds) / len(preds), 4)


def expected_calibration_error(preds: list[Prediction], bins: int) -> float | None:
    """ECE = Σ_b (n_b/N)·|acc_b − conf_b|. 표본 0이면 None.

    abstain은 confidence=자기가 보고한 값 그대로 들어간다(보통 0) — 모델이 '모른다'고 말한
    강도까지 캘리브레이션 대상이다.
    """
    if not preds:
        return None
    buckets: dict[int, list[Prediction]] = defaultdict(list)
    for p in preds:
        conf = min(max(p.confidence, 0.0), 1.0)
        buckets[min(int(conf * bins), bins - 1)].append(p)

    total = len(preds)
    ece = 0.0
    for members in buckets.values():
        acc = sum(m.correct for m in members) / len(members)
        conf = sum(min(max(m.confidence, 0.0), 1.0) for m in members) / len(members)
        ece += (len(members) / total) * abs(acc - conf)
    return round(ece, 4)


def confusion_matrix(preds: list[Prediction], *, confirm_min: int) -> list[dict]:
    """방향성 confusion 목록 — (from_true, to_predicted, count, confusion_rate, confirmed).

    분모는 해당 gold intent의 **전체 아이템 수**다(abstain 포함) — 그래야 rate가
    `P(예측=B | 정답=A)`라는 정의를 지킨다. abstain 자체는 어떤 intent로도 혼동된 것이
    아니므로 pair를 만들지 않는다.
    """
    totals: dict[str, int] = defaultdict(int)
    pairs: dict[tuple[str, str], int] = defaultdict(int)
    for p in preds:
        totals[p.gold_intent] += 1
        if p.predicted_intent is not None and p.predicted_intent != p.gold_intent:
            pairs[(p.gold_intent, p.predicted_intent)] += 1

    rows = [
        {
            "from_true": true,
            "to_predicted": pred,
            "count": count,
            "confusion_rate": round(count / totals[true], 4),
            "confirmed": count >= confirm_min,
        }
        for (true, pred), count in pairs.items()
    ]
    # 결정론적 순서: rate 내림차순 → 이름 (같은 입력 → 같은 JSONB)
    rows.sort(key=lambda r: (-r["confusion_rate"], r["from_true"], r["to_predicted"]))
    return rows


def compute_metrics(
    preds: list[Prediction], regions: dict[str, str], *, ece_bins: int
) -> dict:
    """global / by_node / by_region 지표 dict (arena_runs.metrics에 그대로 저장).

    regions: intent_id → region(domain). gold intent가 매핑에 없으면 region 집계에서 빠진다
    (온톨로지 밖 라벨을 임의의 region에 귀속시키지 않는다).
    """
    by_node_preds: dict[str, list[Prediction]] = defaultdict(list)
    by_region_preds: dict[str, list[Prediction]] = defaultdict(list)
    for p in preds:
        by_node_preds[p.gold_intent].append(p)
        region = regions.get(p.gold_intent)
        if region is not None:
            by_region_preds[region].append(p)

    return {
        "first_intent_accuracy": _accuracy(preds),
        "item_count": len(preds),
        "correct": sum(p.correct for p in preds),
        "abstain_count": sum(p.predicted_intent is None for p in preds),
        "ece": expected_calibration_error(preds, ece_bins),
        "by_node": {
            intent: {
                "n": len(members),
                "correct": sum(m.correct for m in members),
                "accuracy": _accuracy(members),
                "ece": expected_calibration_error(members, ece_bins),
            }
            for intent, members in sorted(by_node_preds.items())
        },
        "by_region": {
            region: {
                "n": len(members),
                "correct": sum(m.correct for m in members),
                "accuracy": _accuracy(members),
            }
            for region, members in sorted(by_region_preds.items())
        },
    }
