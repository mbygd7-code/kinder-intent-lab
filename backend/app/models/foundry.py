"""Foundry 테이블 (S1~S5): sources, source_documents, situation_frames, atlas_entries,
canonical_scenarios."""
from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, Text, text
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


class SourceDocument(Base):
    """소스 원문 — ALLOW 소스만 저장 가능 (절대 규칙 7).

    앱 가드(store_raw_document)와 DB 트리거(마이그레이션 0003)가 이중으로 강제한다.
    """
    __tablename__ = "source_documents"
    __table_args__ = (Index("idx_source_documents_source", "source_id"),)

    doc_id: Mapped[str] = mapped_column(Text, primary_key=True)
    source_id: Mapped[str] = mapped_column(
        Text, ForeignKey("sources.source_id"), nullable=False
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class FailedEpisode(Base):
    """배치 러너의 실패 에피소드 격리 큐 — 한 에피소드 실패가 배치를 중단시키지 않는다 (T2.1)."""
    __tablename__ = "failed_episodes"
    __table_args__ = (Index("idx_failed_episodes_run", "run_id"),)

    fail_id: Mapped[str] = mapped_column(Text, primary_key=True)
    run_id: Mapped[str] = mapped_column(Text, nullable=False)
    slot_index: Mapped[int] = mapped_column(Integer, nullable=False)
    stage: Mapped[str | None] = mapped_column(Text)
    error: Mapped[str] = mapped_column(Text, nullable=False)
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


class AtlasExpansionEntry(Base):
    """미매핑 발화의 Atlas 확장 큐 (§2-4) — 주간 클러스터링으로 신규 pattern_cluster 후보가 된다."""
    __tablename__ = "atlas_expansion_queue"
    __table_args__ = (
        CheckConstraint("status IN ('PENDING','CLUSTERED','DISMISSED')"),
        Index("idx_atlas_expansion_status", "status"),
    )

    queue_id: Mapped[str] = mapped_column(Text, primary_key=True)
    utterance: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'PENDING'"))
    source_run: Mapped[str | None] = mapped_column(Text)
    created_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class CanonicalScenario(Base):
    __tablename__ = "canonical_scenarios"

    scenario_id: Mapped[str] = mapped_column(Text, primary_key=True)
    frame_id: Mapped[str | None] = mapped_column(Text, ForeignKey("situation_frames.frame_id"))
    workspace_state = mapped_column(JSONB, nullable=False)  # visual_semantics 포함 (vs-1.0)
    variation_of: Mapped[str | None] = mapped_column(Text)
    variation_axis: Mapped[str | None] = mapped_column(Text)
    created_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))
