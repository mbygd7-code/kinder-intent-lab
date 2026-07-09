"""Gym API (§8-1) — 강화하기(§7-4)에서 세션을 열고, 트레이너 응답을 evidence로 적재한다.

POST /v1/gym/session          origin(node/region/diagnosis/target_confusion) + mode → pack + items
POST /v1/gym/session/{id}/submit   trainer 응답 → GYM_HUMAN 에피소드 + HUMAN evidence

계약은 pydantic(내부 훈련 도구 — runtime 스펙 아님). 세션 아이템은 서버가 gym_sessions에
저장하므로 submit은 item_id로만 참조한다(발화·정답 위조 방지).
"""
from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.config import ExperimentsConfig
from app.core.db import get_session
from app.gym.evidence import evidence_type_for
from app.gym.pack import build_items, build_pack
from app.gym.session import start_session
from app.gym.session import submit_results as _submit
from app.models.gym import GymSession

router = APIRouter(prefix="/v1/gym", tags=["gym"])

GymMode = Literal["guess_my_intent", "choose_right_meaning", "correction_drill"]


def get_experiments() -> ExperimentsConfig:
    from app.core.config import get_config

    return get_config()


# --- 계약 (pydantic) ---


class PackOriginInput(BaseModel):
    node: str
    region: str | None = None
    diagnosis: list[str] | None = None
    target_confusion: str | None = None


class SessionStartRequest(BaseModel):
    trainer_ref: str = Field(min_length=1)
    mode: GymMode
    origin: PackOriginInput


class GymItemOut(BaseModel):
    item_id: str
    utterance: str
    candidate_intents: list[str]
    brain_guess: str | None = None
    # true_intent는 교정드릴 브레인 오답 세팅용 — 서버 보관, 응답엔 포함해 UI가 오답을 만든다


class SessionStartResponse(BaseModel):
    session_id: str
    pack_id: str
    mode: GymMode
    items: list[GymItemOut]


class ResultIn(BaseModel):
    item_id: str
    chosen_intent: str
    brain_guess: str | None = None
    recovery_turns: int = Field(default=0, ge=0)


class SubmitRequest(BaseModel):
    results: list[ResultIn]


class SubmitResponse(BaseModel):
    session_id: str
    episodes_created: int
    evidence_created: int
    by_type: dict[str, int]


@router.post("/session", response_model=SessionStartResponse)
def open_session(
    req: SessionStartRequest,
    session: Session = Depends(get_session),
    config: ExperimentsConfig = Depends(get_experiments),
) -> SessionStartResponse:
    evidence_type_for(req.mode)  # 지원 모드 검증(미지원 → 여기서 명확히 실패)
    pack = build_pack(
        session, trigger="observatory_click", node=req.origin.node, region=req.origin.region,
        diagnosis=req.origin.diagnosis, target_confusion=req.origin.target_confusion, config=config,
    )
    items = build_items(node_intent=req.origin.node, mode=req.mode, config=config)
    if not items:
        raise HTTPException(status_code=422, detail="이 노드로 만들 훈련 아이템이 없습니다")
    gs = start_session(session, trainer_ref=req.trainer_ref, mode=req.mode, pack=pack, items=items)
    return SessionStartResponse(
        session_id=gs.session_id,
        pack_id=pack.pack_id,
        mode=req.mode,
        items=[GymItemOut(**{k: it[k] for k in ("item_id", "utterance", "candidate_intents")},
                          brain_guess=it.get("brain_guess")) for it in items],
    )


@router.post("/session/{session_id}/submit", response_model=SubmitResponse)
def submit_session(
    session_id: str,
    req: SubmitRequest,
    session: Session = Depends(get_session),
    config: ExperimentsConfig = Depends(get_experiments),
) -> SubmitResponse:
    gs = session.get(GymSession, session_id)
    if gs is None:
        raise HTTPException(status_code=404, detail="세션 없음")
    report = _submit(session, gs, [r.model_dump() for r in req.results], config)
    return SubmitResponse(
        session_id=report.session_id,
        episodes_created=report.episodes_created,
        evidence_created=report.evidence_created,
        by_type=report.by_type,
    )
