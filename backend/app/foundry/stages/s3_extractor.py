"""S3. Domain Knowledge Extractor — 소스에서 situation_frame 추출·적재 (§1-S3).

품질 게이트: extraction_confidence < config.foundry.extract_min → 사람 검토 큐(보류, 폐기 아님).
"""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.contracts.base import Domain
from app.core.config import ExperimentsConfig, get_config
from app.foundry.prompts import load_prompt
from app.models.foundry import SituationFrame

PROMPT = load_prompt("s3_extractor")


class FrameInput(BaseModel):
    """S3 LLM 산출 — situation_frame 후보."""

    model_config = ConfigDict(extra="forbid")

    domain: Domain
    summary: str = Field(min_length=1)
    teacher_concern: str | None = None
    participants: dict[str, Any] | None = None
    materials: list[str] | None = None
    source_refs: list[str] | None = None
    extraction_confidence: float = Field(ge=0, le=1)


def new_frame_id() -> str:
    return f"SF_{uuid.uuid4().hex[:12]}"


def build_situation_frame(session: Session, frame: FrameInput) -> SituationFrame:
    """추출된 프레임을 적재한다 (confidence는 그대로 기록 — 게이트는 하류 조회)."""
    row = SituationFrame(
        frame_id=new_frame_id(),
        domain=frame.domain,
        summary=frame.summary,
        participants=frame.participants,
        materials=frame.materials,
        teacher_concern=frame.teacher_concern,
        source_refs=frame.source_refs,
        extraction_confidence=frame.extraction_confidence,
    )
    session.add(row)
    return row


def needs_human_review(frame: SituationFrame, config: ExperimentsConfig | None = None) -> bool:
    """extraction_confidence < extract_min → 사람 검토 대상."""
    cfg = config or get_config()
    conf = frame.extraction_confidence
    return conf is not None and conf < cfg.foundry.extract_min


def frames_needing_review(
    session: Session, config: ExperimentsConfig | None = None
) -> list[SituationFrame]:
    cfg = config or get_config()
    stmt = select(SituationFrame).where(
        SituationFrame.extraction_confidence < cfg.foundry.extract_min
    )
    return list(session.scalars(stmt))
