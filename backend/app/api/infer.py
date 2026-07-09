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
from app.llm.base import EmbeddingRequest
from app.llm.client import LLMClient, get_embedding_client, get_llm_client
from app.models.brain import BrainVersion

router = APIRouter(prefix="/v1/intent", tags=["intent"])
logger = logging.getLogger("app.api.infer")

EmbedFn = Callable[[list[str]], list[list[float]]]

# 위험 등급은 아직 노드/온톨로지에 모델링돼 있지 않다(위험 게이팅은 Stage 3 live 소관). gym에선
# 보수적 기본값 LOW/미확인으로 응답한다 — 고정 서열을 코드에 굳히는 게 아니라 '미모델링' 표시.
_DEFAULT_RISK_TIER = "LOW"
_DEFAULT_REQUIRES_CONFIRMATION = False


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

    candidates = [
        IntentCandidate(
            intent_id=c["intent_id"],
            domain=c["domain"],
            score=c["score"],
            risk_tier=_DEFAULT_RISK_TIER,
            requires_confirmation=_DEFAULT_REQUIRES_CONFIRMATION,
        )
        for c in served
    ]

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
    )
