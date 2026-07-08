"""S1. Source Discovery Agent — 자료 후보를 발견만 한다. 수집 여부는 S2가 결정 (§1-S1).

여기서는 발견된 후보를 Source Registry에 PENDING으로 적재하고 조회하는 CRUD를 제공한다.
governance 판정 전에는 원문이 저장소에 들어가지 않는다(§1-S2, 절대 규칙 7).
"""
from __future__ import annotations

import uuid
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.foundry import Source

SourceClass = Literal["AUTHORITY", "PRACTICE", "TEACHER_LANGUAGE"]


class SourceCandidate(BaseModel):
    """S1 산출 — 발견된 자료 후보. discovery_reason(의도·언어 밀도 근거) 필수."""

    model_config = ConfigDict(extra="forbid")

    source_class: SourceClass
    title: str = Field(min_length=1)
    discovery_reason: str = Field(min_length=1)
    access: str | None = None
    format: str | None = None
    est_volume: str | None = None


def new_source_id() -> str:
    return f"SRC_{uuid.uuid4().hex[:12]}"


def register_source(session: Session, candidate: SourceCandidate) -> Source:
    """후보를 Registry에 PENDING으로 적재한다 (governance 미판정)."""
    source = Source(
        source_id=new_source_id(),
        source_class=candidate.source_class,
        title=candidate.title,
        access=candidate.access,
        format=candidate.format,
        est_volume=candidate.est_volume,
        discovery_reason=candidate.discovery_reason,
        governance_status="PENDING",
    )
    session.add(source)
    return source


def get_source(session: Session, source_id: str) -> Source | None:
    return session.get(Source, source_id)


def list_sources(session: Session, status: str | None = None) -> list[Source]:
    stmt = select(Source)
    if status is not None:
        stmt = stmt.where(Source.governance_status == status)
    return list(session.scalars(stmt))
