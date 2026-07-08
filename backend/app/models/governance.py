"""ontology_versions, governance_events (§5-8, 절대 규칙 4)."""
from sqlalchemy import CheckConstraint, DateTime, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class OntologyVersion(Base):
    __tablename__ = "ontology_versions"
    __table_args__ = (CheckConstraint("change_type IN ('minor','major')"),)

    version: Mapped[str] = mapped_column(Text, primary_key=True)
    change_type: Mapped[str | None] = mapped_column(Text)
    migration_map = mapped_column(JSONB)
    created_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class GovernanceEvent(Base):
    __tablename__ = "governance_events"

    event_id: Mapped[str] = mapped_column(Text, primary_key=True)
    event_type: Mapped[str] = mapped_column(Text, nullable=False)
    payload = mapped_column(JSONB, nullable=False)
    approved_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))
