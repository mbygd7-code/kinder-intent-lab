"""POST /v1/intent/infer (mode=gym) — 추론 파이프라인 + decision 정책 (T3.3).

계약(infer_request/response)만 runtime §3-0·§3-1에서 차용한다. live rollout(Suggest/Assist/Auto)
서빙 코드는 만들지 않는다(CLAUDE.md PARTIAL HOLD): live/shadow는 계약을 통과해도 501로 막고,
gym만 서빙한다. emit하는 'suggest'는 브레인의 판정 라벨이지 실서비스 자동 실행이 아니다.

의존성(session/client/embed/config)은 override 가능한 seam으로 분리 — 테스트는 savepoint 세션과
합성 scorer/임베딩을 주입해 실 LLM·네트워크 없이 파이프라인을 돈다.
"""
from __future__ import annotations

import logging
import os
import time
from collections.abc import Callable
from functools import lru_cache

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.brain.decision import decide
from app.brain.inference import infer
from app.contracts.infer_request import InferRequest
from app.contracts.infer_response import InferResponse, IntentCandidate
from app.core.config import ExperimentsConfig, get_config
from app.core.db import get_session
from app.core.ontology import load_ontology
from app.core.risk_model import get_risk_model
from app.llm.base import EmbeddingRequest
from app.llm.client import LLMClient, get_embedding_client, get_llm_client
from app.models.brain import BrainVersion

router = APIRouter(prefix="/v1/intent", tags=["intent"])
logger = logging.getLogger("app.api.infer")

EmbedFn = Callable[[list[str]], list[list[float]]]

# 위험 등급은 리스크 모델(rm-1.x, 온톨로지 밖 평가 정책)에서 파생한다 — 투트랙 채택 D
# (2026-07-17 사용자 승인, 이전의 하드코딩 기본값 LOW/false를 교체). 응답 계약(runtime §3-1)의
# 4단 어휘(LOW/MED/HIGH/CRITICAL)로 사상: CRITICAL→CRITICAL(게이트·CWAR 대상),
# ELEVATED→HIGH(egress 경계에서 이미 게이트된 위험 — UX/telemetry 티어), STANDARD→LOW.
# MED는 현 리스크 모델에 대응 티어가 없어 비워 둔다(지어내지 않음).
_RISK_TIER_MAP = {"CRITICAL": "CRITICAL", "ELEVATED": "HIGH", "STANDARD": "LOW"}


# --- 주입 seam (테스트가 override) ---
# lru_cache: SDK 클라이언트/커넥션풀을 프로세스당 1회만 만들어 요청 간 재사용(요청마다 새 TLS
# 핸드셰이크·풀 생성 방지). 테스트는 이 함수를 dependency_overrides로 통째 대체하므로 캐시 무관.


@lru_cache(maxsize=1)
def get_infer_client() -> LLMClient:
    return get_llm_client()


@lru_cache(maxsize=1)
def get_infer_embed() -> EmbedFn:
    client = get_embedding_client()
    model = os.environ.get("EMBEDDING_MODEL", "embed")
    return lambda texts: client.embed(EmbeddingRequest(inputs=texts, model=model)).vectors


def get_experiments() -> ExperimentsConfig:
    return get_config()


async def parse_infer_request(request: Request) -> InferRequest:
    """본문을 InferRequest 계약으로 검증. 위반(훈련 메타의 Core 침범 등)은 400 (기본 422 아님)."""
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001 — 잘못된 JSON도 400
        raise HTTPException(status_code=400, detail="잘못된 JSON 본문") from exc
    try:
        return InferRequest.model_validate(body)
    except ValidationError as exc:
        # 상세(제출 값·내부 계약 형태)는 서버 로그로만 — 응답엔 안정적 일반 메시지만 노출
        logger.warning("infer 요청 계약 위반: %s", exc)
        raise HTTPException(status_code=400, detail="유효하지 않은 infer 요청") from exc


def _model_version(session: Session) -> str:
    """현재 서빙 브레인 버전 = 최신 promote된 brain_version. 없으면 시드 기본."""
    v = session.scalar(
        select(BrainVersion.version)
        .where(BrainVersion.decision == "promote")
        .order_by(BrainVersion.created_at.desc())
    )
    return v or "seed-v0"


@router.post("/infer", response_model=InferResponse, response_model_exclude_none=True)
def infer_endpoint(
    req: InferRequest = Depends(parse_infer_request),
    session: Session = Depends(get_session),
    client: LLMClient = Depends(get_infer_client),
    embed_fn: EmbedFn = Depends(get_infer_embed),
    config: ExperimentsConfig = Depends(get_experiments),
) -> InferResponse:
    if req.mode != "gym":
        # 계약은 통과해도 live/shadow 서빙은 하지 않는다 (PARTIAL HOLD)
        raise HTTPException(status_code=501, detail="mode=gym만 서빙 (live/shadow rollout HOLD)")

    started = time.monotonic()
    result = infer(session, req, client, embed_fn, config,
                   model=os.environ.get("LLM_MODEL", "brain"))

    # UNKNOWN/온톨로지 드리프트(domain=None) 후보는 계약상 응답에 못 실린다 — 한 번 걸러서
    # decision·top_intent·clarification·intent_candidates가 모두 같은 집합을 참조하게 한다
    # (필터를 응답에만 걸면 client가 못 받은 intent를 제안하는 불일치가 생긴다).
    served = [c for c in result.candidates if c["domain"] is not None]

    outcome = decide(
        candidate_intents=[c["intent_id"] for c in served],
        top_activation=result.top_activation,
        confidence=result.confidence,
        margin=result.margin,
        config=config,
    )

    risk_model = get_risk_model()
    candidates = [
        IntentCandidate(
            intent_id=c["intent_id"],
            domain=c["domain"],
            score=c["score"],
            risk_tier=_RISK_TIER_MAP[risk_model.tier_of(c["intent_id"])],
            # 확인 게이트는 CRITICAL만 — ELEVATED는 egress 경계에서 이미 게이트됨(이중 게이트는
            # CWAR를 희석, risk_model_v1.yaml 머리말 원칙)
            requires_confirmation=risk_model.tier_of(c["intent_id"]) == "CRITICAL",
        )
        for c in served
    ]

    # 추론이 실제 소비한 문맥 블록 에코(투트랙 채택 D) — 빈 블록은 넣지 않는다(정직성).
    ws = req.workspace_context
    context_used = ["utterance"]
    if ws is not None and (ws.objects or ws.selection or ws.derived_summary):
        context_used.append("workspace_context")
    if req.recent_actions:
        context_used.append("recent_actions")
    if req.teacher_context is not None and req.teacher_context.teacher_ref:
        context_used.append("teacher_context")
    if result.persona_state_version:  # persona prior가 실제 적용된 경우만
        context_used.append("persona_prior")

    return InferResponse(
        request_id=req.request_id,
        schema_version=req.schema_version,
        model_version=_model_version(session),
        ontology_version=load_ontology().version,
        latency_ms=int((time.monotonic() - started) * 1000),
        intent_candidates=candidates,
        top_intent=served[0]["intent_id"] if served else "UNKNOWN",
        confidence=result.confidence,
        margin=result.margin,
        is_multi_intent=False,  # v1은 단일 의도 (다중 의도 계획은 후속)
        intent_plan=None,
        decision=outcome.decision,
        clarification=outcome.clarification,
        abstain_reason=outcome.abstain_reason,
        persona_state_version=result.persona_state_version or "ps-none",
        fallback_used=result.fallback_used,
        # 투트랙 채택 D — 킨더버스 연결 계약 3필드
        risk_level=candidates[0].risk_tier if candidates else None,
        required_slots=None,  # 예약 — 슬롯 추출은 트랙2(구현 전까지 항상 null)
        context_used=context_used,
    )
