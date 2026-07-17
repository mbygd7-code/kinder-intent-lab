"""의도 목록·표시 수정·변경 제안 — /v1/ontology (2026-07-17 사용자 요청).

계층 분리가 핵심이다:
- **표시 계층**(한글 이름·화면 설명) = intent_display 오버레이 — PIN 확인 후 즉시 수정.
  온톨로지 YAML(의미)과 ontology_version(replay 축)은 절대 건드리지 않는다.
- **의미·구조 변경**(정의·추가·이동·삭제) = 제안 대기열 — 승인은 '반영 예약' 표시일 뿐,
  실반영은 운영자의 거버넌스 경로(§5-9 버전 규칙)로만. intent_id는 어디서도 수정 불가.
모든 수정·판정은 governance_events에 남는다(감사).
"""
from __future__ import annotations

import hmac
import os
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.db import get_session
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.models.governance import GovernanceEvent
from app.models.intent_admin import IntentChangeRequest, IntentDisplay

router = APIRouter(prefix="/v1/ontology", tags=["ontology"])

DISPLAY_EDIT_EVENT = "INTENT_DISPLAY_EDIT"
CHANGE_DECISION_EVENT = "INTENT_CHANGE_DECISION"


def _pin() -> str:
    """오클릭 방지 자물쇠 — 채점 PIN과 동일 관례(기본 2341, env로 교체)."""
    return os.environ.get("ONTOLOGY_PIN") or os.environ.get("ARENA_PIN") or "2341"


def _check_pin(pin: str) -> None:
    if not hmac.compare_digest(pin, _pin()):
        raise HTTPException(status_code=401, detail="비밀번호가 달라요")


def _real_intent_ids() -> set[str]:
    return {i.intent_id for i in load_ontology().intents if i.intent_id != UNKNOWN_INTENT_ID}


# --- 의도 목록 (의미 계층 + 표시 오버레이 병합) ---


class IntentItem(BaseModel):
    intent_id: str
    domain: str
    definition: str          # 의미 계층(YAML) — 여기서는 읽기 전용
    example_count: int
    name_ko: str | None      # 표시 오버레이 — 없으면 프론트 정적 라벨 사용
    description_ko: str | None


class IntentCatalogOut(BaseModel):
    ontology_version: str
    total: int
    items: list[IntentItem]


@router.get("/intents", response_model=IntentCatalogOut)
def intent_catalog(session: Session = Depends(get_session)) -> IntentCatalogOut:
    onto = load_ontology()
    overrides = {d.intent_id: d for d in session.scalars(select(IntentDisplay))}
    items = [
        IntentItem(
            intent_id=i.intent_id, domain=i.domain or "?", definition=i.definition,
            example_count=len(i.positive_examples),
            name_ko=(o.name_ko if (o := overrides.get(i.intent_id)) else None),
            description_ko=(o.description_ko if o else None),
        )
        for i in onto.intents if i.intent_id != UNKNOWN_INTENT_ID
    ]
    items.sort(key=lambda x: (x.domain, x.intent_id))
    return IntentCatalogOut(ontology_version=onto.version, total=len(items), items=items)


# --- 표시 수정 (PIN — 즉시 반영, 버전·YAML 불변) ---


class DisplayEditIn(BaseModel):
    pin: str
    edited_by: str
    name_ko: str | None = None
    description_ko: str | None = None


@router.put("/intents/{intent_id}/display", response_model=IntentItem)
def edit_display(
    intent_id: str, payload: DisplayEditIn, session: Session = Depends(get_session)
) -> IntentItem:
    _check_pin(payload.pin)
    if not payload.edited_by.strip():
        raise HTTPException(status_code=422, detail="수정자 이름을 입력해주세요")
    if intent_id not in _real_intent_ids():
        raise HTTPException(status_code=404, detail="온톨로지에 없는 의도예요")
    if payload.name_ko is None and payload.description_ko is None:
        raise HTTPException(status_code=422, detail="바꿀 내용(이름 또는 설명)을 입력해주세요")

    row = session.get(IntentDisplay, intent_id)
    before = {"name_ko": row.name_ko, "description_ko": row.description_ko} if row else None
    if row is None:
        row = IntentDisplay(intent_id=intent_id, updated_by=payload.edited_by)
        session.add(row)
    if payload.name_ko is not None:
        row.name_ko = payload.name_ko.strip() or None
    if payload.description_ko is not None:
        row.description_ko = payload.description_ko.strip() or None
    row.updated_by = payload.edited_by
    row.updated_at = datetime.now(UTC)

    session.add(GovernanceEvent(  # 감사 — 표시 수정도 기록이 남는 문으로만
        event_id="GOV_" + uuid.uuid4().hex[:12],
        event_type=DISPLAY_EDIT_EVENT,
        payload={"intent_id": intent_id, "before": before,
                 "after": {"name_ko": row.name_ko, "description_ko": row.description_ko}},
        approved_by=payload.edited_by,
    ))
    session.flush()

    onto = next(i for i in load_ontology().intents if i.intent_id == intent_id)
    return IntentItem(
        intent_id=intent_id, domain=onto.domain or "?", definition=onto.definition,
        example_count=len(onto.positive_examples),
        name_ko=row.name_ko, description_ko=row.description_ko,
    )


# --- 표시 일괄 수정 (CSV 업로드 — 이름·설명만. 구조 변경은 CSV로 우회 불가) ---

BULK_DISPLAY_EVENT = "INTENT_DISPLAY_BULK_EDIT"


class BulkDisplayRow(BaseModel):
    intent_id: str
    # None(필드 생략) = 변경 안 함. ""(빈 문자열) = 오버레이 해제(원래 값으로 복귀).
    name_ko: str | None = None
    description_ko: str | None = None


class BulkDisplayIn(BaseModel):
    pin: str
    edited_by: str
    rows: list[BulkDisplayRow]


class BulkDisplaySkip(BaseModel):
    intent_id: str
    reason: str


class BulkDisplayOut(BaseModel):
    applied: int
    skipped: list[BulkDisplaySkip]
    message: str


@router.post("/intents/display/bulk", response_model=BulkDisplayOut)
def bulk_display(payload: BulkDisplayIn, session: Session = Depends(get_session)) -> BulkDisplayOut:
    """CSV에서 온 이름·화면설명 일괄 반영(즉시). 온톨로지 버전·의미(YAML)는 불변.

    목록에 없는 id(새 의도)는 건너뛴다 — 새 의도·구조 변경은 CSV로 우회할 수 없고
    [＋ 새 의도 추가]/제안 경로로만 간다(§5-9 버전 규칙).
    """
    _check_pin(payload.pin)
    if not payload.edited_by.strip():
        raise HTTPException(status_code=422, detail="수정자 이름을 입력해주세요")
    real = _real_intent_ids()

    applied = 0
    skipped: list[BulkDisplaySkip] = []
    changed: list[str] = []
    for r in payload.rows:
        if r.intent_id not in real:
            skipped.append(BulkDisplaySkip(
                intent_id=r.intent_id,
                reason="목록에 없는 의도 — 새 의도는 [＋ 새 의도 추가]로 제안하세요",
            ))
            continue
        if r.name_ko is None and r.description_ko is None:
            continue  # 바꿀 필드 없음
        row = session.get(IntentDisplay, r.intent_id)
        if row is None:
            row = IntentDisplay(intent_id=r.intent_id, updated_by=payload.edited_by)
            session.add(row)
        if r.name_ko is not None:
            row.name_ko = r.name_ko.strip() or None
        if r.description_ko is not None:
            row.description_ko = r.description_ko.strip() or None
        row.updated_by = payload.edited_by
        row.updated_at = datetime.now(UTC)
        applied += 1
        changed.append(r.intent_id)

    if changed:  # 감사 — 일괄 수정은 요약 이벤트 1건(누가·몇 건·어떤 id)
        session.add(GovernanceEvent(
            event_id="GOV_" + uuid.uuid4().hex[:12],
            event_type=BULK_DISPLAY_EVENT,
            payload={"count": applied, "intent_ids": changed,
                     "skipped": [s.intent_id for s in skipped]},
            approved_by=payload.edited_by,
        ))
    session.flush()
    return BulkDisplayOut(
        applied=applied, skipped=skipped,
        message=(f"이름·설명 {applied}건 반영"
                 + (f" · {len(skipped)}건은 목록에 없어 건너뜀" if skipped else "")),
    )


# --- 변경 제안 대기열 (누구나 접수 → PIN으로 판정 — 실반영은 운영 경로) ---


class ChangeRequestIn(BaseModel):
    kind: Literal["DEFINITION", "ADD", "MOVE", "DELETE", "OTHER"]
    proposal: str
    proposed_by: str
    intent_id: str | None = None


class ChangeRequestOut(BaseModel):
    request_id: str
    intent_id: str | None
    kind: str
    proposal: str
    proposed_by: str
    status: str
    decided_by: str | None
    created_at: datetime | None


@router.post("/change-requests", response_model=ChangeRequestOut)
def submit_change_request(
    payload: ChangeRequestIn, session: Session = Depends(get_session)
) -> ChangeRequestOut:
    if not payload.proposal.strip() or not payload.proposed_by.strip():
        raise HTTPException(status_code=422, detail="제안 내용과 제안자 이름을 입력해주세요")
    if payload.intent_id is not None and payload.intent_id not in _real_intent_ids():
        raise HTTPException(status_code=404, detail="온톨로지에 없는 의도예요")
    row = IntentChangeRequest(
        request_id="ICR_" + uuid.uuid4().hex[:12],
        intent_id=payload.intent_id, kind=payload.kind,
        proposal=payload.proposal.strip(), proposed_by=payload.proposed_by.strip(),
    )
    session.add(row)
    session.flush()
    return _req_out(row)


def _req_out(r: IntentChangeRequest) -> ChangeRequestOut:
    return ChangeRequestOut(
        request_id=r.request_id, intent_id=r.intent_id, kind=r.kind, proposal=r.proposal,
        proposed_by=r.proposed_by, status=r.status, decided_by=r.decided_by,
        created_at=r.created_at,
    )


class ChangeRequestListOut(BaseModel):
    requests: list[ChangeRequestOut]


@router.get("/change-requests", response_model=ChangeRequestListOut)
def list_change_requests(
    status: str | None = None, session: Session = Depends(get_session)
) -> ChangeRequestListOut:
    q = select(IntentChangeRequest).order_by(IntentChangeRequest.created_at.desc())
    if status:
        q = q.where(IntentChangeRequest.status == status)
    return ChangeRequestListOut(requests=[_req_out(r) for r in session.scalars(q)])


class DecideIn(BaseModel):
    pin: str
    decision: Literal["approve", "reject"]
    decided_by: str


class DecideOut(BaseModel):
    request: ChangeRequestOut
    message: str


@router.post("/change-requests/{request_id}/decide", response_model=DecideOut)
def decide_change_request(
    request_id: str, payload: DecideIn, session: Session = Depends(get_session)
) -> DecideOut:
    _check_pin(payload.pin)
    if not payload.decided_by.strip():
        raise HTTPException(status_code=422, detail="판정자 이름을 입력해주세요")
    row = session.get(IntentChangeRequest, request_id)
    if row is None:
        raise HTTPException(status_code=404, detail="제안을 찾을 수 없어요")
    if row.status != "PENDING":
        raise HTTPException(status_code=409, detail=f"이미 판정된 제안이에요 ({row.status})")

    row.status = "APPROVED" if payload.decision == "approve" else "REJECTED"
    row.decided_by = payload.decided_by
    row.decided_at = datetime.now(UTC)
    session.add(GovernanceEvent(
        event_id="GOV_" + uuid.uuid4().hex[:12],
        event_type=CHANGE_DECISION_EVENT,
        payload={"request_id": row.request_id, "intent_id": row.intent_id,
                 "kind": row.kind, "decision": row.status, "proposal": row.proposal},
        approved_by=payload.decided_by,
    ))
    session.flush()
    msg = (
        "승인 완료 — 의미·구조 반영은 버전 규칙에 따라 운영 경로로 진행돼요(반영 예약)."
        if row.status == "APPROVED" else "반려했어요."
    )
    return DecideOut(request=_req_out(row), message=msg)
