"""T5.2/T5.3 AC (§8-2·§5-6): Arena 지표 순수 계산.

- global/node/region heldout accuracy
- 방향성 confusion matrix: P(예측=B | 정답=A) ≠ P(예측=A | 정답=B)
- calibration ECE
- 정직성: abstain은 정답이 아니다 · 미측정 노드는 by_node에서 빠진다(0%가 아니다)
"""
import pytest

from app.arena.metrics import (
    Prediction,
    compute_metrics,
    confusion_matrix,
    expected_calibration_error,
)

REGIONS = {"visual_naturalize": "VISUAL", "text_naturalize": "DOCUMENT", "play_expand": "PLAY"}


def _p(gold, pred, conf=0.9, epid=None) -> Prediction:
    return Prediction(epid or f"EP_{gold}_{pred}", gold, pred, conf)


# --- accuracy ---


def test_accuracy_counts_only_exact_first_intent() -> None:
    preds = [_p("a", "a"), _p("a", "b"), _p("b", "b")]
    m = compute_metrics(preds, {}, ece_bins=10)
    assert m["first_intent_accuracy"] == pytest.approx(2 / 3, abs=1e-4)
    assert m["correct"] == 2 and m["item_count"] == 3


def test_abstain_is_wrong_but_counted_separately() -> None:
    """abstain(top=None)은 정답이 아니다 — 그러나 오답과 구분해 기록한다."""
    preds = [_p("a", "a"), _p("a", None, 0.0)]
    m = compute_metrics(preds, {}, ece_bins=10)
    assert m["first_intent_accuracy"] == 0.5
    assert m["abstain_count"] == 1


def test_unmeasured_node_absent_not_zero() -> None:
    """★ §7-6 Stage 0 = '노드 heldout 미측정'. 미측정과 0%는 다른 값이다."""
    m = compute_metrics([_p("visual_naturalize", "visual_naturalize")], REGIONS, ece_bins=10)
    assert set(m["by_node"]) == {"visual_naturalize"}
    assert "text_naturalize" not in m["by_node"]  # 0%로 채워 넣지 않는다


def test_by_region_aggregates_by_gold_domain() -> None:
    preds = [
        _p("visual_naturalize", "visual_naturalize", epid="E1"),
        _p("visual_naturalize", "text_naturalize", epid="E2"),
        _p("text_naturalize", "text_naturalize", epid="E3"),
    ]
    m = compute_metrics(preds, REGIONS, ece_bins=10)
    assert m["by_region"]["VISUAL"] == {"n": 2, "correct": 1, "accuracy": 0.5}
    assert m["by_region"]["DOCUMENT"] == {"n": 1, "correct": 1, "accuracy": 1.0}


def test_gold_intent_outside_ontology_excluded_from_regions() -> None:
    """온톨로지에 없는 라벨을 임의 region에 귀속시키지 않는다."""
    m = compute_metrics([_p("ghost_intent", "ghost_intent")], REGIONS, ece_bins=10)
    assert m["by_region"] == {}
    assert "ghost_intent" in m["by_node"]


def test_empty_predictions_yield_none_not_zero() -> None:
    m = compute_metrics([], REGIONS, ece_bins=10)
    assert m["first_intent_accuracy"] is None and m["ece"] is None
    assert m["item_count"] == 0


# --- 방향성 confusion matrix (§5-6) ---


def test_confusion_matrix_is_directional() -> None:
    """P(예측=B|정답=A) ≠ P(예측=A|정답=B) — 두 방향이 별개 행이고 rate 분모가 다르다."""
    preds = [
        _p("A", "B", epid="E1"), _p("A", "B", epid="E2"), _p("A", "A", epid="E3"),
        _p("B", "A", epid="E4"), _p("B", "B", epid="E5"), _p("B", "B", epid="E6"),
        _p("B", "B", epid="E7"),
    ]
    rows = {(r["from_true"], r["to_predicted"]): r for r in confusion_matrix(preds, confirm_min=2)}
    assert rows[("A", "B")]["confusion_rate"] == pytest.approx(2 / 3, abs=1e-4)  # 3건 중 2건
    assert rows[("B", "A")]["confusion_rate"] == pytest.approx(1 / 4, abs=1e-4)  # 4건 중 1건
    assert rows[("A", "B")]["confirmed"] is True    # count 2 ≥ confirm_min
    assert rows[("B", "A")]["confirmed"] is False   # count 1 < confirm_min


def test_abstain_makes_no_confusion_pair_but_stays_in_denominator() -> None:
    """abstain은 '다른 intent와 혼동'한 것이 아니다. 단 정답 A의 표본 수에는 포함된다."""
    preds = [_p("A", "B", epid="E1"), _p("A", None, 0.0, epid="E2")]
    rows = confusion_matrix(preds, confirm_min=1)
    assert len(rows) == 1
    assert rows[0]["from_true"] == "A" and rows[0]["to_predicted"] == "B"
    assert rows[0]["confusion_rate"] == 0.5  # 분모 2 (abstain 포함)


def test_confusion_matrix_order_is_deterministic() -> None:
    """같은 입력 → 같은 JSONB (replay 재현성의 전제)."""
    preds = [_p("A", "B", epid="E1"), _p("C", "D", epid="E2"), _p("A", "B", epid="E3")]
    assert confusion_matrix(preds, confirm_min=1) == confusion_matrix(preds, confirm_min=1)
    assert confusion_matrix(list(reversed(preds)), confirm_min=1) == confusion_matrix(
        preds, confirm_min=1
    )


# --- calibration (ECE) ---


def test_ece_zero_when_perfectly_calibrated() -> None:
    """신뢰도 1.0으로 전부 맞히면 ECE=0."""
    preds = [_p("a", "a", 1.0, epid=f"E{i}") for i in range(4)]
    assert expected_calibration_error(preds, bins=10) == 0.0


def test_ece_maximal_when_confidently_wrong() -> None:
    """신뢰도 1.0으로 전부 틀리면 ECE=1."""
    preds = [_p("a", "b", 1.0, epid=f"E{i}") for i in range(4)]
    assert expected_calibration_error(preds, bins=10) == 1.0


def test_ece_weights_buckets_by_size() -> None:
    """|acc−conf|의 표본수 가중평균 — 손계산과 일치."""
    preds = [
        _p("a", "a", 0.9, epid="E1"), _p("a", "a", 0.9, epid="E2"),  # 버킷 0.9: acc 1.0
        _p("a", "b", 0.1, epid="E3"),                                 # 버킷 0.1: acc 0.0
    ]
    # (2/3)*|1.0-0.9| + (1/3)*|0.0-0.1| = 0.0667 + 0.0333 = 0.1
    assert expected_calibration_error(preds, bins=10) == pytest.approx(0.1, abs=1e-3)


def test_ece_none_on_empty() -> None:
    assert expected_calibration_error([], bins=10) is None
