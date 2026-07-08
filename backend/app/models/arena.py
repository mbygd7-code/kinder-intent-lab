"""arena_runs (§8 KTIB 러너 기록, replay 무결성 4종)."""
from sqlalchemy import DateTime, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ArenaRun(Base):
    __tablename__ = "arena_runs"

    run_id: Mapped[str] = mapped_column(Text, primary_key=True)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    ontology_version: Mapped[str] = mapped_column(Text, nullable=False)
    persona_state_version: Mapped[str] = mapped_column(Text, nullable=False)
    extractor_versions = mapped_column(JSONB, nullable=False)
    ktib_version: Mapped[str] = mapped_column(Text, nullable=False)
    metrics = mapped_column(JSONB, nullable=False)
    confusion_matrix = mapped_column(JSONB)
    created_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))
