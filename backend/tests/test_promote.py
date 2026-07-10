"""T4.6 AC (§6-6·§8-2): Promote / Reject 파이프라인.

- promote 규칙: global 상승 ∧ region 회귀 없음 ∧ critical 악화 없음 (config.version_gate)
- region 회귀 존재 시 promote 차단(→ reject)
- promote: 노드 brightness(heldout) 갱신 — 밝기의 유일한 쓰기 지점(§8-2·원칙 8) + pending 링 소등
  + Full Brain Resonance 이벤트
- reject: brightness·pending 불변, evidence 전량 보존, 회귀 원인 리포트
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select, update

from app.brain.promote import (
    ArenaOutcome,
    evaluate_promotion,
    resolve_candidate,
)
from app.brain.version_gate import build_candidate, current_base, version_gate_status
from app.core.config import get_config
from app.core.db import get_session
from app.core.ontology import load_ontology
from app.main import app
from app.models.arena import ArenaRun
from app.models.brain import BrainNode, BrainVersion, Exemplar
from app.models.episodes import Episode, Evidence
from app.models.governance import GovernanceEvent

CFG = get_config()


@pytest.fixture(autouse=True)
def _empty(db_session):
    """brain_versions·이벤트·evidence 비우고, 노드 brightness/pending을 알려진 상태로 리셋
    (세이브포인트 안 — 롤백으로 원복). brain_nodes 자체는 지우지 않는다(brightness 대상)."""
    db_session.execute(delete(Evidence))
    db_session.execute(delete(Exemplar))
    db_session.execute(delete(Episode))
    db_session.execute(delete(BrainVersion))
    db_session.execute(delete(GovernanceEvent))
    db_session.execute(update(BrainNode).values(
        heldout_accuracy=None, calibration_ece=None, last_arena_run=None, pending_evaluation=False
    ))
    db_session.flush()


def _intent(idx=0):
    return [i.intent_id for i in load_ontology().intents if i.domain][idx]


def _cfg(min_new_gold: int):
    return CFG.model_copy(
        update={"version_gate": CFG.version_gate.model_copy(update={"min_new_gold": min_new_gold})}
    )


def _gold(db, epid, intent):
    db.add(Episode(
        episode_id=epid, ontology_version="onto-1.0", lang="ko", dataset_split="TRAIN",
        reliability_tier="GOLD", label_state="LABELED", origin_channel="EXPERT_AUTHORED",
        episode_creator_type="HUMAN_ANNOTATOR", primary_subject_type="TEACHER",
        teacher_prompt="발화", label_distribution={intent: 1.0},
    ))


def _candidate(db) -> BrainVersion:
    row = BrainVersion(
        version="seed-v0-rc1", base="seed-v0", trigger="D_MODEL: new_gold 3",
        decision="candidate", delta={"gold_watermark": 3, "updated_nodes": [_intent(0)]},
    )
    db.add(row)
    db.flush()
    return row


def _outcome(**over):
    node = _intent(0)
    base = dict(
        run_id="AR_t46", global_delta=2.1, region_regressions=[], critical_worse=[],
        node_heldout={node: 0.62}, node_ece={node: 0.08},
    )
    base.update(over)
    return ArenaOutcome(**base)


# --- promote 규칙 평가 (순수) ---


def test_evaluate_promote_all_pass() -> None:
    d = evaluate_promotion(_outcome(), CFG)
    assert d.promote is True and d.reasons == []


def test_evaluate_region_regression_blocks() -> None:
    d = evaluate_promotion(_outcome(region_regressions=["VISUAL"]), CFG)
    assert d.promote is False and "region_regression" in d.reasons


def test_evaluate_critical_worse_blocks() -> None:
    d = evaluate_promotion(_outcome(critical_worse=["visual_naturalize"]), CFG)
    assert d.promote is False and "critical_worse" in d.reasons


def test_evaluate_global_not_up_blocks() -> None:
    assert evaluate_promotion(_outcome(global_delta=0.0), CFG).promote is False
    assert evaluate_promotion(_outcome(global_delta=-1.0), CFG).promote is False


def test_promote_rule_mismatch_loud_fails() -> None:
    """config.version_gate.promote_rule가 구현 규칙명과 다르면 loud-fail (규칙명 드리프트 가드)."""
    vg = CFG.version_gate.model_copy(update={"promote_rule": "some_other_rule"})
    bad = CFG.model_copy(update={"version_gate": vg})
    with pytest.raises(ValueError, match="promote_rule"):
        evaluate_promotion(_outcome(), bad)


# --- AC: region 회귀 시 promote 차단 (reject) ---


def test_region_regression_blocks_promotion_end_to_end(db_session) -> None:
    node = _intent(0)
    cand = _candidate(db_session)
    node_row = db_session.scalar(select(BrainNode).where(BrainNode.intent_id == node))
    node_row.pending_evaluation = True   # 훈련됨·검증 대기
    db_session.flush()

    result = resolve_candidate(
        db_session, cand, _outcome(region_regressions=["VISUAL"]), CFG
    )
    db_session.flush()
    assert result.decision == "reject"
    assert "region_regression" in result.reasons
    assert cand.decision == "reject"
    # 차단 시 brightness·pending 불변 (Arena 결과를 적용하지 않는다)
    db_session.refresh(node_row)
    assert node_row.heldout_accuracy is None            # 밝기 미갱신
    assert node_row.pending_evaluation is True          # ring 유지(아직 검증 대기)
    # Resonance 이벤트 없음
    assert db_session.scalar(
        select(func.count()).select_from(GovernanceEvent).where(
            GovernanceEvent.event_type == "FULL_BRAIN_RESONANCE"
        )
    ) == 0
    # 회귀 원인 리포트 기록
    assert "VISUAL" in cand.arena_result["region_regressions"]


# --- AC: reject 후 evidence 카운트 불변 ---


def test_reject_preserves_evidence(db_session) -> None:
    node = _intent(0)
    db_session.add(Episode(
        episode_id="EP_R", ontology_version="onto-1.0", lang="ko", dataset_split="TRAIN",
        reliability_tier="BRONZE", label_state="LABEL_CANDIDATE", origin_channel="GYM_HUMAN",
        episode_creator_type="GYM_SESSION", primary_subject_type="TEACHER",
        teacher_prompt="발화", label_distribution={node: 1.0},
    ))
    db_session.add(Evidence(
        evidence_id="EV_R", episode_id="EP_R", intent_id=node, polarity="supports",
        strength=0.9, evidence_type="HUMAN_CONFIRMATION", actor_type="TEACHER_TRAINER",
        adversarial=False,
    ))
    db_session.flush()
    ev_before = db_session.scalar(select(func.count()).select_from(Evidence))

    cand = _candidate(db_session)
    resolve_candidate(db_session, cand, _outcome(global_delta=-2.0), CFG)  # 차단 → reject
    db_session.flush()
    assert db_session.scalar(select(func.count()).select_from(Evidence)) == ev_before  # 불변


def test_reject_records_regression_report(db_session) -> None:
    """§6-6 reject 원인 리포트: 어떤 region·critical이 회귀했는지 arena_result.report에 기록."""
    cand = _candidate(db_session)
    resolve_candidate(
        db_session, cand,
        _outcome(region_regressions=["VISUAL"], critical_worse=["visual_naturalize"]), CFG,
    )
    db_session.flush()
    report = cand.arena_result["report"]
    assert "region_regression" in report["reasons"]
    assert "critical_worse" in report["reasons"]
    assert set(report["regressed"]) == {"VISUAL", "visual_naturalize"}


def test_promote_skips_missing_node(db_session) -> None:
    """실존하지 않는 intent가 섞여도 promote 성공 — 실존 노드만, 자동생성 없음(규칙4)."""
    node = _intent(0)
    cand = _candidate(db_session)
    nodes_before = db_session.scalar(select(func.count()).select_from(BrainNode))
    result = resolve_candidate(
        db_session, cand, _outcome(node_heldout={node: 0.6, "NOT_A_REAL_INTENT": 0.9}), CFG
    )
    db_session.flush()
    assert result.decision == "promote"
    assert result.nodes_brightened == 1  # 실존 노드(node)만
    after = db_session.scalar(select(func.count()).select_from(BrainNode))
    assert after == nodes_before  # 자동생성 0 (규칙 4)


# --- promote: brightness 갱신 + pending 소등 + Resonance ---


def test_promote_updates_brightness_clears_pending_resonance(db_session) -> None:
    node = _intent(0)
    cand = _candidate(db_session)
    node_row = db_session.scalar(select(BrainNode).where(BrainNode.intent_id == node))
    node_row.pending_evaluation = True
    db_session.flush()
    assert node_row.heldout_accuracy is None  # 시작: Dormant

    result = resolve_candidate(db_session, cand, _outcome(), CFG)
    db_session.flush()
    assert result.decision == "promote" and result.nodes_brightened == 1
    assert cand.decision == "promote"
    # 밝기 = Arena 결과 (§8-2 유일 원천), calibration·last_arena_run 기록, ring 소등
    db_session.refresh(node_row)
    assert node_row.heldout_accuracy == pytest.approx(0.62)
    assert node_row.calibration_ece == pytest.approx(0.08)
    assert node_row.last_arena_run == "AR_t46"
    assert node_row.pending_evaluation is False        # ring 소등 (§6-7 [9])
    # Full Brain Resonance 이벤트 1회
    ev = db_session.scalars(
        select(GovernanceEvent).where(GovernanceEvent.event_type == "FULL_BRAIN_RESONANCE")
    ).all()
    assert len(ev) == 1
    assert ev[0].payload["version"] == cand.version


def test_resolve_rejects_already_resolved(db_session) -> None:
    cand = _candidate(db_session)
    resolve_candidate(db_session, cand, _outcome(), CFG)  # promote
    db_session.flush()
    with pytest.raises(ValueError, match="이미"):
        resolve_candidate(db_session, cand, _outcome(), CFG)  # 재판정 거부


def test_promote_flows_to_observatory(db_session) -> None:
    """E2E: promote 후 3D brain에 새 버전·노드 밝기·KTIB가 흐른다(§8-2 밝기 원천)."""
    node = _intent(0)
    cand = _candidate(db_session)
    # ktib_global(arena metrics)와 node heldout(brain_nodes 컬럼)은 서로 다른 값 — 교차배선 탐지
    db_session.add(ArenaRun(
        run_id="AR_t46", model_version="v1", ontology_version="onto-1.0",
        persona_state_version="ps-1", extractor_versions={}, ktib_version="ktib-1",
        metrics={"first_intent_accuracy": 0.71},
    ))
    node_row = db_session.scalar(select(BrainNode).where(BrainNode.intent_id == node))
    node_row.pending_evaluation = True
    db_session.flush()

    result = resolve_candidate(  # promote
        db_session, cand, _outcome(node_heldout={node: 0.62}), CFG
    )
    db_session.flush()

    app.dependency_overrides[get_session] = lambda: db_session
    try:
        with TestClient(app) as client:
            body = client.get("/v1/observatory/brain").json()
    finally:
        app.dependency_overrides.clear()
    assert body["brain_version"] == "v1" == result.version  # rc 접미사 없는 clean 버전
    assert body["ktib_global"] == pytest.approx(0.71)      # Arena metrics → 중앙 수치(0.71)
    n = next(x for x in body["nodes"] if x["intent_id"] == node)
    assert n["heldout_accuracy"] == pytest.approx(0.62)    # 밝기 = 노드 heldout(0.62, 별개 경로)
    assert n["pending_evaluation"] is False                # ring 소등


# --- Phase 4 게이트: Version Gate 1회전 (candidate → Arena → 판정) ---


def test_version_gate_one_rotation_promote(db_session) -> None:
    """T4.5 build_candidate → T4.6 resolve_candidate(promote) 1회전. base·watermark가 전진한다."""
    node = _intent(0)
    for i in range(3):
        _gold(db_session, f"EP_{i}", _intent(i))
    db_session.flush()
    cfg = _cfg(min_new_gold=2)

    cand = build_candidate(db_session, cfg)                       # T4.5
    assert cand is not None and cand.decision == "candidate"
    result = resolve_candidate(db_session, cand, _outcome(node_heldout={node: 0.7}), cfg)  # T4.6
    db_session.flush()
    assert result.decision == "promote"

    # 판정 후: 현행 base가 promote된 버전으로 전진, watermark가 올라 증분이 리셋된다
    base = current_base(db_session)
    assert base is not None and base.version == cand.version
    assert version_gate_status(db_session, cfg).new_gold == 0     # 3(현재) − 3(promote watermark)
    assert version_gate_status(db_session, cfg).condition_met is False  # 다음 회전은 새 GOLD 필요
