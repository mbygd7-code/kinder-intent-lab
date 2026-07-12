"""시험지(KTIB) 후보 2차 검수 스테이징 (마이그레이션 0015, §3-3·§8-2).

교사 A가 문항+1~5 평점을 제출하면 여기 대기하고(episodes 아님 — 반쯤 만든 후보가 벤치마크를
오염시키지 않게, §8-2), 교사 B가 다른 컴퓨터에서 blind로 2차 평점을 매긴다. 서로 다른 2명 ∧
가중 kappa ≥ 임계면 등록 가능 → 등록은 오직 ingest_expert_episodes로만 episodes에 들어가
benchmark_integrity CHECK가 최종 방어(절대 규칙 2).

여기 스테이징 테이블에는 GOLD·brightness 어떤 것도 없다 — tier/label은 등록 시 부여된다.
컬럼·인덱스명은 db/migrations/versions/0015_*.py와 정확히 일치(test_models_match_migrated_schema).
"""
from sqlalchemy import CheckConstraint, DateTime, Float, ForeignKey, Index, Integer, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class BenchmarkCandidateBatch(Base):
    """제출 세션 1건 = 교사 A가 한 번에 올린 문항 묶음. 2차 검수·등록 단위(배치 kappa)."""
    __tablename__ = "benchmark_candidate_batches"
    __table_args__ = (
        CheckConstraint(
            "status IN ('AWAITING_SECOND','SECOND_DONE','REGISTERED')"
        ),
        Index("idx_benchmark_candidate_batches_status", "status"),
    )

    batch_id: Mapped[str] = mapped_column(Text, primary_key=True)
    # 1차(작성) 검수자 — 정규화 신원(canonical_reviewer). 2차 검수자는 이 사람과 달라야 한다.
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'AWAITING_SECOND'")
    )
    # 2차 검수 완료 시 기록되는 배치 가중 kappa (미완료면 null — 지어내지 않는다)
    agreement_kappa: Mapped[float | None] = mapped_column(Float)
    reviewer_second: Mapped[str | None] = mapped_column(Text)
    ktib_version: Mapped[str | None] = mapped_column(Text)
    created_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class BenchmarkCandidateItem(Base):
    """배치 안의 문항 1건. rating_a=작성자 평점(1~5), rating_b=2차 검수자 평점(1~5, 검수 전 null)."""
    __tablename__ = "benchmark_candidate_items"
    __table_args__ = (
        CheckConstraint("rating_a BETWEEN 1 AND 5"),
        CheckConstraint("rating_b IS NULL OR rating_b BETWEEN 1 AND 5"),
        Index("idx_benchmark_candidate_items_batch", "batch_id"),
    )

    item_id: Mapped[str] = mapped_column(Text, primary_key=True)
    batch_id: Mapped[str] = mapped_column(
        Text,
        ForeignKey("benchmark_candidate_batches.batch_id", ondelete="CASCADE"),
        nullable=False,
    )
    intent_id: Mapped[str] = mapped_column(Text, nullable=False)
    teacher_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    rating_a: Mapped[int] = mapped_column(Integer, nullable=False)
    rating_b: Mapped[int | None] = mapped_column(Integer)
