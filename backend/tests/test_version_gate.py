"""T4.5 AC (§6-6): Version Gate + Candidate Build.

- candidate 생성 조건: 신규 GOLD ≥ config.version_gate.min_new_gold (base 대비 watermark 차)
- 조건 미달 → candidate 미생성 (brain_versions 무변화)
- candidate 빌드는 현행(promote) 버전을 절대 건드리지 않는다 — 새 행 INSERT만, exemplar/edge 무변화,
  observatory brain_version(promote만 읽음)도 불변
- candidate는 delta(updated_nodes/edges·gold_watermark·persona_state_version)를 기록
임계는 config.version_gate(절대 규칙 1). Arena 시험·promote/reject는 T4.6.
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.brain.backfill import bootstrap_nodes
from app.brain.priors import current_state_version, issue_state_version
from app.brain.version_gate import (
    build_candidate,
    current_base,
    new_gold_since_base,
    version_gate_status,
)
from app.core.config import get_config
from app.core.db import get_session
from app.core.ontology import load_ontology
from app.main import app
from app.models.arena import KtibItem, KtibVersion
from app.models.brain import BrainNode, BrainVersion, ConfusionEdge, Exemplar
from app.models.episodes import Episode, Evidence
from app.models.persona import PersonaStateVersion

CFG = get_config()


@pytest.fixture(autouse=True)
def _empty(db_session):
    """빈 뱅크 전제 — brain_versions·GOLD 카운트가 실 DB 잔량에 안 오염되게(FK: 자식 먼저)."""
    # ktib_items → episodes FK: KtibItem/KtibVersion을 Episode보다 먼저(벤치마크 episode 대응)
    for model in (KtibItem, KtibVersion, Evidence, Exemplar, Episode,
                  ConfusionEdge, BrainVersion, PersonaStateVersion):
        db_session.execute(delete(model))
    db_session.flush()


def _cfg(min_new_gold: int):
    return CFG.model_copy(
        update={"version_gate": CFG.version_gate.model_copy(update={"min_new_gold": min_new_gold})}
    )


def _intent(idx=0):
    return [i.intent_id for i in load_ontology().intents if i.domain][idx]


def _gold(db, epid, intent):
    db.add(Episode(
        episode_id=epid, ontology_version="onto-1.0", lang="ko", dataset_split="TRAIN",
        reliability_tier="GOLD", label_state="LABELED", origin_channel="EXPERT_AUTHORED",
        episode_creator_type="HUMAN_ANNOTATOR", primary_subject_type="TEACHER",
        teacher_prompt="발화", label_distribution={intent: 1.0},
    ))


def _n_versions(db) -> int:
    return db.scalar(select(func.count()).select_from(BrainVersion))


# --- AC: 조건 미달 → candidate 미생성 ---


def test_below_threshold_no_candidate(db_session) -> None:
    _gold(db_session, "EP_G1", _intent(0))  # GOLD 1건
    db_session.flush()
    result = build_candidate(db_session, _cfg(min_new_gold=2))  # 2 필요, 1뿐
    assert result is None
    assert _n_versions(db_session) == 0  # brain_versions 무변화


def test_no_gold_no_candidate(db_session) -> None:
    assert build_candidate(db_session, _cfg(min_new_gold=1)) is None
    assert _n_versions(db_session) == 0


# --- AC: 조건 충족 → candidate 빌드 + delta 기록 ---


def test_condition_met_builds_candidate(db_session) -> None:
    a, b, c = _intent(0), _intent(1), _intent(2)
    _gold(db_session, "EP_A", a)
    _gold(db_session, "EP_B", b)
    _gold(db_session, "EP_C", c)  # GOLD 3건
    # 신호 있는 edge 하나
    db_session.add(ConfusionEdge(
        edge_id="CE_v", from_true=a, to_predicted=b, confusion_rate=0.4, state="observed",
    ))
    db_session.flush()

    cand = build_candidate(db_session, _cfg(min_new_gold=2))
    assert cand is not None
    assert cand.decision == "candidate"
    assert cand.base == "seed-v0"                    # 최초 promote 없음 → seed 기준
    assert cand.version.startswith("seed-v0-rc")
    assert cand.delta["gold_watermark"] == 3
    assert set(cand.delta["updated_nodes"]) == {a, b, c}
    assert "CE_v" in cand.delta["updated_edges"]
    assert _n_versions(db_session) == 1


def test_candidate_records_persona_state_version(db_session) -> None:
    _gold(db_session, "EP_A", _intent(0))
    _gold(db_session, "EP_B", _intent(1))
    v = issue_state_version(db_session, reason="seed")
    db_session.flush()
    cand = build_candidate(db_session, _cfg(min_new_gold=1))
    assert cand.delta["persona_state_version"] == v == current_state_version(db_session)


# --- AC: 현행(promote) 버전 불변성 ---


def test_candidate_does_not_touch_current_promoted_version(db_session) -> None:
    a = _intent(0)
    # 현행 promote 버전 + 그 시점 exemplar/edge
    promoted = BrainVersion(
        version="v1", base="seed-v0", trigger="seed", decision="promote",
        delta={"gold_watermark": 0},
    )
    db_session.add(promoted)
    bootstrap_nodes(db_session, approved_by="lab")  # 노드 보장 → exemplar FK 성립(가드 falsifiable)
    db_session.flush()
    node = db_session.scalar(select(BrainNode).where(BrainNode.intent_id == a))
    assert node is not None
    db_session.add(Episode(  # exemplar FK 대상 — 에피소드 먼저
        episode_id="EP_KEEP", ontology_version="onto-1.0", lang="ko", dataset_split="TRAIN",
        reliability_tier="GOLD", label_state="LABELED", origin_channel="EXPERT_AUTHORED",
        episode_creator_type="HUMAN_ANNOTATOR", primary_subject_type="TEACHER",
        teacher_prompt="발화", label_distribution={a: 1.0},
    ))
    db_session.flush()
    db_session.add(Exemplar(
        exemplar_id="EX_keep", node_id=node.node_id, intent_id=a, episode_id="EP_KEEP",
        embedding=[0.0] * 1536,
    ))
    db_session.add(ConfusionEdge(
        edge_id="CE_keep", from_true=a, to_predicted=_intent(1), confusion_rate=0.3,
        state="observed",
    ))
    db_session.flush()
    ex_before = db_session.scalar(select(func.count()).select_from(Exemplar))
    edge_before = db_session.scalar(select(func.count()).select_from(ConfusionEdge))
    assert ex_before >= 1 and edge_before >= 1  # 가드가 vacuous(0==0) 아님을 보장

    for i in range(3):  # base watermark 0 → 신규 GOLD 3건(+EP_KEEP=4) 충분
        _gold(db_session, f"EP_new_{i}", _intent(i))
    db_session.flush()
    cand = build_candidate(db_session, _cfg(min_new_gold=2))

    assert cand is not None and cand.base == "v1"     # 현행 promote가 base
    # 현행 promote 행 그대로 (건드리지 않음)
    kept = db_session.get(BrainVersion, "v1")
    assert kept.decision == "promote" and kept.delta == {"gold_watermark": 0}
    # exemplar/edge 무변화 — 후보 빌드는 읽기만 한다
    assert db_session.scalar(select(func.count()).select_from(Exemplar)) == ex_before
    assert db_session.scalar(select(func.count()).select_from(ConfusionEdge)) == edge_before


def test_new_gold_measured_against_base_watermark(db_session) -> None:
    """new_gold = 현재 GOLD − base의 gold_watermark (누적 아님, 증분)."""
    db_session.add(BrainVersion(
        version="v1", base="seed-v0", trigger="seed", decision="promote",
        delta={"gold_watermark": 5},
    ))
    for i in range(6):  # 현재 GOLD 6건
        _gold(db_session, f"EP_{i}", _intent(i % 3))
    db_session.flush()
    assert new_gold_since_base(db_session) == 6 - 5  # = 1
    assert build_candidate(db_session, _cfg(min_new_gold=2)) is None   # 1 < 2 → 미생성
    assert build_candidate(db_session, _cfg(min_new_gold=1)) is not None  # 1 ≥ 1 → 생성


# --- 멱등: 대기 중 candidate가 있으면 재빌드하지 않는다 ---


def test_pending_candidate_is_idempotent(db_session) -> None:
    for i in range(3):
        _gold(db_session, f"EP_{i}", _intent(i))
    db_session.flush()
    first = build_candidate(db_session, _cfg(min_new_gold=2))
    db_session.flush()
    second = build_candidate(db_session, _cfg(min_new_gold=2))
    assert first is not None and second is not None
    assert first.version == second.version          # 같은 대기 candidate 반환
    assert _n_versions(db_session) == 1             # 중복 INSERT 없음


# --- 상태 리포트 ---


def test_version_gate_status(db_session) -> None:
    for i in range(3):
        _gold(db_session, f"EP_{i}", _intent(i))
    db_session.flush()
    status = version_gate_status(db_session, _cfg(min_new_gold=2))
    assert status.new_gold == 3
    assert status.min_new_gold == 2
    assert status.condition_met is True
    assert status.base_version == "seed-v0"
    assert status.pending_candidate is None         # 아직 안 지음


def test_current_base_is_latest_promote(db_session) -> None:
    db_session.add(BrainVersion(version="v1", base="seed-v0", decision="promote", delta={}))
    db_session.add(BrainVersion(version="v1-rc1", base="v1", decision="candidate", delta={}))
    db_session.flush()
    base = current_base(db_session)
    assert base is not None and base.version == "v1"  # candidate 아니라 최신 promote


# --- API: GET /v1/observatory/version-gate (읽기 전용 상태) ---


def test_version_gate_endpoint(db_session) -> None:
    for i in range(2):
        _gold(db_session, f"EP_{i}", _intent(i))
    db_session.flush()
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        with TestClient(app) as client:
            r = client.get("/v1/observatory/version-gate")
    finally:
        app.dependency_overrides.clear()
    assert r.status_code == 200
    body = r.json()
    assert body["base_version"] == "seed-v0"
    assert body["new_gold"] == 2
    assert body["min_new_gold"] == CFG.version_gate.min_new_gold
    assert body["pending_candidate"] is None


def test_candidate_does_not_change_observatory_brain_version(db_session) -> None:
    """AC(b) E2E: candidate 빌드 후에도 observatory brain_version은 현행 promote 그대로."""
    db_session.add(BrainVersion(
        version="v1", base="seed-v0", trigger="seed", decision="promote",
        delta={"gold_watermark": 0},
    ))
    for i in range(3):
        _gold(db_session, f"EP_{i}", _intent(i))
    db_session.flush()
    cand = build_candidate(db_session, _cfg(min_new_gold=2))
    assert cand is not None and cand.decision == "candidate"
    db_session.flush()
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        with TestClient(app) as client:
            body = client.get("/v1/observatory/brain").json()
    finally:
        app.dependency_overrides.clear()
    assert body["brain_version"] == "v1"          # 현행 promote — candidate로 안 바뀐다
    assert body["brain_version"] != cand.version


def test_endpoint_surfaces_pending_candidate(db_session) -> None:
    """version-gate 엔드포인트가 대기 candidate 버전을 그대로 노출한다(non-null 경로)."""
    for i in range(3):
        _gold(db_session, f"EP_{i}", _intent(i))
    db_session.flush()
    cand = build_candidate(db_session, _cfg(min_new_gold=2))
    db_session.flush()
    assert version_gate_status(db_session, _cfg(min_new_gold=2)).pending_candidate == cand.version
    app.dependency_overrides[get_session] = lambda: db_session
    try:
        with TestClient(app) as client:
            body = client.get("/v1/observatory/version-gate").json()
    finally:
        app.dependency_overrides.clear()
    assert body["pending_candidate"] == cand.version
