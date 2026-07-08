"""S2. Source Governance Gate — 저작권·약관·개인정보·수집 범위 판정 (§1-S2).

핵심 규칙(절대 규칙 7):
- 게이트 통과 전(PENDING)에는 어떤 원문도 저장소에 들어가지 않는다. 하류(S3+)가 읽을 수 없다.
- TRANSFORM_ONLY 소스의 원문 저장 금지 — 패턴·통계·개념만 추출.
- DENY 소스는 원천 drop(수집 금지). drop 카운터만 기록한다.
"""
from __future__ import annotations

import uuid
from typing import Literal

from sqlalchemy import delete, func, select
from sqlalchemy.orm import Session

from app.models.foundry import Source, SourceDocument
from app.models.governance import GovernanceEvent

Decision = Literal["ALLOW", "TRANSFORM_ONLY", "DENY"]

# S3+가 읽을 수 있는(게이트 통과) 상태
READABLE_STATUSES = ("ALLOW", "TRANSFORM_ONLY")
# 원문 저장이 허용되는 유일한 상태
RAW_STORAGE_STATUS = "ALLOW"


class GovernanceError(Exception):
    """거버넌스 규칙 위반 계열."""


class SourceNotFound(GovernanceError):
    pass


class SourceNotReadable(GovernanceError):
    """게이트 미통과(PENDING) 또는 DENY 소스를 하류가 읽으려 함."""


class RawStorageForbidden(GovernanceError):
    """ALLOW가 아닌 소스에 원문 저장 시도 (절대 규칙 7)."""


def _require_source(session: Session, source_id: str) -> Source:
    source = session.get(Source, source_id)
    if source is None:
        raise SourceNotFound(f"source {source_id!r} 없음")
    return source


def govern_source(
    session: Session,
    source_id: str,
    decision: Decision,
    *,
    reviewed_by: str,
    rules: list[str] | None = None,
) -> Source:
    """S2 판정을 소스에 반영하고 governance_event(SOURCE_DECISION)를 남긴다.

    ALLOW → 비ALLOW 재판정 시 이미 저장된 원문을 purge한다 (절대 규칙 7: 비ALLOW 소스는
    원문을 가질 수 없다). DB 트리거(마이그레이션 0004)가 직접 SQL 우회까지 백스톱.
    """
    source = _require_source(session, source_id)

    purged = 0
    if decision != RAW_STORAGE_STATUS:
        purged = int(
            session.scalar(
                select(func.count())
                .select_from(SourceDocument)
                .where(SourceDocument.source_id == source_id)
            )
            or 0
        )
        if purged:
            session.execute(
                delete(SourceDocument).where(SourceDocument.source_id == source_id)
            )

    source.governance_status = decision
    source.governance_meta = {
        "reviewed_by": reviewed_by,
        "rules": rules or [],
        "decision": decision,
    }
    payload: dict[str, object] = {
        "source_id": source_id,
        "decision": decision,
        "rules": rules or [],
    }
    if purged:
        payload["purged_raw_documents"] = purged
    session.add(
        GovernanceEvent(
            event_id=f"GEV_{uuid.uuid4().hex[:12]}",
            event_type="SOURCE_DECISION",
            payload=payload,
            approved_by=reviewed_by,
        )
    )
    return source


def assert_readable(source: Source) -> None:
    """하류(S3+)가 읽기 전 게이트 통과 여부 확인 — 파이프라인 레벨 차단."""
    if source.governance_status not in READABLE_STATUSES:
        raise SourceNotReadable(
            f"source {source.source_id!r} governance={source.governance_status} — "
            "S3+ 읽기 불가 (게이트 미통과)"
        )


def readable_sources(session: Session) -> list[Source]:
    """게이트를 통과한(ALLOW/TRANSFORM_ONLY) 소스만 반환."""
    stmt = select(Source).where(Source.governance_status.in_(READABLE_STATUSES))
    return list(session.scalars(stmt))


def dropped_source_count(session: Session) -> int:
    """현재 DENY 상태(수집 금지)인 소스 수 — drop 카운터."""
    stmt = select(func.count()).select_from(Source).where(Source.governance_status == "DENY")
    return int(session.scalar(stmt) or 0)


def store_raw_document(session: Session, source_id: str, content: str) -> SourceDocument:
    """원문 저장 — ALLOW 소스만 허용 (절대 규칙 7). DB 트리거가 백스톱."""
    source = _require_source(session, source_id)
    if source.governance_status != RAW_STORAGE_STATUS:
        raise RawStorageForbidden(
            f"source {source_id!r} governance={source.governance_status} — "
            "원문 저장 금지 (ALLOW만 가능, 절대 규칙 7)"
        )
    doc = SourceDocument(
        doc_id=f"DOC_{uuid.uuid4().hex[:12]}", source_id=source_id, content=content
    )
    session.add(doc)
    return doc
