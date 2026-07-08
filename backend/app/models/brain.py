"""brain_nodes, confusion_edges, brain_versions (§5, §6-6)."""
from sqlalchemy import Boolean, CheckConstraint, DateTime, Float, Text, UniqueConstraint, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base
from app.models.foundry import DOMAIN_CHECK


class BrainNode(Base):
    __tablename__ = "brain_nodes"
    __table_args__ = (CheckConstraint("region " + DOMAIN_CHECK),)

    node_id: Mapped[str] = mapped_column(Text, primary_key=True)
    intent_id: Mapped[str] = mapped_column(Text, nullable=False, unique=True)
    region: Mapped[str] = mapped_column(Text, nullable=False)
    definition_ref: Mapped[str] = mapped_column(Text, nullable=False)
    exemplar_stats = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    evidence_stats = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    # 절대 규칙 3: brightness 계열(heldout_accuracy 등)은 Arena 러너만 갱신
    heldout_accuracy: Mapped[float | None] = mapped_column(Float)
    calibration_ece: Mapped[float | None] = mapped_column(Float)
    last_arena_run: Mapped[str | None] = mapped_column(Text)
    coverage = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    pending_evaluation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    # 절대 규칙 4: 노드 생성은 governance_events를 남기는 승인 플로우로만
    created_by_event: Mapped[str] = mapped_column(Text, nullable=False)


class ConfusionEdge(Base):
    __tablename__ = "confusion_edges"
    __table_args__ = (
        CheckConstraint("state IN ('hypothesized','observed','confirmed')"),
        CheckConstraint(
            "origin IN ('SKEPTIC','CONSENSUS_DISAGREEMENT','GYM_CORRECTION','ARENA_MATRIX')"
        ),
        UniqueConstraint("from_true", "to_predicted"),  # 방향성: (A,B) != (B,A)
    )

    edge_id: Mapped[str] = mapped_column(Text, primary_key=True)
    from_true: Mapped[str] = mapped_column(Text, nullable=False)
    to_predicted: Mapped[str] = mapped_column(Text, nullable=False)
    confusion_rate: Mapped[float | None] = mapped_column(Float)
    state: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'hypothesized'")
    )
    origin: Mapped[str | None] = mapped_column(Text)
    evidence_runs = mapped_column(JSONB)
    contrast_exemplars = mapped_column(JSONB)
    last_updated = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class BrainVersion(Base):
    __tablename__ = "brain_versions"
    __table_args__ = (CheckConstraint("decision IN ('candidate','promote','reject')"),)

    version: Mapped[str] = mapped_column(Text, primary_key=True)
    base: Mapped[str | None] = mapped_column(Text)
    trigger: Mapped[str | None] = mapped_column(Text)
    delta = mapped_column(JSONB)
    arena_result = mapped_column(JSONB)
    decision: Mapped[str | None] = mapped_column(Text)
    created_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))
