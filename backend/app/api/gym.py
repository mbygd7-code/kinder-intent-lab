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
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.gym.challenge import generate_pack, pack_to_dict
from app.gym.evidence import evidence_type_for
from app.gym.growth import finalize_session
from app.gym.pack import build_items, build_pack
from app.gym.session import start_session
from app.gym.session import submit_results as _submit
from app.models.gym import GymSession

router = APIRouter(prefix="/v1/gym", tags=["gym"])

GymMode = Literal["guess_my_intent", "choose_right_meaning", "correction_drill"]
PackTrigger = Literal["observatory_click", "scheduled", "version_gate_campaign"]


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
    # §6-7 [5][6]: 세션 종료 성장 반영 결과 (프론트가 노드 갱신·pending 링 표시에 사용)
    node_intent: str | None = None
    episodes_aggregated: int = 0
    label_states: dict[str, int] = Field(default_factory=dict)
    pending_set: bool = False


# --- T4.2 Challenge Pack 생성 (진단→전략, 사람 세션 이전 단계) ---


class PackGenRequest(BaseModel):
    node_intent: str = Field(min_length=1)
    trigger: PackTrigger = "observatory_click"


class WorkOrderOut(BaseModel):
    order_id: str
    order_type: str
    status: str
    requested_items: int


class PackGenResponse(BaseModel):
    pack: dict            # challenge_pack.schema.json 형태
    diagnosis_codes: list[str]
    strategy: list[str]
    needs_human: bool     # False면 A/D형 — Gym 세션 없이 처리
    node_priority: float  # §6-3 훈련 우선순위 점수
    work_orders: list[WorkOrderOut]


@router.post("/pack", response_model=PackGenResponse)
def generate_challenge_pack(
    req: PackGenRequest,
    session: Session = Depends(get_session),
    config: ExperimentsConfig = Depends(get_experiments),
) -> PackGenResponse:
    """§6-1·6-3·6-4: 노드 진단 → 강화 pack. A형은 Foundry 작업 큐로 발행(사람 세션 없이)."""
    real = {i.intent_id for i in load_ontology().intents if i.intent_id != UNKNOWN_INTENT_ID}
    if req.node_intent not in real:
        raise HTTPException(status_code=404, detail="알 수 없는 intent")
    result = generate_pack(
        session, node_intent=req.node_intent, trigger=req.trigger, config=config
    )
    return PackGenResponse(
        pack=pack_to_dict(result.pack),
        diagnosis_codes=result.diagnosis_codes,
        strategy=result.pack.strategy,
        needs_human=result.needs_human,
        node_priority=result.node_priority,
        work_orders=[
            WorkOrderOut(
                order_id=w.order_id, order_type=w.order_type,
                status=w.status, requested_items=w.requested_items,
            )
            for w in result.work_orders
        ],
    )


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
    # 멱등 가드: 이미 제출된 세션의 재-POST(타임아웃 재시도·더블클릭)가 에피소드·evidence를
    # 통째로 복제해 노드 size를 이중 계상하는 것을 차단한다 (T4.3 리뷰 MAJOR)
    if (gs.results or {}).get("responses"):
        raise HTTPException(status_code=409, detail="이미 제출된 세션입니다")
    report = _submit(session, gs, [r.model_dump() for r in req.results], config)
    # §6-7 [5][6] — 세션 종료 성장 반영: aggregator 전이 + 노드 size/density + pending 링
    fin = finalize_session(session, gs, config)
    return SubmitResponse(
        session_id=report.session_id,
        episodes_created=report.episodes_created,
        evidence_created=report.evidence_created,
        by_type=report.by_type,
        node_intent=fin.node_intent,
        episodes_aggregated=fin.episodes_aggregated,
        label_states=fin.label_states,
        pending_set=fin.pending_set,
    )
