"""Promote / Reject 파이프라인 (§6-6·§8-2, T4.6).

Version Gate가 만든 candidate(T4.5)를 Arena 결과로 판정한다.

- promote 규칙: global 상승 ∧ region 회귀 없음 ∧ critical 악화 없음
  (config.version_gate.promote_rule로 이름을 고정 — 다른 규칙명이면 loud-fail).
- **promote: 노드 brightness(heldout_accuracy)를 Arena 결과로 갱신한다 — 이곳이 밝기의 유일한
  쓰기 지점이다(§8-2 'Arena = 3D 밝기의 유일한 원천', 원칙 8·절대 규칙 3).** pending 링 소등
  + Full Brain Resonance 이벤트 + candidate.decision='promote'.
- reject: brightness·pending 불변, evidence 전량 보존, 회귀 원인 리포트 + decision='reject'.

Arena run(Phase 5)이 호출자다 — 여기서는 결과(ArenaOutcome)를 받아 판정·적용만 한다. run_id는
그 arena run을 가리킨다(replay 무결성은 arena run이 4버전을 기록, §8-2).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import ExperimentsConfig
from app.models.brain import BrainNode, BrainVersion
from app.models.governance import GovernanceEvent

# 구현하는 promote 규칙의 이름 — config.version_gate.promote_rule과 일치해야 한다(구조 가드).
PROMOTE_RULE = "global_up_and_no_region_regression_and_no_critical_worse"
RESONANCE_EVENT = "FULL_BRAIN_RESONANCE"  # promote 순간의 시각 서명(§6-6)


@dataclass
class ArenaOutcome:
    """Arena run(Phase 5) 산출 — 판정 입력 + 노드별 밝기 원천."""

    run_id: str
    global_delta: float                 # pp; > 0 = global 상승
    region_regressions: list[str]       # 회귀한 region (비어 있어야 promote)
    critical_worse: list[str]           # 악화한 critical intent (비어 있어야 promote)
    node_heldout: dict[str, float]      # intent → heldout accuracy (밝기의 유일 원천)
    node_ece: dict[str, float] = field(default_factory=dict)  # intent → calibration ECE


@dataclass
class PromotionDecision:
    promote: bool
    reasons: list[str]                  # 차단 사유(promote면 빈 목록)


@dataclass
class ResolveResult:
    decision: str                       # promote | reject
    version: str
    reasons: list[str]
    nodes_brightened: int               # brightness를 갱신한 노드 수(reject면 0)


def _assert_rule(config: ExperimentsConfig) -> None:
    if config.version_gate.promote_rule != PROMOTE_RULE:
        raise ValueError(
            f"promote_rule '{config.version_gate.promote_rule}'는 이 구현({PROMOTE_RULE})과 다름"
        )


def evaluate_promotion(
    outcome: ArenaOutcome, config: ExperimentsConfig
) -> PromotionDecision:
    """§6-6 promote 규칙 평가 — 세 조건을 모두 만족해야 promote."""
    _assert_rule(config)
    reasons: list[str] = []
    if outcome.global_delta <= 0.0:
        reasons.append("global_not_up")     # global 상승 아님
    if outcome.region_regressions:
        reasons.append("region_regression")  # region 회귀 존재
    if outcome.critical_worse:
        reasons.append("critical_worse")     # critical 악화 존재
    return PromotionDecision(promote=not reasons, reasons=reasons)


def _apply_arena_brightness(session: Session, outcome: ArenaOutcome) -> int:
    """Arena 결과를 노드 밝기에 반영 — heldout·ece·last_arena_run + pending 링 소등.

    이것이 밝기(heldout_accuracy)를 쓰는 유일한 함수다(§8-2). 노드가 없으면 건너뛴다.
    """
    nodes = {
        n.intent_id: n for n in session.scalars(
            select(BrainNode).where(BrainNode.intent_id.in_(list(outcome.node_heldout)))
        )
    }
    count = 0
    for intent, acc in outcome.node_heldout.items():
        node = nodes.get(intent)
        if node is None:
            continue
        node.heldout_accuracy = acc
        # ECE는 이 run의 값으로 덮되, 없으면 None으로 지운다 — heldout·last_arena_run은 새 run인데
        # ECE만 이전 run 값이 남아 오귀속되는 내부 불일치를 막는다(리뷰 MINOR).
        node.calibration_ece = outcome.node_ece.get(intent)
        node.last_arena_run = outcome.run_id
        node.pending_evaluation = False     # ring 소등 — "훈련됨·검증 대기"가 검증됨(§6-7 [9])
        count += 1
    session.flush()
    return count


def _promoted_version(session: Session) -> str:
    """promote 시 부여할 깨끗한 단조 버전명 — rc 접미사 누적을 막는다(§6-6 clean 버전).

    seed→첫 promote='v1', 이후 'v2'…. 다음 candidate는 이 이름 위에 '-rc{n}'을 붙이므로
    'v1-rc1'→promote→'v2'로 이어져 접미사가 겹치지 않는다.
    """
    n = int(session.scalar(
        select(func.count()).select_from(BrainVersion).where(BrainVersion.decision == "promote")
    ) or 0)
    return f"v{n + 1}"


def resolve_candidate(
    session: Session,
    candidate: BrainVersion,
    outcome: ArenaOutcome,
    config: ExperimentsConfig,
    *,
    approved_by: str = "arena",
) -> ResolveResult:
    """candidate를 Arena 결과로 판정 — promote면 밝기 갱신·소등·Resonance, reject면 보존·리포트."""
    if candidate.decision != "candidate":
        raise ValueError(f"이미 판정된 버전({candidate.version}, decision={candidate.decision})")

    decision = evaluate_promotion(outcome, config)
    arena_result: dict = {
        "run_id": outcome.run_id,
        "global_delta": outcome.global_delta,
        "region_regressions": list(outcome.region_regressions),
        "critical_worse": list(outcome.critical_worse),
    }

    if not decision.promote:
        # reject: brightness·pending·evidence 불변. 회귀 원인 리포트만 남긴다.
        arena_result["report"] = {
            "reasons": decision.reasons,
            "regressed": list(outcome.region_regressions) + list(outcome.critical_worse),
        }
        candidate.decision = "reject"
        candidate.arena_result = arena_result
        session.flush()
        return ResolveResult("reject", candidate.version, decision.reasons, 0)

    # promote: 밝기의 유일 쓰기 지점 + ring 소등 + Resonance + decision 승격
    brightened = _apply_arena_brightness(session, outcome)
    candidate.version = _promoted_version(session)  # rc 접미사 누적 방지(§6-6 clean 버전)
    candidate.decision = "promote"
    candidate.arena_result = arena_result
    session.add(GovernanceEvent(
        event_id="GOV_" + uuid.uuid4().hex[:12],
        event_type=RESONANCE_EVENT,
        payload={
            "version": candidate.version, "base": candidate.base,
            "global_delta": outcome.global_delta, "run_id": outcome.run_id,
            "nodes_brightened": brightened,
        },
        approved_by=approved_by,
    ))
    session.flush()
    return ResolveResult("promote", candidate.version, [], brightened)
