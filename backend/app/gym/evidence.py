"""Gym 모드 → evidence 의미 (§8-1). 절대 규칙 6·9·10 준수.

- Guess My Intent / Choose the Right Meaning: 트레이너가 의도를 고름 → HUMAN_CONFIRMATION
- Correction Drill: 브레인 오답을 트레이너가 교정 → HUMAN_CORRECTION
- 전부 actor_type=TEACHER_TRAINER, polarity=supports(트레이너가 고른 intent), adversarial=false
  (Break the Brain만 adversarial=true — 이 티켓의 3모드엔 없음).
- strength는 config.gym.evidence_strength (aggregator 가중 입력 — 고정 서열 금지, 절대 규칙 10).
"""
from __future__ import annotations

# 모드 → evidence_type. 3모드만 — 나머지 delivery_mode는 후속 티켓.
_MODE_EVIDENCE_TYPE: dict[str, str] = {
    "guess_my_intent": "HUMAN_CONFIRMATION",
    "choose_right_meaning": "HUMAN_CONFIRMATION",
    "correction_drill": "HUMAN_CORRECTION",
}

GYM_ACTOR_TYPE = "TEACHER_TRAINER"


def evidence_type_for(mode: str) -> str:
    """모드의 evidence_type. 미지원 모드는 오류(조용히 잘못된 타입 적재 방지)."""
    try:
        return _MODE_EVIDENCE_TYPE[mode]
    except KeyError:
        raise ValueError(f"지원하지 않는 gym 모드: {mode!r}") from None
