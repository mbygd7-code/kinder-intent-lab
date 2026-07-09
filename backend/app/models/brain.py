"""brain_nodes, confusion_edges, brain_versions, exemplars (§5, §6-6, §5-7)."""
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    REAL,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    text,
)
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


class Exemplar(Base):
    """노드별 대표 에피소드 임베딩 (§5-1·§5-7). GOLD 확정 라벨에서만 선정.

    hnsw 인덱스는 비-idx_ 이름이라 model↔schema 동기 테스트(idx_ 대조)에서 제외 —
    벡터 인덱스 이름은 마이그레이션 0009가 원천.
    """
    __tablename__ = "exemplars"
    __table_args__ = (
        UniqueConstraint("node_id", "episode_id"),  # 중복 채택 방지
        Index("idx_exemplars_node", "node_id"),
        Index(
            "exemplars_embedding_hnsw", "embedding",
            postgresql_using="hnsw", postgresql_ops={"embedding": "vector_cosine_ops"},
        ),
    )

    exemplar_id: Mapped[str] = mapped_column(Text, primary_key=True)
    node_id: Mapped[str] = mapped_column(
        Text, ForeignKey("brain_nodes.node_id"), nullable=False
    )
    intent_id: Mapped[str] = mapped_column(Text, nullable=False)
    episode_id: Mapped[str] = mapped_column(
        Text, ForeignKey("episodes.episode_id"), nullable=False
    )
    embedding = mapped_column(Vector(1536), nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))


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


class InferenceLog(Base):
    """추론 전건 로그 — 4단계(retrieval/scorer/prior/normalize) 기여를 stages에 분리 기록 (§5-5)."""
    __tablename__ = "inference_logs"
    __table_args__ = (Index("idx_inference_logs_request", "request_id"),)

    inference_id: Mapped[str] = mapped_column(Text, primary_key=True)
    request_id: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    top_intent: Mapped[str | None] = mapped_column(Text)
    confidence: Mapped[float | None] = mapped_column(REAL)  # 001 관례: REAL
    margin: Mapped[float | None] = mapped_column(REAL)
    persona_state_version: Mapped[str | None] = mapped_column(Text)
    fallback_used: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    stages = mapped_column(JSONB, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))


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
