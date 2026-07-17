"""의도 표시 오버레이 + 변경 제안 대기열 (마이그레이션 0020, §5-9 운영 보조).

intent_display는 **표시 계층**이다 — 온톨로지 YAML(의미)·ontology_version(replay 축)을
건드리지 않는다. 변경 제안(intent_change_requests)의 승인은 '반영 예약' 표시일 뿐,
실제 의미·구조 반영은 운영자의 거버넌스 경로(버전 규칙)로만 이루어진다.
"""
from sqlalchemy import CheckConstraint, DateTime, Index, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class IntentDisplay(Base):
    __tablename__ = "intent_display"

    intent_id: Mapped[str] = mapped_column(Text, primary_key=True)
    name_ko: Mapped[str | None] = mapped_column(Text)
    description_ko: Mapped[str | None] = mapped_column(Text)
    updated_by: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class IntentChangeRequest(Base):
    __tablename__ = "intent_change_requests"
    __table_args__ = (
        CheckConstraint("kind IN ('DEFINITION','ADD','MOVE','DELETE','OTHER')"),
        CheckConstraint("status IN ('PENDING','APPROVED','REJECTED')"),
        Index("idx_intent_change_requests_status", "status"),
    )

    request_id: Mapped[str] = mapped_column(Text, primary_key=True)
    intent_id: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(Text, nullable=False)
    proposal: Mapped[str] = mapped_column(Text, nullable=False)
    proposed_by: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    decided_by: Mapped[str | None] = mapped_column(Text)
    decided_at = mapped_column(DateTime(timezone=True))
    created_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))
