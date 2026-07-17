"""공부 데이터 웹 검수 — /v1/review (투트랙 세트 ③, 2026-07-17 사용자 승인).

YAML 검수(run_human_review)의 웹 판. 표(votes)는 review_votes에 모으고, 적용은
`aggregator.review.apply_review_batch`(GOLD **유일문**)에 그대로 넣는다 — 이 라우터는
승격 규칙(2인·만장일치·배치 kappa)을 재구현하지 않는다. 우회 경로 없음(§3-3).

- 큐는 **blind**: 다른 검수자의 표·집계 제안(_aggregator_suggests류)을 절대 싣지 않는다
  (앵커링 방지 — 벤치마크 2차 blind와 같은 원칙). 발화·언어·채널만 준다.
- 한 사람 한 표: (episode_id, canonical) 유니크 — 재제출은 갱신. 별칭 위장 불가.
- 적용 성공 시 run_backfill(대표 예문) 자동 체인 — run_human_review --apply와 동일.
"""
from __future__ import annotations

import uuid
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.aggregator.review import (
    REVIEWABLE_STATES,
    ReviewBatchRejected,
    ReviewVote,
    apply_review_batch,
    canonical_reviewer,
)
from app.aggregator.state_machine import IllegalTransition
from app.brain.backfill import run_backfill
from app.core.config import ExperimentsConfig, get_config
from app.core.db import get_session
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.llm.client import embed_fn_from_env
from app.models.episodes import Episode, ReviewVoteRow

router = APIRouter(prefix="/v1/review", tags=["review"])


def _get_experiments() -> ExperimentsConfig:
    return get_config()


@lru_cache(maxsize=1)
def get_review_embed():
    """backfill 체인용 임베딩 seam — 테스트가 dependency_overrides로 대체한다."""
    return embed_fn_from_env()


def _real_intents() -> set[str]:
    return {i.intent_id for i in load_ontology().intents if i.intent_id != UNKNOWN_INTENT_ID}


def _reviewable_q():
    return select(Episode).where(Episode.label_state.in_(sorted(REVIEWABLE_STATES)))


# --- 큐 (blind) ---


class QueueItem(BaseModel):
    episode_id: str
    teacher_prompt: str
    lang: str
    origin_channel: str


class QueueOut(BaseModel):
    reviewer: str          # 정규화 신원 — 표는 이 이름으로 쌓인다
    total_reviewable: int
    my_done: int
    items: list[QueueItem]


@router.get("/queue", response_model=QueueOut)
def review_queue(
    reviewer: str,
    limit: int = 50,
    session: Session = Depends(get_session),
) -> QueueOut:
    canon = canonical_reviewer(reviewer)
    if not canon:
        raise HTTPException(status_code=422, detail="검수자 이름을 입력해주세요")

    total = session.scalar(select(func.count()).select_from(_reviewable_q().subquery()))
    my_voted = set(session.scalars(
        select(ReviewVoteRow.episode_id).where(ReviewVoteRow.reviewer_canonical == canon)
    ))
    rows = session.scalars(_reviewable_q().order_by(Episode.episode_id)).all()
    items = [
        QueueItem(episode_id=e.episode_id, teacher_prompt=e.teacher_prompt,
                  lang=e.lang, origin_channel=e.origin_channel)
        for e in rows if e.episode_id not in my_voted
    ][:limit]
    my_done = sum(1 for e in rows if e.episode_id in my_voted)
    return QueueOut(reviewer=canon, total_reviewable=total or 0, my_done=my_done, items=items)


# --- 표 제출 ---


class VoteIn(BaseModel):
    reviewer: str
    episode_id: str
    chosen_intent: str | None = None  # null = 폐기(REJECTED) 표


class VoteOut(BaseModel):
    ok: bool
    vote_id: str
    updated: bool  # 같은 사람의 재제출(갱신)이었는가


@router.post("/vote", response_model=VoteOut)
def submit_vote(payload: VoteIn, session: Session = Depends(get_session)) -> VoteOut:
    canon = canonical_reviewer(payload.reviewer)
    if not canon:
        raise HTTPException(status_code=422, detail="검수자 이름을 입력해주세요")
    episode = session.get(Episode, payload.episode_id)
    if episode is None:
        raise HTTPException(status_code=404, detail="에피소드를 찾을 수 없어요")
    if episode.label_state not in REVIEWABLE_STATES:
        raise HTTPException(status_code=409, detail="이미 확정됐거나 검수 대상이 아니에요")
    if payload.chosen_intent is not None and payload.chosen_intent not in _real_intents():
        raise HTTPException(status_code=422, detail="온톨로지에 없는 의도예요 — 목록에서 골라주세요")

    existing = session.scalar(
        select(ReviewVoteRow).where(
            ReviewVoteRow.episode_id == payload.episode_id,
            ReviewVoteRow.reviewer_canonical == canon,
        )
    )
    if existing is not None:
        existing.chosen_intent = payload.chosen_intent
        existing.reviewer_ref = payload.reviewer
        session.flush()
        return VoteOut(ok=True, vote_id=existing.vote_id, updated=True)

    vote = ReviewVoteRow(
        vote_id="RV_" + uuid.uuid4().hex[:12],
        episode_id=payload.episode_id,
        reviewer_canonical=canon,
        reviewer_ref=payload.reviewer,
        chosen_intent=payload.chosen_intent,
    )
    session.add(vote)
    session.flush()
    return VoteOut(ok=True, vote_id=vote.vote_id, updated=False)


# --- 적용 (GOLD 유일문 경유 + backfill 체인) ---


class ApplyIn(BaseModel):
    approved_by: str


class ApplyOut(BaseModel):
    labeled: int
    rejected: int
    unchanged: int
    kappa: float | None
    exemplars_added: int
    message: str


@router.post("/apply", response_model=ApplyOut)
def apply_votes(
    payload: ApplyIn,
    session: Session = Depends(get_session),
    config: ExperimentsConfig = Depends(_get_experiments),
    embed=Depends(get_review_embed),
) -> ApplyOut:
    if not payload.approved_by.strip():
        raise HTTPException(status_code=422, detail="승인자 이름을 입력해주세요")

    reviewable_ids = set(session.scalars(
        select(Episode.episode_id).where(Episode.label_state.in_(sorted(REVIEWABLE_STATES)))
    ))
    rows = [
        r for r in session.scalars(select(ReviewVoteRow)).all()
        if r.episode_id in reviewable_ids
    ]
    if not rows:
        raise HTTPException(status_code=409, detail="적용할 검수 표가 없어요")
    distinct = {r.reviewer_canonical for r in rows}
    if len(distinct) < config.review.min_reviewers:
        raise HTTPException(
            status_code=409,
            detail=f"검수자 {config.review.min_reviewers}인 이상의 표가 필요해요 — "
                   f"지금은 {len(distinct)}인이에요 (1인 확정 금지 §3-3)",
        )

    votes = [
        ReviewVote(episode_id=r.episode_id, reviewer_ref=r.reviewer_ref,
                   chosen_intent=r.chosen_intent)
        for r in rows
    ]
    try:
        report = apply_review_batch(session, votes, config, approved_by=payload.approved_by)
    except (ReviewBatchRejected, IllegalTransition) as exc:
        # 배치 전량 거부 — 아무것도 확정하지 않는다(부분 승격 금지). 문구 그대로 안내.
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    # GOLD가 생겼으면 대표 예문 자동 체인(run_human_review --apply와 동일) — 별도 원자성:
    # 여기 실패해도 검수 확정은 유지되고, backfill은 멱등이라 다음 적용에서 따라잡는다.
    exemplars = 0
    if report.labeled:
        exemplars = run_backfill(
            session, config, approved_by=payload.approved_by, embed_fn=embed
        ).exemplars_selected

    return ApplyOut(
        labeled=report.labeled, rejected=report.rejected, unchanged=report.unchanged,
        kappa=report.kappa, exemplars_added=exemplars,
        message=(
            f"확정 {report.labeled}건(GOLD) · 폐기 {report.rejected}건 · 보류 {report.unchanged}건"
            + (f" · 대표 예문 +{exemplars}" if exemplars else "")
        ),
    )


# --- 상태 ---


class ReviewerStat(BaseModel):
    name: str
    votes: int


class StatusOut(BaseModel):
    reviewable_total: int
    ready_total: int  # 서로 다른 2인 이상의 표가 모인 에피소드 수
    reviewers: list[ReviewerStat]


@router.get("/status", response_model=StatusOut)
def review_status(
    session: Session = Depends(get_session),
    config: ExperimentsConfig = Depends(_get_experiments),
) -> StatusOut:
    reviewable_ids = set(session.scalars(
        select(Episode.episode_id).where(Episode.label_state.in_(sorted(REVIEWABLE_STATES)))
    ))
    rows = [
        r for r in session.scalars(select(ReviewVoteRow)).all()
        if r.episode_id in reviewable_ids
    ]
    by_episode: dict[str, set[str]] = {}
    by_reviewer: dict[str, int] = {}
    for r in rows:
        by_episode.setdefault(r.episode_id, set()).add(r.reviewer_canonical)
        by_reviewer[r.reviewer_canonical] = by_reviewer.get(r.reviewer_canonical, 0) + 1
    ready = sum(1 for s in by_episode.values() if len(s) >= config.review.min_reviewers)
    return StatusOut(
        reviewable_total=len(reviewable_ids),
        ready_total=ready,
        reviewers=[
            ReviewerStat(name=n, votes=v)
            for n, v in sorted(by_reviewer.items(), key=lambda kv: (-kv[1], kv[0]))
        ],
    )
