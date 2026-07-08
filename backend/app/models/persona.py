"""persona_clusters, population_priors, teacher_priors (§4, §5-3)."""
from sqlalchemy import DateTime, Float, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class PersonaCluster(Base):
    __tablename__ = "persona_clusters"

    cluster_id: Mapped[str] = mapped_column(Text, primary_key=True)
    method: Mapped[str | None] = mapped_column(Text)
    axes = mapped_column(JSONB)
    member_count: Mapped[int | None] = mapped_column(Integer)
    version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class PopulationPrior(Base):
    __tablename__ = "population_priors"

    cluster_id: Mapped[str] = mapped_column(
        Text, ForeignKey("persona_clusters.cluster_id"), primary_key=True
    )
    intent_id: Mapped[str] = mapped_column(Text, primary_key=True)
    prior: Mapped[float] = mapped_column(Float, nullable=False)
    state_version: Mapped[str] = mapped_column(Text, primary_key=True)  # replay 무결성


class TeacherPrior(Base):
    __tablename__ = "teacher_priors"

    trainer_ref: Mapped[str] = mapped_column(Text, primary_key=True)
    intent_id: Mapped[str] = mapped_column(Text, primary_key=True)
    prior: Mapped[float] = mapped_column(Float, nullable=False)
    state_version: Mapped[str] = mapped_column(Text, primary_key=True)
    updated_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))
