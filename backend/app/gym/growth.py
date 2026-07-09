"""세션 종료 후 성장 반영 — §6-7 Trace [5][6] (T4.3).

[5] 세션이 만든 GYM_HUMAN 에피소드를 Label Aggregator(§3-6)로 흘린다. 전이 조건은 §3-6
    그대로 '최소 신호 수 도달'(config.label_aggregator.min_label_functions) — 미달 에피소드는
    EVIDENCE_ACCUMULATING에 남아 다음 트레이너의 신호를 기다린다(§6-7 [5] 2인 일치 경로).
    도달분만 AGGREGATION_READY → LABEL_CANDIDATE|REVIEW_REQUIRED로 전이하고 tier를 산출한다.
    (LABELED/GOLD 승격은 사람 2인 검수 소관 §3-3 — 자동 클릭-투-트레인 루프 밖.)
[6] 노드 evidence_stats(size·density)를 재집계하고, **훈련이 실제로 있었을 때만**(세션이
    evidence를 만든 경우) pending_evaluation 링을 켠다(§6-5 '훈련됨·검증 대기' — 빈 제출에
    링을 켜면 거짓 상태다).

**절대 규칙 3 · 원칙 8: 이 파이프라인은 brightness(heldout_accuracy·calibration_ece·
last_arena_run)를 절대 읽지도 쓰지도 갱신하지도 않는다 — 밝기의 원천은 Arena뿐이다.**
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.aggregator.aggregator import aggregate, apply_aggregation, signals_from_rows
from app.aggregator.state_machine import advance_label_state
from app.brain.backfill import aggregate_evidence_stats
from app.core.config import ExperimentsConfig
from app.models.brain import BrainNode
from app.models.episodes import Episode, Evidence
from app.models.gym import ChallengePack, GymSession


@dataclass
class FinalizeReport:
    node_intent: str | None
    episodes_aggregated: int   # 이번 호출로 전이(집계)된 에피소드 수
    label_states: dict[str, int] = field(default_factory=dict)  # 세션 에피소드의 사후 상태 분포
    pending_set: bool = False


def _session_episode_ids(gym_session: GymSession) -> list[str]:
    """submit_results가 results.responses에 남긴 에피소드 id (없으면 빈 목록)."""
    responses = (gym_session.results or {}).get("responses", [])
    return [r["episode_id"] for r in responses if r.get("episode_id")]


def _pack_node(session: Session, gym_session: GymSession) -> str | None:
    """세션 pack의 origin.node — pending 링을 켤 대상 노드."""
    if not gym_session.pack_id:
        return None
    pack = session.get(ChallengePack, gym_session.pack_id)
    return (pack.origin or {}).get("node") if pack else None


def finalize_session(
    session: Session, gym_session: GymSession, config: ExperimentsConfig
) -> FinalizeReport:
    """§6-7 [5][6]: 세션 에피소드 집계 + 노드 size/density 갱신 + pending 링. brightness 불변."""
    # [5] 신호 수가 §3-6 '최소 신호 수'에 도달한 에피소드만 전이 — 미달은 축적 유지
    min_signals = config.label_aggregator.min_label_functions
    label_states: dict[str, int] = {}
    aggregated = 0
    episode_ids = _session_episode_ids(gym_session)
    for ep_id in episode_ids:
        ep = session.get(Episode, ep_id)
        if ep is None:
            continue
        if ep.label_state != "EVIDENCE_ACCUMULATING":
            # 이미 전이된 에피소드(예: 다른 세션이 방금 집계)는 재처리하지 않는다(멱등)
            label_states[ep.label_state] = label_states.get(ep.label_state, 0) + 1
            continue
        rows = session.scalars(select(Evidence).where(Evidence.episode_id == ep_id)).all()
        result = aggregate(signals_from_rows(rows), config)
        if result.signal_count < min_signals:
            # §3-6: 전이 조건 '최소 신호 수 도달' 미충족 — 다음 트레이너 신호를 기다린다
            label_states[ep.label_state] = label_states.get(ep.label_state, 0) + 1
            continue
        advance_label_state(ep, "AGGREGATION_READY")
        apply_aggregation(ep, result, config)  # → LABEL_CANDIDATE|REVIEW_REQUIRED + tier(≤SILVER)
        label_states[ep.label_state] = label_states.get(ep.label_state, 0) + 1
        aggregated += 1
    session.flush()

    # [6] 노드 반영: size/density 재집계 + pending ring. brightness는 건드리지 않는다.
    node_intent = _pack_node(session, gym_session)
    aggregate_evidence_stats(session)  # 전체 노드 evidence_stats 재계산 (새 HUMAN evidence 반영)
    pending_set = False
    if node_intent and episode_ids:  # 훈련이 실제로 있었을 때만 — 빈 제출에 링은 거짓(§6-5)
        node = session.scalar(select(BrainNode).where(BrainNode.intent_id == node_intent))
        if node is not None:
            node.pending_evaluation = True  # §6-5 훈련됨·검증 대기 (규칙 3이 허용하는 필드)
            pending_set = True
    session.flush()

    return FinalizeReport(
        node_intent=node_intent, episodes_aggregated=aggregated,
        label_states=label_states, pending_set=pending_set,
    )
