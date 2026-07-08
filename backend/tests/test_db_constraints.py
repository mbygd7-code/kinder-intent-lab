"""T1.3 AC (§3-4, 절대 규칙 2).

1. dataset_split=BENCHMARK_HOLDOUT + origin_channel=FOUNDRY_SYNTHETIC INSERT
   → DB CHECK(benchmark_integrity)로 IntegrityError
2. label_state=REVIEW_REQUIRED ∧ tier=GOLD 승격 시도 → 앱 레벨 차단
3. 모델(app/models)과 마이그레이션 스키마 동기
"""
import pytest
from sqlalchemy import inspect
from sqlalchemy.exc import IntegrityError

from app.models import Base, Episode
from app.models.guards import TierPromotionBlocked, promote_tier


def _episode(**overrides) -> Episode:
    base = dict(
        episode_id="EP_TEST_0001",
        ontology_version="onto-1.0",
        dataset_split="TRAIN",
        reliability_tier="UNVERIFIED",
        label_state="UNLABELED",
        origin_channel="FOUNDRY_SYNTHETIC",
        episode_creator_type="FOUNDRY_PIPELINE",
        primary_subject_type="SIMULATED_TEACHER",
        teacher_prompt="다음엔 뭘 해주면 좋을까?",
        label_distribution={"play_expand": 1.0},
    )
    base.update(overrides)
    return Episode(**base)


# --- AC 1: benchmark_integrity CHECK (DB 레벨) ---


def test_benchmark_holdout_rejects_foundry_synthetic(db_session) -> None:
    """LLM 합성 에피소드는 GOLD·LABELED여도 벤치마크에 못 들어간다."""
    db_session.add(
        _episode(
            episode_id="EP_AC1_SYN",
            dataset_split="BENCHMARK_HOLDOUT",
            reliability_tier="GOLD",
            label_state="LABELED",
            origin_channel="FOUNDRY_SYNTHETIC",
        )
    )
    with pytest.raises(IntegrityError, match="benchmark_integrity"):
        db_session.flush()


def test_benchmark_holdout_rejects_foundry_augmented(db_session) -> None:
    db_session.add(
        _episode(
            episode_id="EP_AC1_AUG",
            dataset_split="BENCHMARK_HOLDOUT",
            reliability_tier="GOLD",
            label_state="LABELED",
            origin_channel="FOUNDRY_AUGMENTED",
        )
    )
    with pytest.raises(IntegrityError, match="benchmark_integrity"):
        db_session.flush()


def test_benchmark_holdout_rejects_non_gold_tier(db_session) -> None:
    db_session.add(
        _episode(
            episode_id="EP_AC1_SILVER",
            dataset_split="BENCHMARK_HOLDOUT",
            reliability_tier="SILVER",
            label_state="LABELED",
            origin_channel="EXPERT_AUTHORED",
            episode_creator_type="HUMAN_ANNOTATOR",
            primary_subject_type="TEACHER",
        )
    )
    with pytest.raises(IntegrityError, match="benchmark_integrity"):
        db_session.flush()


def test_benchmark_holdout_accepts_gold_labeled_human_origin(db_session) -> None:
    """정상 경로: GOLD ∧ LABELED ∧ 비합성 origin은 통과한다."""
    db_session.add(
        _episode(
            episode_id="EP_AC1_OK",
            dataset_split="BENCHMARK_HOLDOUT",
            reliability_tier="GOLD",
            label_state="LABELED",
            origin_channel="EXPERT_AUTHORED",
            episode_creator_type="HUMAN_ANNOTATOR",
            primary_subject_type="TEACHER",
        )
    )
    db_session.flush()  # 예외 없어야 함 (이후 rollback으로 미영속)


# --- AC 2: 앱 레벨 tier 승격 차단 (§3-3: GOLD은 확정 라벨 보유) ---


def test_promote_to_gold_blocked_when_review_required(db_session) -> None:
    ep = _episode(episode_id="EP_AC2_BLOCK", label_state="REVIEW_REQUIRED")
    db_session.add(ep)
    db_session.flush()
    with pytest.raises(TierPromotionBlocked):
        promote_tier(ep, "GOLD")
    assert ep.reliability_tier == "UNVERIFIED"


def test_gold_with_review_required_blocked_at_flush(db_session) -> None:
    """promote_tier를 우회한 직접 대입도 flush에서 잡힌다."""
    ep = _episode(episode_id="EP_AC2_FLUSH", label_state="REVIEW_REQUIRED")
    db_session.add(ep)
    db_session.flush()
    ep.reliability_tier = "GOLD"
    with pytest.raises(TierPromotionBlocked):
        db_session.flush()


def test_promote_to_gold_allowed_when_labeled(db_session) -> None:
    ep = _episode(episode_id="EP_AC2_OK", label_state="LABELED")
    db_session.add(ep)
    db_session.flush()
    promote_tier(ep, "GOLD")
    db_session.flush()
    assert ep.reliability_tier == "GOLD"


def test_invalid_tier_name_rejected(db_session) -> None:
    ep = _episode(episode_id="EP_AC2_BADTIER", label_state="LABELED")
    db_session.add(ep)
    db_session.flush()
    with pytest.raises(ValueError):
        promote_tier(ep, "PLATINUM")


# --- 모델 ↔ 마이그레이션 동기 ---


def test_models_match_migrated_schema(migrated_engine) -> None:
    """app/models의 모든 테이블·컬럼·명명 인덱스가 마이그레이션 결과와 양방향 일치."""
    insp = inspect(migrated_engine)
    db_tables = set(insp.get_table_names()) - {"alembic_version"}
    model_tables = set(Base.metadata.tables.keys())
    assert db_tables == model_tables

    for table in sorted(model_tables):
        db_cols = {c["name"] for c in insp.get_columns(table)}
        model_cols = set(Base.metadata.tables[table].columns.keys())
        assert db_cols == model_cols, table

        # 001_init.sql의 명명 규칙(idx_*)을 따르는 인덱스만 대조
        db_idx = {
            i["name"] for i in insp.get_indexes(table)
            if i["name"] and i["name"].startswith("idx_")
        }
        model_idx = {
            i.name for i in Base.metadata.tables[table].indexes
            if i.name and i.name.startswith("idx_")
        }
        assert db_idx == model_idx, table
