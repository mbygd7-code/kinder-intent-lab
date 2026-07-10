"""arena_runs + ktib_versions/ktib_items (§8 KTIB 러너 기록, replay 무결성 4종).

KTIB(§8-2)는 학습 파이프라인이 접근할 수 없는 격리 벤치마크다. 구성 자격은
`dataset_split=BENCHMARK_HOLDOUT ∧ tier=GOLD ∧ label_state=LABELED ∧ origin_channel 비합성`이며
그 강제는 episodes의 benchmark_integrity CHECK(절대 규칙 2)가 물리적으로 담당한다.

`ktib_items`는 채택 시점의 발화·gold intent·workspace(visual_semantics)를 **동결**한다.
extractor가 바뀌면 content_hash가 바뀌어 새 ktib_version이 강제된다 — 신·구 벤치마크 점수를
같은 축에 그리지 않기 위해서다(§8-2).
"""
from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Text,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base

# arena run 종류 — 'brain'만이 3D 밝기의 원천이다(§8-2, 절대 규칙 3).
RUN_TYPE_BRAIN = "brain"
RUN_TYPE_BASELINE = "zero_shot_baseline"

# persona_state_version은 NOT NULL이다. 발급된 persona state가 아직 없을 때 쓰는 명시적 sentinel —
# 없는 버전을 지어내거나 다른 축(brain 버전)의 이름을 빌려오지 않는다.
NO_PERSONA_STATE = "none"


class KtibVersion(Base):
    __tablename__ = "ktib_versions"
    __table_args__ = (
        CheckConstraint("episode_count > 0"),
        Index("idx_ktib_versions_content", "content_hash", unique=True),
    )

    ktib_version: Mapped[str] = mapped_column(Text, primary_key=True)
    seq: Mapped[int] = mapped_column(Integer, nullable=False, unique=True)
    # 동결된 extractor 버전들 — replay 무결성 4종의 4번째 축 (§8-2)
    extractor_versions = mapped_column(JSONB, nullable=False)
    episode_count: Mapped[int] = mapped_column(Integer, nullable=False)
    content_hash: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text)
    created_at = mapped_column(DateTime(timezone=True), server_default=text("now()"))


class KtibItem(Base):
    """채택 시점 동결 스냅샷 — 에피소드 원본이 나중에 바뀌어도 벤치마크는 흔들리지 않는다."""

    __tablename__ = "ktib_items"
    __table_args__ = (Index("idx_ktib_items_version", "ktib_version"),)

    ktib_version: Mapped[str] = mapped_column(
        Text, ForeignKey("ktib_versions.ktib_version", ondelete="CASCADE"), primary_key=True
    )
    episode_id: Mapped[str] = mapped_column(
        Text, ForeignKey("episodes.episode_id"), primary_key=True
    )
    gold_intent: Mapped[str] = mapped_column(Text, nullable=False)
    teacher_prompt: Mapped[str] = mapped_column(Text, nullable=False)
    lang: Mapped[str] = mapped_column(Text, nullable=False)
    # visual_semantics 포함. 시나리오가 없는 에피소드는 NULL — 지어내지 않는다.
    workspace_snapshot = mapped_column(JSONB)


class ArenaRun(Base):
    __tablename__ = "arena_runs"
    __table_args__ = (
        CheckConstraint(f"run_type IN ('{RUN_TYPE_BRAIN}','{RUN_TYPE_BASELINE}')"),
        Index("idx_arena_runs_type_created", "run_type", "created_at"),
    )

    run_id: Mapped[str] = mapped_column(Text, primary_key=True)
    # replay 무결성 4종 (§8-2) — 이 넷이 같으면 같은 실험이다
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    ontology_version: Mapped[str] = mapped_column(Text, nullable=False)
    persona_state_version: Mapped[str] = mapped_column(Text, nullable=False)
    extractor_versions = mapped_column(JSONB, nullable=False)
    ktib_version: Mapped[str] = mapped_column(
        Text, ForeignKey("ktib_versions.ktib_version"), nullable=False
    )
    # 'brain'만 밝기를 만든다. baseline run은 3D에 새지 않는다(§8-2 베이스라인 규칙).
    run_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text(f"'{RUN_TYPE_BRAIN}'")
    )
    metrics = mapped_column(JSONB, nullable=False)
    confusion_matrix = mapped_column(JSONB)
    # clock_timestamp(): now()는 트랜잭션 시작 시각이라 한 트랜잭션의 여러 run이 같은 값을 갖고
    # '최신 run' 정렬이 비결정적이 된다(마이그레이션 0014). run 로그는 행 삽입 시각이어야 한다.
    created_at = mapped_column(DateTime(timezone=True), server_default=text("clock_timestamp()"))
