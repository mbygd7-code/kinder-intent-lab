"""T5.2/T5.3 AC (§8-2·§5-6) + 게이트 지표 (§10-2, 2026-07-10 확정): Arena 지표 순수 계산.

- global/node/region heldout accuracy
- 방향성 confusion matrix: P(예측=B | 정답=A) ≠ P(예측=A | 정답=B)
- calibration ECE
- 1-Turn Recovery (분모=clarify)
- CWAR 양방향(fire/miss) + Critical Commit Coverage
- 정직성: abstain은 정답이 아니다 · 미측정은 by_node/by_intent에서 빠진다(0%가 아니다)
"""
import pytest

from app.arena.metrics import (
    Prediction,
    compute_metrics,
    confusion_matrix,
    critical_metrics,
    decision_counts,
    expected_calibration_error,
    recovery_rate,
)

REGIONS = {"visual_naturalize": "VISUAL", "text_naturalize": "DOCUMENT", "play_expand": "PLAY"}
CRIT = ["op_workspace_delete", "op_notice_send"]


def _p(gold, pred, conf=0.9, epid=None, decision=None, top2=None) -> Prediction:
    return Prediction(
        epid or f"EP_{gold}_{pred}", gold, pred, conf,
        decision=decision, clarify_top2=tuple(top2) if top2 else None,
    )


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


# --- 1-Turn Recovery (§10-2 레그 3) ---


def test_recovery_numerator_is_gold_in_clarify_top2() -> None:
    """clarify 한 번으로 정답이 드러나면 복구다 — decision.py가 정확히 top-2를 제시한다."""
    preds = [
        _p("a", "b", epid="E1", decision="clarify", top2=["b", "a"]),   # 복구됨
        _p("a", "b", epid="E2", decision="clarify", top2=["b", "c"]),   # 복구 실패
    ]
    r = recovery_rate(preds)
    assert r == {"rate": 0.5, "numerator": 1, "denominator": 2}


def test_recovery_excludes_suggest_and_abstain() -> None:
    """★ Recovery는 clarify라는 *행동*의 품질이다 — suggest·abstain은 분자·분모 모두에서 뺀다."""
    preds = [
        _p("a", "a", epid="E1", decision="suggest"),
        _p("a", None, 0.0, epid="E2", decision="abstain"),
        _p("a", "b", epid="E3", decision="clarify", top2=["b", "a"]),
    ]
    r = recovery_rate(preds)
    assert r["denominator"] == 1 and r["rate"] == 1.0


def test_recovery_null_when_no_clarify() -> None:
    """clarify가 하나도 없으면 0%가 아니라 null — 측정 대상이 없는 것과 나쁜 것은 다르다."""
    assert recovery_rate([_p("a", "a", epid="E1", decision="suggest")]) is None


def test_recovery_null_for_legacy_run_without_decision() -> None:
    """decision을 기록하지 않은 과거 run은 소급 계산하지 않는다(백필 금지)."""
    assert recovery_rate([_p("a", "b", epid="E1")]) is None


# --- CWAR 양방향 + Critical Commit Coverage (§10-2 레그 2) ---


def test_cwar_fire_counts_only_committed_critical() -> None:
    """★ CWAR-fire = P(오발 | critical을 커밋함). abstain·clarify는 fire가 아니다."""
    preds = [
        # 커밋한 critical 3건 중 1건 오발
        _p("op_notice_send", "op_notice_send", epid="E1", decision="suggest"),
        _p("op_workspace_delete", "op_workspace_delete", epid="E2", decision="suggest"),
        _p("play_expand", "op_workspace_delete", epid="E3", decision="suggest"),   # 오발 ★
        # clarify/abstain으로 흘린 critical 예측은 분모에도 안 들어간다
        _p("play_expand", "op_notice_send", epid="E4", decision="clarify",
           top2=["op_notice_send", "play_expand"]),
        _p("op_notice_send", None, 0.0, epid="E5", decision="abstain"),
    ]
    m = critical_metrics(preds, CRIT)
    assert m["cwar_fire_n"] == 3 and m["cwar_fire_wrong"] == 1
    assert m["cwar_fire"] == pytest.approx(1 / 3, abs=1e-4)


def test_cwar_miss_catches_unmasked_child_failure() -> None:
    """★ 2026-07-10 결정: fire 방향만으로는 '정답이 critical인데 놓침'을 구조적으로 못 본다.

    여기서 op_workspace_delete가 정답인데 play_expand로 오인식 → fire 방향엔 흔적이 없다.
    """
    preds = [
        _p("op_workspace_delete", "play_expand", epid="E1", decision="suggest"),  # miss ★
        _p("op_notice_send", "op_notice_send", epid="E2", decision="suggest"),
        _p("op_notice_send", None, 0.0, epid="E3", decision="abstain"),            # abstain도 miss
    ]
    m = critical_metrics(preds, CRIT)
    assert m["cwar_fire_n"] == 1 and m["cwar_fire"] == 0.0  # fire 방향은 깨끗하다
    assert m["cwar_miss_n"] == 3 and m["cwar_miss_wrong"] == 2
    assert m["cwar_miss"] == pytest.approx(2 / 3, abs=1e-4)  # ★ miss 방향만이 잡는다


def test_ccc_closes_the_coward_and_laundering_paths() -> None:
    """★ 쉬운 critical만 fire하고 어려운 건 흘리면 CWAR-fire=0이지만 CCC가 잡는다."""
    preds = [
        _p("op_notice_send", "op_notice_send", epid="E1", decision="suggest"),      # 커밋
        _p("op_workspace_delete", "op_workspace_delete", epid="E2", decision="clarify",
           top2=["op_workspace_delete", "play_expand"]),                            # 세탁
        _p("op_workspace_delete", None, 0.0, epid="E3", decision="abstain"),        # 겁쟁이
        _p("op_notice_send", None, 0.0, epid="E4", decision="abstain"),
    ]
    m = critical_metrics(preds, CRIT)
    assert m["cwar_fire"] == 0.0          # 커밋한 1건은 정답 — fire 방향은 완벽해 보인다
    assert m["o_count"] == 4
    assert m["ccc"] == 0.25               # 4건 중 1건만 실제로 커밋 → 하한(0.80) 미달 → FAIL
    # E2는 top-1이 정답이므로 miss가 아니다(clarify했을 뿐 인식은 했다). abstain 2건만 miss.
    # → 세탁(clarify)은 CWAR-miss로는 안 잡히고 **CCC만이** 잡는다. 두 지표는 상보적이다.
    assert m["cwar_miss"] == 0.5


def test_cwar_null_when_critical_set_empty() -> None:
    """critical 집합이 비면 안전을 주장할 근거가 없다 — 0%가 아니라 null."""
    m = critical_metrics([_p("a", "a", epid="E1", decision="suggest")], [])
    assert m["cwar_fire"] is None and m["cwar_miss"] is None and m["ccc"] is None
    assert m["critical_set_size"] == 0


def test_cwar_null_for_legacy_run_without_decision() -> None:
    assert critical_metrics([_p("op_notice_send", "op_notice_send")], CRIT)["cwar_fire"] is None


def test_cwar_null_when_no_critical_fired_or_gold() -> None:
    """critical을 한 번도 커밋하지 않고 정답에도 없으면 두 방향 모두 null (0%가 아니다)."""
    m = critical_metrics([_p("play_expand", "play_expand", epid="E1", decision="suggest")], CRIT)
    assert m["cwar_fire"] is None and m["cwar_miss"] is None and m["ccc"] is None
    assert m["o_count"] == 0 and m["by_intent"] == {}


def test_by_intent_omits_unobserved_critical_intents() -> None:
    """★ 관측되지 않은 critical intent는 by_intent에서 빠진다 — 0% 오발로 읽히면 안 된다."""
    preds = [_p("op_notice_send", "op_notice_send", epid="E1", decision="suggest")]
    m = critical_metrics(preds, CRIT)
    assert set(m["by_intent"]) == {"op_notice_send"}
    assert "op_workspace_delete" not in m["by_intent"]


# --- abstain 2종 구분 (구현 리뷰에서 확인된 결함의 회귀 테스트) ---
#
# decide()는 `top_activation < config.decision.abstain_score`면 abstain을 내는데, 그때도
# `predicted_intent`(argmax)는 남아 있다. 즉 `decision=='abstain'`과 `predicted_intent is None`은
# 다른 사건이다. 둘을 한 숫자에 섞으면 지표가 거짓말한다.


def _weak_abstain(gold, pred, epid):
    """argmax는 정답을 짚었지만 강도가 낮아 행동하지 않기로 한 아이템 (decision abstain)."""
    return _p(gold, pred, 0.2, epid=epid, decision="abstain")


def test_decision_abstain_keeps_predicted_intent() -> None:
    """★ decision='abstain'이어도 predicted_intent는 남는다 — no-candidate abstain과 다른 사건."""
    p = _weak_abstain("op_workspace_delete", "op_workspace_delete", "E1")
    assert p.decision == "abstain" and p.predicted_intent == "op_workspace_delete"
    assert p.correct is True        # 인식은 성공했다
    assert p.committed is False     # 그러나 행동은 커밋하지 않았다


def test_capability_metric_stays_pure_argmax() -> None:
    """★ first_intent_accuracy는 decision과 무관한 순수 argmax다.

    안 그러면 `config.decision.abstain_score`를 만지는 것만으로 노드 밝기(heldout)가 조용히
    바뀌고, decision 엔진을 돌리지 않는 zero-shot 베이스라인과 비교할 수 없게 된다(§8-2).
    """
    preds = [_weak_abstain("a", "a", "E1"), _p("b", "b", epid="E2", decision="suggest")]
    m = compute_metrics(preds, {}, ece_bins=10)
    assert m["first_intent_accuracy"] == 1.0  # ★ decision abstain이 능력 지표를 깎지 않는다
    assert m["abstain_count"] == 0            # no-candidate가 아니다
    # compute_metrics는 decision을 담지 않는다(베이스라인과 공유하는 순수 능력 지표다).
    assert "decisions" not in m


def test_decision_counts_surfaces_decision_level_abstain() -> None:
    """★ abstain_count(=후보 0)가 0이어도 decision abstain은 decisions에서 드러난다."""
    preds = [
        _weak_abstain("a", "a", "E1"),
        _p("b", "b", epid="E2", decision="suggest"),
        _p("c", "d", epid="E3", decision="clarify", top2=["d", "c"]),
        _p("e", None, 0.0, epid="E4", decision="abstain"),   # no-candidate
    ]
    assert decision_counts(preds) == {"suggest": 1, "clarify": 1, "abstain": 2}
    assert compute_metrics(preds, {}, ece_bins=10)["abstain_count"] == 1  # 후보 0인 1건만
    assert decision_counts([_p("a", "a", epid="E1")]) is None             # 미기록 run은 null


def test_decision_abstain_on_critical_is_not_a_miss_but_kills_ccc() -> None:
    """★ 리뷰 지적의 핵심: 인식 성공 + 미커밋은 CWAR-miss가 아니라 **CCC**가 잡는다.

    비가역 삭제(op_workspace_delete)를 약하게 맞혔지만 행동하지 않은 브레인:
    - 인식은 했으니 CWAR-miss(인식 재현율)는 벌하지 않는다
    - 그러나 커밋하지 않았으므로 CCC가 0으로 떨어져 안전 레그가 FAIL한다
    """
    preds = [_weak_abstain("op_workspace_delete", "op_workspace_delete", "E1")]
    m = critical_metrics(preds, CRIT)
    assert m["o_count"] == 1
    assert m["cwar_miss"] == 0.0              # 인식은 성공 — 미마스킹 류 실패가 아니다
    assert m["ccc"] == 0.0                    # ★ 커밋 0% → 안전 레그 FAIL
    assert m["recognized_not_committed"] == 1
    assert m["cwar_fire"] is None             # critical을 fire한 적이 없다
    assert m["by_intent"]["op_workspace_delete"]["gold_committed"] == 0


def test_no_candidate_abstain_on_critical_is_a_miss() -> None:
    """반면 후보를 아예 못 낸 abstain은 **인식 실패** — CWAR-miss가 잡는다."""
    preds = [_p("op_workspace_delete", None, 0.0, epid="E1", decision="abstain")]
    m = critical_metrics(preds, CRIT)
    assert m["cwar_miss"] == 1.0 and m["ccc"] == 0.0
    assert m["recognized_not_committed"] == 0
