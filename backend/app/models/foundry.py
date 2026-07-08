"""Foundry 테이블 (S1~S5): sources, situation_frames, atlas_entries, canonical_scenarios."""
from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

DOMAIN_CHECK = (
    "IN ('PLAY','OBSERVATION','DOCUMENT','VISUAL','COMMUNICATION','OPERATION','REFLECTION')"
)


class Source(Base):
    __tablename__ = "sources"
    __table_args__ = (
        CheckConstraint("source_class IN ('AUTHORITY','PRACTICE','TEACHER_LANGUAGE')"),
        CheckConstraint("governance_status IN ('PENDING','ALLOW','TRANSFORM_ONLY','DENY')"),
    )

    source_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_class: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    access: Mapped[str | None] = mapped_column(Text)
    format: Mapped[str | None] = mapped_column(Text)
    est_volume: Mapped[str | None] = mapped_column(Text)
    discovery_reason: Mapped[str] = mapped_column(Text, nullable=False)
    governance_status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'PENDING'")
    )
    governance_meta = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class SituationFrame(Base):
    __tablename__ = "situation_frames"
    __table_args__ = (CheckConstraint("domain " + DOMAIN_CHECK),)

    frame_id: Mapped[str] = mapped_column(Text, primary_key=True)
    domain: Mapped[str] = mapped_column(Text, nullable=False)
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    participants = mapped_column(JSONB)
    materials = mapped_column(JSONB)
    teacher_concern: Mapped[str | None] = mapped_column(Text)
    source_refs = mapped_column(JSONB)
    extraction_confidence: Mapped[float | None] = mapped_column(Float)
    created_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class AtlasEntry(Base):
    __tablename__ = "atlas_entries"

    atlas_id: Mapped[str] = mapped_column(Text, primary_key=True)
    surface_form: Mapped[str] = mapped_column(Text, nullable=False)
    pattern_cluster: Mapped[str] = mapped_column(Text, nullable=False)
    ambiguity_types = mapped_column(JSONB, nullable=False)
    possible_intents = mapped_column(JSONB, nullable=False)
    resolution_signals = mapped_column(JSONB, nullable=False)
    register = mapped_column(JSONB)
    observed_count: Mapped[int | None] = mapped_column(Integer, server_default=text("0"))
    source_class_mix = mapped_column(JSONB)
    created_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class CanonicalScenario(Base):
    __tablename__ = "canonical_scenarios"

    scenario_id: Mapped[str] = mapped_column(Text, primary_key=True)
    frame_id: Mapped[str | None] = mapped_column(Text, ForeignKey("situation_frames.frame_id"))
    workspace_state = mapped_column(JSONB, nullable=False)  # visual_semantics 포함 (vs-1.0)
    variation_of: Mapped[str | None] = mapped_column(Text)
    variation_axis: Mapped[str | None] = mapped_column(Text)
    created_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))
