"""episodes + evidence (§3-1, §3-2). benchmark_integrity CHECK = 절대 규칙 2의 물리적 구현."""
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class Episode(Base):
    __tablename__ = "episodes"
    __table_args__ = (
        CheckConstraint(
            "dataset_split IN ('TRAIN','VALIDATION','TEST','BENCHMARK_HOLDOUT')"
        ),
        CheckConstraint("reliability_tier IN ('UNVERIFIED','BRONZE','SILVER','GOLD')"),
        CheckConstraint(
            "label_state IN ('UNLABELED','EVIDENCE_ACCUMULATING','AGGREGATION_READY',"
            "'LABEL_CANDIDATE','REVIEW_REQUIRED','LABELED','REJECTED')"
        ),
        CheckConstraint(
            "origin_channel IN ('FOUNDRY_SYNTHETIC','FOUNDRY_AUGMENTED','GYM_HUMAN',"
            "'EXPERT_AUTHORED','PRODUCTION_SHADOW','OFFICIAL_CORPUS','COMMUNITY_DERIVED')"
        ),
        # 절대 규칙 9: provenance 필드 enum (episode_creator_type / primary_subject_type)
        CheckConstraint(
            "episode_creator_type IN ('FOUNDRY_PIPELINE','GYM_SESSION',"
            "'SHADOW_CONVERTER','HUMAN_ANNOTATOR')"
        ),
        CheckConstraint("primary_subject_type IN ('TEACHER','SIMULATED_TEACHER')"),
        # 절대 규칙 2: 벤치마크에 합성 데이터·미검증 라벨 진입 금지 (§3-4)
        CheckConstraint(
            "dataset_split <> 'BENCHMARK_HOLDOUT' "
            "OR (reliability_tier = 'GOLD' AND label_state = 'LABELED' "
            "AND origin_channel NOT IN ('FOUNDRY_SYNTHETIC','FOUNDRY_AUGMENTED'))",
            name="benchmark_integrity",
        ),
        # §3-3 백스톱: GOLD = 확정 라벨 보유 (마이그레이션 0002, §3-4 v1.2)
        CheckConstraint(
            "reliability_tier <> 'GOLD' OR label_state = 'LABELED'",
            name="gold_requires_labeled",
        ),
        Index("idx_episodes_split", "dataset_split"),
        Index("idx_episodes_state", "label_state"),
    )

    episode_id: Mapped[str] = mapped_column(Text, primary_key=True)
    ontology_version: Mapped[str] = mapped_column(Text, nullable=False)
    lang: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'ko'"))
    dataset_split: Mapped[str] = mapped_column(Text, nullable=False)
    reliability_tier: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'UNVERIFIED'")
    )
    label_state: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'UNLABELED'")
    )
    origin_channel: Mapped[str] = mapped_column(Text, nullable=False)
    episode_creator_type: Mapped[str] = mapped_column(Text, nullable=False)
    primary_subject_type: Mapped[str] = mapped_column(Text, nullable=False)
    scenario_id: Mapped[str | None] = mapped_column(
        Text, ForeignKey("canonical_scenarios.scenario_id")
    )
    teacher_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    persona_lens_used: Mapped[str | None] = mapped_column(Text)
    label_distribution = mapped_column(JSONB, nullable=False)
    consensus: Mapped[float | None] = mapped_column(Float)
    disagreement_pairs = mapped_column(JSONB)
    human_review = mapped_column(JSONB)
    dedup_hash: Mapped[str | None] = mapped_column(Text)
    prompt_embedding = mapped_column(Vector(1536))
    created_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class Evidence(Base):
    __tablename__ = "evidence"
    __table_args__ = (
        CheckConstraint("polarity IN ('supports','refutes')"),
        CheckConstraint("strength BETWEEN 0 AND 1"),
        CheckConstraint(
            "reliability IS NULL OR reliability BETWEEN 0 AND 1",
            name="evidence_reliability_range",
        ),
        CheckConstraint(
            "evidence_type IN ('SYNTHETIC_CONSENSUS','WEAK_BEHAVIORAL','DOMAIN_RULE',"
            "'HUMAN_CORRECTION','HUMAN_CONFIRMATION','EXPERT_REVIEW')"
        ),
        CheckConstraint(
            "actor_type IN ('LLM_ANALYST','DOMAIN_EXPERT','TEACHER_TRAINER',"
            "'STAFF_TRAINER','BEHAVIOR_SIGNAL','RULE_ENGINE')"
        ),
        Index("idx_evidence_episode", "episode_id"),
        Index("idx_evidence_intent", "intent_id"),
    )

    evidence_id: Mapped[str] = mapped_column(Text, primary_key=True)
    episode_id: Mapped[str] = mapped_column(
        Text, ForeignKey("episodes.episode_id"), nullable=False
    )
    intent_id: Mapped[str] = mapped_column(Text, nullable=False)
    polarity: Mapped[str] = mapped_column(Text, nullable=False)
    strength: Mapped[float] = mapped_column(Float, nullable=False)
    evidence_type: Mapped[str] = mapped_column(Text, nullable=False)
    actor_type: Mapped[str] = mapped_column(Text, nullable=False)
    trainer_ref: Mapped[str | None] = mapped_column(Text)
    reliability: Mapped[float | None] = mapped_column(Float)
    # 절대 규칙 6: adversarial=true는 자연 분포 학습·집계에서 분리
    adversarial: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("FALSE")
    )
    context = mapped_column(JSONB, server_default=text("'{}'::jsonb"))
    created_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))
