"""challenge_packs, gym_sessions (§6-4)."""
from sqlalchemy import DateTime, ForeignKey, Integer, Text, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class ChallengePack(Base):
    __tablename__ = "challenge_packs"

    pack_id: Mapped[str] = mapped_column(Text, primary_key=True)
    origin = mapped_column(JSONB, nullable=False)
    strategy = mapped_column(JSONB, nullable=False)
    target_edges = mapped_column(JSONB)
    items: Mapped[int] = mapped_column(Integer, nullable=False)
    difficulty_curve: Mapped[str | None] = mapped_column(Text)
    persona_mix = mapped_column(JSONB)
    delivery_modes = mapped_column(JSONB)
    expected_yield = mapped_column(JSONB)
    created_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class GymSession(Base):
    __tablename__ = "gym_sessions"

    session_id: Mapped[str] = mapped_column(Text, primary_key=True)
    pack_id: Mapped[str | None] = mapped_column(Text, ForeignKey("challenge_packs.pack_id"))
    trainer_ref: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(Text, nullable=False)
    results = mapped_column(JSONB, nullable=False, server_default=text("'[]'::jsonb"))
    created_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))
