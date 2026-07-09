"""T3.3 decision 엔진 단위 테스트 (DB·HTTP 없음) — 사다리 각 분기를 결정론적으로 고정.

임계값은 config.decision.*에서 읽어 경계값을 만든다(코드에 리터럴 금지, 절대 규칙 1).
특히 clarify의 두 트리거(margin·confidence)를 각각 독립적으로 검증한다.
"""
from app.brain.decision import decide
from app.core.config import get_config

CFG = get_config()
D = CFG.decision


def test_empty_candidates_abstains_ood() -> None:
    out = decide(candidate_intents=[], top_activation=0.0, confidence=0.0, margin=0.0, config=CFG)
    assert out.decision == "abstain"
    assert out.abstain_reason == "OOD"


def test_weak_top_abstains_low_confidence() -> None:
    # top의 절대 강도가 abstain_score 미만이면 분포 confidence가 높아도 abstain
    out = decide(candidate_intents=["a", "b"], top_activation=D.abstain_score - 0.05,
                 confidence=0.9, margin=0.9, config=CFG)
    assert out.decision == "abstain"
    assert out.abstain_reason == "LOW_CONFIDENCE"


def test_low_margin_triggers_clarify() -> None:
    out = decide(candidate_intents=["a", "b"], top_activation=0.9,
                 confidence=D.clarify_confidence + 0.1,  # confidence 절은 False
                 margin=D.clarify_margin - 0.05, config=CFG)  # margin 절만 발동
    assert out.decision == "clarify"
    assert out.clarification is not None
    assert [o.intent_id for o in out.clarification.options] == ["a", "b"]


def test_low_confidence_alone_triggers_clarify() -> None:
    # margin은 충분하지만 confidence가 낮은 경우 — `or confidence < clarify_confidence` 절 단독 검증
    out = decide(candidate_intents=["a", "b", "c", "d"], top_activation=0.9,
                 confidence=D.clarify_confidence - 0.05,   # confidence 절 발동
                 margin=D.clarify_margin + 0.1, config=CFG)  # margin 절은 False
    assert out.decision == "clarify"
    assert len(out.clarification.options) == 2  # 상위 2개


def test_confident_suggests() -> None:
    out = decide(candidate_intents=["a", "b"], top_activation=0.9,
                 confidence=D.clarify_confidence + 0.2,
                 margin=D.clarify_margin + 0.2, config=CFG)
    assert out.decision == "suggest"
    assert out.clarification is None and out.abstain_reason is None


def test_clarify_budget_exhausted_degrades_to_suggest() -> None:
    # 세션 clarify 상한 소진 시 모호해도 clarify 대신 suggest (교사 피로 방지)
    out = decide(candidate_intents=["a", "b"], top_activation=0.9,
                 confidence=D.clarify_confidence + 0.1, margin=D.clarify_margin - 0.05,
                 config=CFG, prior_clarify_count=D.clarify_per_session_max)
    assert out.decision == "suggest"


def test_single_candidate_never_clarifies() -> None:
    # 후보가 1개면 양자택일 옵션을 만들 수 없다 — 모호해 보여도 clarify 아님
    out = decide(candidate_intents=["a"], top_activation=0.9, confidence=1.0, margin=0.0,
                 config=CFG)
    assert out.decision == "suggest"
