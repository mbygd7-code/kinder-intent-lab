"""Label State Machine — §3-6 상태 전이 그대로 (절대 규칙 8: tier와 혼용하지 않는다).

UNLABELED → EVIDENCE_ACCUMULATING → AGGREGATION_READY
  → LABEL_CANDIDATE  (Aggregator 게이트 통과)
  → REVIEW_REQUIRED  (conflict 초과 or 저신뢰)
  → LABELED / REJECTED (사람 검수)

전이는 advance_label_state() 단일 경로로만 한다 — 순서를 건너뛰는 전이는 거부.
(에피소드를 특정 상태로 '생성'하는 것은 전이가 아니므로 여기서 막지 않는다.)
"""
from __future__ import annotations

from app.contracts.episode import LabelState

ALLOWED_TRANSITIONS: dict[str, set[str]] = {
    "UNLABELED": {"EVIDENCE_ACCUMULATING"},
    "EVIDENCE_ACCUMULATING": {"AGGREGATION_READY"},
    "AGGREGATION_READY": {"LABEL_CANDIDATE", "REVIEW_REQUIRED"},
    # LABEL_CANDIDATE·REVIEW_REQUIRED는 사람 검수를 거쳐 LABELED/REJECTED로만 간다 (§3-6 그대로)
    "LABEL_CANDIDATE": {"LABELED", "REJECTED"},
    "REVIEW_REQUIRED": {"LABELED", "REJECTED"},
    "LABELED": set(),
    "REJECTED": set(),
}

# 계약 enum과 상태 기계가 완전히 동일한 상태 집합을 다루는지 import 시점에 고정
_VALID_STATES = set(LabelState.__args__)  # type: ignore[attr-defined]
if set(ALLOWED_TRANSITIONS) != _VALID_STATES:  # -O에서도 스트립되지 않도록 assert 대신 raise
    raise RuntimeError("state machine ↔ LabelState enum 불일치")


class IllegalTransition(Exception):
    """§3-6에서 허용되지 않는 label_state 전이."""


def can_transition(src: str, dst: str) -> bool:
    return dst in ALLOWED_TRANSITIONS.get(src, set())


def assert_transition(src: str, dst: str) -> None:
    if src not in ALLOWED_TRANSITIONS:
        raise IllegalTransition(f"알 수 없는 상태: {src!r}")
    if dst not in _VALID_STATES:
        raise IllegalTransition(f"알 수 없는 상태: {dst!r}")
    if not can_transition(src, dst):
        raise IllegalTransition(f"허용되지 않는 전이: {src} → {dst} (§3-6)")


def is_terminal(state: str) -> bool:
    return ALLOWED_TRANSITIONS.get(state) == set()


def advance_label_state(episode, dst: str) -> None:
    """episode.label_state를 dst로 전이 (검증 후 대입). 위반 시 상태 불변."""
    assert_transition(episode.label_state, dst)
    episode.label_state = dst
