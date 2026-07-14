"""브레인 운영실 대시보드 API AC — GET /v1/observatory/dashboard (읽기 전용 집계).

정직성 원칙이 곧 AC다:
- 측정 전 값은 null (0으로 위장 금지) · 유입 시계열의 0만 실제 0
- 기준선(하한·목표)은 config 원천 그대로 동봉 — 테스트도 리터럴 30 비교 금지
- run 비교는 같은 축(brain run ∧ 현행 뇌 ∧ 같은 ktib_version)만, 첫 run delta는 null
"""
import uuid
from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.config import get_config
from app.core.db import get_session
from app.core.ontology import load_ontology
from app.main import app
from app.models.arena import (
    NO_PERSONA_STATE,
    RUN_TYPE_BASELINE,
    RUN_TYPE_BRAIN,
    ArenaRun,
    KtibItem,
    KtibVersion,
)
from app.models.benchmark_candidates import (
    BenchmarkCandidateBatch,
    BenchmarkCandidateItem,
)
from app.models.brain import BrainNode, BrainVersion, Exemplar
from app.models.episodes import Episode, Evidence
from app.models.foundry import AtlasExpansionEntry

CFG = get_config()
NOW = datetime.now(UTC)


@pytest.fixture(autouse=True)
def _empty(db_session):
    """빈 슬레이트 — 실 KTIB·후보·큐가 카운트 전제를 깨지 않게 세이브포인트 안에서 비운다.

    FK 순서: arena/ktib → evidence류 → episode → node/version, 후보는 item → batch.
    """
    for model in (
        ArenaRun, KtibItem, KtibVersion,
        Evidence, Exemplar, Episode,
        BrainNode, BrainVersion,
        BenchmarkCandidateItem, BenchmarkCandidateBatch,
        AtlasExpansionEntry,
    ):
        db_session.execute(delete(model))
    db_session.flush()


@pytest.fixture()
def api(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        yield client, db_session
    app.dependency_overrides.clear()


def _episode(
    *,
    split="TRAIN",
    channel="FOUNDRY_SYNTHETIC",
    creator="FOUNDRY_PIPELINE",
    subject="SIMULATED_TEACHER",
    tier="SILVER",
    state="LABEL_CANDIDATE",
    intent="play_expand",
    created_at=None,
) -> Episode:
    return Episode(
        episode_id=f"EP_{uuid.uuid4().hex[:10]}",
        ontology_version="onto-test", lang="ko",
        dataset_split=split, reliability_tier=tier, label_state=state,
        origin_channel=channel, episode_creator_type=creator,
        primary_subject_type=subject,
        teacher_prompt=f"발화 {uuid.uuid4().hex[:6]}",
        label_distribution={intent: 1.0},
        created_at=created_at or NOW,
    )


def _ktib_version(db, seq=1) -> KtibVersion:
    v = KtibVersion(
        ktib_version=f"ktib-t{seq}", seq=seq, extractor_versions={},
        episode_count=1, content_hash=f"hash-{uuid.uuid4().hex}",
    )
    db.add(v)
    db.flush()
    return v


def _run(db, *, run_id, acc, created_at, model="seed-v0",
         run_type=RUN_TYPE_BRAIN, ktib="ktib-t1", metrics_extra=None) -> ArenaRun:
    run = ArenaRun(
        run_id=run_id, model_version=model, ontology_version="onto-test",
        persona_state_version=NO_PERSONA_STATE, extractor_versions={},
        ktib_version=ktib, run_type=run_type,
        metrics={"first_intent_accuracy": acc, "item_count": 10, "ece": 0.1,
                 **(metrics_extra or {})},
        created_at=created_at,
    )
    db.add(run)
    db.flush()
    return run


def _get(client) -> dict:
    res = client.get("/v1/observatory/dashboard")
    assert res.status_code == 200, res.text
    return res.json()


# --- AC1·AC2: 빈 뱅크의 정직성 + config 동봉 ---


def test_empty_bank_is_honest_and_carries_config(api) -> None:
    client, _ = api
    body = _get(client)

    # 성능: run이 없으면 축도 귀속도 없다 — 어떤 숫자도 0으로 위장되지 않는다
    perf = body["performance"]
    assert perf["axis"] is None and perf["runs"] == []
    assert perf["attribution_ready"] is False

    # 의도 63행 전부 측정 전(null) — 시험/공부 카운트는 실제 0
    rows = body["intents"]
    assert len(rows) == 63
    assert all(r["heldout_accuracy"] is None for r in rows)
    assert all(r["exam_registered"] == 0 and r["train"] == 0 for r in rows)
    # 하한(갭)은 CRITICAL에만 존재한다
    for r in rows:
        assert (r["gap_to_floor"] is not None) == r["is_critical"]

    sb = body["scoreboard"]
    assert sb["critical_met"] == 0 and sb["critical_total"] == len(CFG.arena.critical_intents)
    assert sb["current_ktib"] is None and sb["gold_total"] == 0
    assert body["inflow"]["shadow"]["total"] == 0

    # 기준선은 config 원천 그대로 (리터럴 비교 금지 — config에서 읽어 대조)
    assert body["config"]["critical_surface_min_items"] == CFG.gate.critical_surface_min_items
    assert body["config"]["gold_low_threshold"] == CFG.growth.gold_low_threshold
    assert body["config"]["first_intent_accuracy_target"] == CFG.arena.first_intent_accuracy_target
    assert body["config"]["min_agreement_kappa"] == CFG.review.min_agreement_kappa


# --- AC3: 유입 창 — 창 밖 도착은 total에만, last_days엔 안 나온다 ---


def test_inflow_window_splits_total_and_recent(api) -> None:
    client, db = api
    db.add(_episode(channel="FOUNDRY_SYNTHETIC"))                       # 오늘 도착
    db.add(_episode(channel="GYM_HUMAN", creator="GYM_SESSION", subject="TEACHER",
                    created_at=NOW - timedelta(days=CFG.dashboard.inflow_window_days + 1)))
    db.flush()

    inflow = _get(client)["inflow"]
    assert inflow["foundry"]["total"] == 1
    assert sum(d["count"] for d in inflow["foundry"]["last_days"]) == 1
    assert len(inflow["foundry"]["last_days"]) == CFG.dashboard.inflow_window_days
    # 창 밖(8일 전) 도착: 총량엔 있고 최근 창엔 없다
    assert inflow["human_teaching"]["total"] == 1
    assert sum(d["count"] for d in inflow["human_teaching"]["last_days"]) == 0


# --- AC4·AC5: run 타임라인 — 같은 축만, 첫 delta는 null, 유입 귀속 ---


def test_run_timeline_same_axis_deltas_and_attribution(api) -> None:
    client, db = api
    _ktib_version(db, seq=1)
    t1, t2 = NOW - timedelta(hours=2), NOW - timedelta(hours=1)
    _run(db, run_id="AR_1", acc=0.5, created_at=t1)
    # 두 run 사이 도착분 — 귀속 대상 (TRAIN 1 + GOLD TRAIN 1)
    db.add(_episode(created_at=t1 + timedelta(minutes=10)))
    db.add(_episode(channel="GYM_HUMAN", creator="GYM_SESSION", subject="TEACHER",
                    tier="GOLD", state="LABELED", created_at=t1 + timedelta(minutes=20)))
    _run(db, run_id="AR_2", acc=0.6, created_at=t2)
    # 배제 대상: 베이스라인 run·candidate run — 타임라인에 새면 §8-2/§6-6 위반
    _run(db, run_id="AR_BASE", acc=0.9, created_at=NOW, run_type=RUN_TYPE_BASELINE)
    _run(db, run_id="AR_RC", acc=0.99, created_at=NOW, model="seed-v0-rc1")
    db.flush()

    perf = _get(client)["performance"]
    assert perf["axis"] == {"ktib_version": "ktib-t1", "model_version": "seed-v0"}
    assert [r["run_id"] for r in perf["runs"]] == ["AR_1", "AR_2"]
    assert perf["attribution_ready"] is True

    first, second = perf["runs"]
    assert first["delta_pp"] is None and first["inflow_since_prev"] is None  # 비교 대상 없음
    assert second["delta_pp"] == 10.0
    assert second["inflow_since_prev"] == {
        "train_episodes": 2, "gold": 1, "benchmark_episodes": 0,
    }


def test_first_run_alone_is_not_attribution_ready(api) -> None:
    client, db = api
    _ktib_version(db, seq=1)
    _run(db, run_id="AR_ONLY", acc=0.55, created_at=NOW - timedelta(hours=1))
    db.flush()

    perf = _get(client)["performance"]
    assert len(perf["runs"]) == 1
    assert perf["attribution_ready"] is False
    assert perf["runs"][0]["delta_pp"] is None  # 0.0으로 위장하지 않는다


# --- AC6: 검수함 ---


def test_review_inbox_lists_batches_with_item_counts(api) -> None:
    client, db = api
    db.add(BenchmarkCandidateBatch(batch_id="B_1", created_by="김검수"))
    db.add(BenchmarkCandidateItem(item_id="I_1", batch_id="B_1",
                                  intent_id="play_expand", teacher_prompt="질문1", rating_a=5))
    db.add(BenchmarkCandidateItem(item_id="I_2", batch_id="B_1",
                                  intent_id="play_expand", teacher_prompt="질문2", rating_a=4))
    db.flush()

    body = _get(client)
    batch = body["review_inbox"][0]
    assert batch["batch_id"] == "B_1" and batch["item_count"] == 2
    assert batch["status"] == "AWAITING_SECOND" and batch["agreement_kappa"] is None
    assert body["scoreboard"]["review_awaiting_batches"] == 1


# --- AC7: 확장 스토리 — PENDING만, 예시 수는 온톨로지 실측과 대조 ---


def test_expansion_counts_pending_queue_and_ontology_examples(api) -> None:
    client, db = api
    for k, status in enumerate(("PENDING", "PENDING", "DISMISSED")):
        db.add(AtlasExpansionEntry(queue_id=f"Q_{k}", utterance=f"미매핑 {k}", status=status))
    db.flush()

    exp = _get(client)["expansion"]
    assert exp["atlas_queue_pending"] == 2  # DISMISSED는 확장 후보가 아니다

    onto = load_ontology()
    real = [i for i in onto.intents if i.domain]
    assert exp["intent_count"] == len(real)
    assert exp["positive_examples_total"] == sum(len(i.positive_examples) for i in real)
    assert exp["ontology_version"] == onto.version
