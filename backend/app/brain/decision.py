"""Decision 정책 엔진 (runtime §4). gym·shadow 공용 — 임계값은 config.decision.*(절대 규칙 1).

사다리(약→강): abstain(너무 약함/분포 밖) → clarify(모호) → suggest(확신).
execute(Stage 3 auto)와 Suggest/Assist/Auto live rollout 서빙은 여기서 만들지 않는다
(CLAUDE.md PARTIAL HOLD) — emit하는 'suggest'는 브레인의 판정 라벨일 뿐 실서비스 자동 실행이 아니다.
brightness·훈련 상태는 건드리지 않는다(절대 규칙 3 — 이 엔진은 읽기 판정만).

abstain 판정은 정규화 confidence가 아니라 top의 절대 강도(top_activation)를 본다: 단일 후보는
정규화상 confidence=1.0이 되어 약한 후보를 실행으로 오판할 수 있기 때문이다(§5-5, T3.2 F3).
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from app.contracts.infer_response import Clarification, ClarificationOption
from app.core.config import ExperimentsConfig

Decision = Literal["suggest", "clarify", "abstain"]
AbstainReason = Literal["LOW_CONFIDENCE", "OOD", "DEADLINE_RISK"]


@dataclass
class DecisionOutcome:
    decision: Decision
    abstain_reason: AbstainReason | None = None
    clarification: Clarification | None = None


def decide(
    *,
    candidate_intents: list[str],
    top_activation: float,
    confidence: float,
    margin: float,
    config: ExperimentsConfig,
    prior_clarify_count: int = 0,
) -> DecisionOutcome:
    """정규화 신호(confidence/margin) + 절대 강도(top_activation)로 decision을 고른다.

    prior_clarify_count: 같은 세션에서 이미 낸 clarify 수(피로 방지 상한
    decision.clarify_per_session_max). 현 Core 계약엔 세션별 clarify 이력이 없어 라우터는 0을
    넘긴다 — 세션 상태 적재는 후속 과제.
    """
    d = config.decision
    if not candidate_intents:
        return DecisionOutcome("abstain", abstain_reason="OOD")  # 후보 없음 = 분포 밖
    if top_activation < d.abstain_score:
        return DecisionOutcome("abstain", abstain_reason="LOW_CONFIDENCE")
    ambiguous = margin < d.clarify_margin or confidence < d.clarify_confidence
    can_clarify = len(candidate_intents) >= 2 and prior_clarify_count < d.clarify_per_session_max
    if ambiguous and can_clarify:
        return DecisionOutcome("clarify", clarification=_clarification(candidate_intents))
    return DecisionOutcome("suggest")


def _clarification(candidate_intents: list[str]) -> Clarification:
    # 상위 2개 후보로 양자택일 옵션(계약상 정확히 2개). 라벨은 UI가 친화 명칭으로 매핑(T3.6).
    options = [ClarificationOption(label=i, intent_id=i) for i in candidate_intents[:2]]
    return Clarification(question="어느 쪽에 가깝나요?", options=options)
