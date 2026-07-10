"""T5.4 AC (§7-5·§7-6, 절대 규칙 3): Arena → Observatory 반영.

- ★ AC: **arena 외 코드 경로에서 brightness UPDATE 시도 시 가드로 실패**
- 반영 잡: arena 결과만 brightness·edge flicker를 갱신한다
- zero-shot 베이스라인 run은 3D 반영 대상이 아니다 (ktib_global로도 새지 않는다)
- §7-6 성장 스테이지 · Persona Overlay
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, update

from app.arena.reflect import BaselineRunNotReflectable, reflect_arena_run
from app.arena.stages import STAGE_NAMES, brain_stage, region_stage, region_stages
from app.brain.backfill import bootstrap_nodes
from app.brain.promote import ArenaOutcome, resolve_candidate
from app.core.config import get_config
from app.core.db import get_session
from app.core.ontology import load_ontology
from app.main import app
from app.models.arena import RUN_TYPE_BASELINE, RUN_TYPE_BRAIN, ArenaRun, KtibItem, KtibVersion
from app.models.brain import BrainNode, BrainVersion, ConfusionEdge, Exemplar
from app.models.episodes import Episode, Evidence
from app.models.foundry import CanonicalScenario
from app.models.governance import GovernanceEvent
from app.models.guards import BrightnessWriteBlocked, arena_brightness_write
from app.models.persona import PersonaCluster, PersonaStateVersion, PopulationPrior

CFG = get_config()


@pytest.fixture(autouse=True)
def _empty(db_session):
    for model in (ArenaRun, KtibItem, KtibVersion, ConfusionEdge, Exemplar, Evidence, Episode,
                  CanonicalScenario, PopulationPrior, PersonaCluster, PersonaStateVersion,
                  BrainVersion, GovernanceEvent, BrainNode):
        db_session.execute(delete(model))
    db_session.flush()
    bootstrap_nodes(db_session, approved_by="lab")
    db_session.flush()


def _intent(i=0) -> str:
    return [x.intent_id for x in load_ontology().intents if x.domain][i]


def _node(db, intent) -> BrainNode:
    return db.scalar(select(BrainNode).where(BrainNode.intent_id == intent))


# --- ★ AC: brightness 쓰기 가드 (절대 규칙 3) ---


def test_brightness_write_outside_arena_context_is_blocked(db_session) -> None:
    """★ arena 반영 경로 밖에서 heldout_accuracy를 대입하면 flush에서 실패한다."""
    node = _node(db_session, _intent(0))
    node.heldout_accuracy = 0.99
    with pytest.raises(BrightnessWriteBlocked, match="절대 규칙 3"):
        db_session.flush()
    db_session.rollback()


@pytest.mark.parametrize("field,value", [
    ("heldout_accuracy", 0.5), ("calibration_ece", 0.1), ("last_arena_run", "AR_forged"),
])
def test_every_brightness_field_is_guarded(db_session, field, value) -> None:
    """heldout뿐 아니라 ece·last_arena_run도 Arena 전용이다 (§7-5 Brightness 계열 전체)."""
    node = _node(db_session, _intent(0))
    setattr(node, field, value)
    with pytest.raises(BrightnessWriteBlocked):
        db_session.flush()
    db_session.rollback()


def test_non_brightness_fields_are_free(db_session) -> None:
    """훈련이 만지는 size/density/pending은 가드 밖 — 훈련은 계속 즉시 반영된다(§6-5)."""
    node = _node(db_session, _intent(0))
    node.pending_evaluation = True
    node.evidence_stats = {"gold": 3}
    db_session.flush()  # 통과해야 한다
    db_session.refresh(node)
    assert node.pending_evaluation is True


def test_arena_context_requires_matching_attribution(db_session) -> None:
    """컨텍스트 안이어도 last_arena_run이 반영 중인 run과 다르면 차단 — 귀속 없는 밝기는 무의미."""
    node = _node(db_session, _intent(0))
    with arena_brightness_write("AR_real"):
        node.heldout_accuracy = 0.44
        node.last_arena_run = "AR_other"   # 다른 run으로 귀속시키려 함
        with pytest.raises(BrightnessWriteBlocked, match="귀속 불가"):
            db_session.flush()
    db_session.rollback()


def test_arena_context_allows_attributed_write(db_session) -> None:
    """올바르게 귀속된 쓰기는 통과한다 — 가드는 봉쇄가 아니라 경로 강제다."""
    node = _node(db_session, _intent(0))
    with arena_brightness_write("AR_real"):
        node.heldout_accuracy = 0.44
        node.calibration_ece = 0.07
        node.last_arena_run = "AR_real"
        db_session.flush()
    db_session.refresh(node)
    assert node.heldout_accuracy == 0.44


def test_empty_run_id_rejected(db_session) -> None:
    with pytest.raises(BrightnessWriteBlocked, match="run_id 없이"):
        with arena_brightness_write(""):
            pass


def test_promote_path_still_writes_brightness(db_session) -> None:
    """유일하게 허용된 경로(promote)는 여전히 동작한다 — 가드가 정상 경로를 막지 않는다."""
    intent = _intent(0)
    cand = BrainVersion(version="seed-v0-rc1", base="seed-v0", trigger="t",
                        decision="candidate", delta={})
    db_session.add(cand)
    db_session.flush()

    outcome = ArenaOutcome(run_id="AR_ok", global_delta=2.0, region_regressions=[],
                           critical_worse=[], node_heldout={intent: 0.44}, node_ece={intent: 0.08})
    result = resolve_candidate(db_session, cand, outcome, CFG)
    db_session.flush()

    assert result.decision == "promote" and result.nodes_brightened == 1
    node = _node(db_session, intent)
    assert node.heldout_accuracy == 0.44 and node.last_arena_run == "AR_ok"


# --- 반영 잡: edge flicker + 베이스라인 분리 ---


def _run(db, run_type=RUN_TYPE_BRAIN, matrix=None, by_node=None,
         model_version="seed-v0", run_id=None) -> ArenaRun:
    if db.get(KtibVersion, "ktib-1") is None:
        db.add(KtibVersion(ktib_version="ktib-1", seq=1, extractor_versions={}, episode_count=1,
                           content_hash="h1"))
        db.flush()
    run = ArenaRun(
        run_id=run_id or f"AR_{run_type}_{model_version}", model_version=model_version,
        ontology_version="onto-1.0", persona_state_version="none", extractor_versions={},
        ktib_version="ktib-1", run_type=run_type,
        metrics={"by_node": by_node or {}}, confusion_matrix=matrix or [],
    )
    db.add(run)
    db.flush()
    return run


def test_reflect_updates_edge_flicker(db_session) -> None:
    """반영 잡이 confusion_rate(= edge flicker, §7-5)를 갱신하고 confirmed로 올린다."""
    a, b = _intent(0), _intent(1)
    run = _run(
        db_session,
        matrix=[{"from_true": a, "to_predicted": b, "count": 3,
                 "confusion_rate": 0.31, "confirmed": True}],
        by_node={a: {"n": 3, "correct": 0, "accuracy": 0.0, "ece": None}},
    )
    result = reflect_arena_run(db_session, run, CFG, promoted=False)
    assert result.edges_touched == 1 and result.resonance is False

    edge = db_session.scalar(
        select(ConfusionEdge).where(ConfusionEdge.from_true == a, ConfusionEdge.to_predicted == b)
    )
    assert edge.confusion_rate == 0.31 and edge.state == "confirmed"


def test_regular_run_on_base_brightens_but_keeps_pending(db_session) -> None:
    """정기 run이 **현행 뇌**를 재면 그 숫자가 곧 밝기다 (§7-6 Stage 1 Spark = 측정 1회 이상).

    단 pending 링은 끄지 않는다 — 이 run은 candidate의 훈련을 검증한 것이 아니다(§6-5).
    """
    a = _intent(0)
    node = _node(db_session, a)
    node.pending_evaluation = True     # 훈련됨·검증 대기
    db_session.flush()

    run = _run(db_session, model_version="seed-v0",  # base(promote 없음) == seed-v0
               by_node={a: {"n": 3, "correct": 1, "accuracy": 0.31, "ece": 0.12}})
    result = reflect_arena_run(db_session, run, CFG, promoted=False)
    assert result.nodes_brightened == 1

    db_session.refresh(node)
    assert node.heldout_accuracy == 0.31          # §6-7 [0] "brightness 31%"
    assert node.calibration_ece == 0.12
    assert node.last_arena_run == run.run_id
    assert node.pending_evaluation is True        # ★ 링은 promote만 끈다(§6-7 [9])


def test_unpromoted_candidate_run_never_brightens(db_session) -> None:
    """★ candidate를 잰 숫자는 아직 뇌의 것이 아니다 — 승격 없이 밝아지는 경로는 없다(§6-7 [9])."""
    a = _intent(0)
    run = _run(db_session, model_version="seed-v0-rc1",  # base가 아니라 candidate를 잼
               by_node={a: {"n": 3, "correct": 3, "accuracy": 1.0, "ece": 0.0}})
    result = reflect_arena_run(db_session, run, CFG, promoted=False)
    assert result.nodes_brightened == 0
    assert _node(db_session, a).heldout_accuracy is None


def test_promoted_run_does_not_double_write(db_session) -> None:
    """promote 경로가 이미 밝기를 켰으므로 반영 잡은 다시 쓰지 않는다."""
    a = _intent(0)
    run = _run(db_session, model_version="seed-v0-rc1",
               by_node={a: {"n": 3, "correct": 3, "accuracy": 1.0, "ece": 0.0}})
    result = reflect_arena_run(db_session, run, CFG, promoted=True)
    assert result.nodes_brightened == 0 and result.resonance is True


def test_baseline_run_cannot_be_reflected(db_session) -> None:
    """§8-2: zero-shot 베이스라인 run은 3D 반영 대상이 아니다."""
    run = _run(db_session, run_type=RUN_TYPE_BASELINE)
    with pytest.raises(BaselineRunNotReflectable):
        reflect_arena_run(db_session, run, CFG)


# --- §7-6 성장 스테이지 ---


def test_region_stage_ladder() -> None:
    """0 Dormant → 1 Spark → 2 Cluster Awake → 3 Region Online (높은 단계 우선)."""
    assert region_stage(None, 10, 0, CFG) == 0                    # 미측정
    assert region_stage(0.2, 10, 1, CFG) == 1                     # 측정 1건, 낮은 신뢰도
    assert region_stage(0.2, 10, 5, CFG) == 2                     # 절반 측정
    assert region_stage(CFG.stages.region_online_reliability, 10, 5, CFG) == 3
    assert region_stage(0.99, 10, 1, CFG) == 3                    # 신뢰도가 비율보다 우선


def test_stage_4_is_never_emitted() -> None:
    """Stage 4(Cross-Region Flow)는 '인접 region' 정의가 없어 판정하지 않는다 — 지어내지 않는다."""
    assert all(region_stage(r, 10, m, CFG) != 4
               for r in (None, 0.0, 0.5, 0.7, 1.0) for m in (0, 1, 5, 10))


def test_region_stages_ignores_unmeasured_nodes_in_reliability(db_session) -> None:
    """reliability는 측정된 노드만 평균낸다 — 미측정을 0%로 끌어내리지 않는다."""
    a = _intent(0)
    region = {i.intent_id: i.domain for i in load_ontology().intents}[a]
    db_session.execute(
        update(BrainNode).where(BrainNode.intent_id == a).values(heldout_accuracy=0.9)
    )
    db_session.flush()
    stages = region_stages(db_session, CFG)
    assert stages[region].reliability == 0.9      # 다른 미측정 노드가 평균을 끌어내리지 않음
    assert stages[region].measured_count == 1
    assert stages[region].node_count > 1


def test_brain_stage_5_only_at_target(db_session) -> None:
    """§7-6 Stage 5 = global ≥ KTIB 목표. 목표 미달이면 region 최고 단계."""
    stages = region_stages(db_session, CFG)
    target = CFG.arena.first_intent_accuracy_target
    assert brain_stage(target, stages, CFG) == 5
    assert brain_stage(target - 0.01, stages, CFG) == 0   # 전부 Dormant
    assert brain_stage(None, stages, CFG) == 0
    assert STAGE_NAMES[5] == "Whole Brain Resonance"


# --- Observatory API ---


@pytest.fixture()
def api(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_brain_endpoint_exposes_stages(api, db_session) -> None:
    body = api.get("/v1/observatory/brain").json()
    assert body["brain_stage"] == 0 and body["brain_stage_name"] == "Dormant"
    assert all(r["stage"] == 0 and r["measured_count"] == 0 for r in body["regions"])


def test_baseline_run_does_not_leak_into_ktib_global(api, db_session) -> None:
    """★ §8-2: 베이스라인 run이 3D 뇌의 중앙 수치를 바꾸지 않는다."""
    db_session.add(KtibVersion(ktib_version="ktib-1", seq=1, extractor_versions={},
                               episode_count=1, content_hash="h1"))
    db_session.flush()
    db_session.add(ArenaRun(
        run_id="AR_base", model_version="zero_shot:m", ontology_version="onto-1.0",
        persona_state_version="none", extractor_versions={}, ktib_version="ktib-1",
        run_type=RUN_TYPE_BASELINE, metrics={"first_intent_accuracy": 0.77}, confusion_matrix=[],
    ))
    db_session.flush()

    body = api.get("/v1/observatory/brain").json()
    assert body["ktib_global"] is None   # 베이스라인은 밝기 원천이 아니다
    assert body["brain_stage"] == 0


def test_brain_run_sets_ktib_global(api, db_session) -> None:
    db_session.add(KtibVersion(ktib_version="ktib-1", seq=1, extractor_versions={},
                               episode_count=1, content_hash="h1"))
    db_session.flush()
    db_session.add(ArenaRun(
        run_id="AR_brain", model_version="seed-v0", ontology_version="onto-1.0",
        persona_state_version="none", extractor_versions={}, ktib_version="ktib-1",
        run_type=RUN_TYPE_BRAIN, metrics={"first_intent_accuracy": 0.81}, confusion_matrix=[],
    ))
    db_session.flush()
    body = api.get("/v1/observatory/brain").json()
    assert body["ktib_global"] == 0.81
    assert body["brain_stage"] == 5 and body["brain_stage_name"] == "Whole Brain Resonance"


def test_rejected_candidate_never_becomes_the_brains_headline(api, db_session) -> None:
    """★ CRITICAL 회귀: reject된 후보의 높은 global이 3D 뇌의 중앙 수치·스테이지로 새면 안 된다.

    §6-6 "reject → 숫자는 폐기된다". 후보 run도 run_type='brain'이라, model_version으로 걸러내지
    않으면 최신 run이 곧 뇌의 상태가 되어 버린다(존재하지 않는 뇌를 렌더).
    """
    db_session.add(KtibVersion(ktib_version="ktib-1", seq=1, extractor_versions={},
                               episode_count=1, content_hash="h1"))
    db_session.flush()
    # 현행 뇌(seed-v0)를 잰 run — 낮은 점수
    db_session.add(ArenaRun(
        run_id="AR_base", model_version="seed-v0", ontology_version="onto-1.0",
        persona_state_version="none", extractor_versions={}, ktib_version="ktib-1",
        run_type=RUN_TYPE_BRAIN, metrics={"first_intent_accuracy": 0.42}, confusion_matrix=[],
    ))
    db_session.flush()
    # region 회귀로 reject된 후보를 잰 run — global은 목표를 넘었다
    db_session.add(BrainVersion(version="seed-v0-rc1", base="seed-v0", trigger="t",
                                delta={}, decision="reject",
                                arena_result={"run_id": "AR_cand"}))
    db_session.add(ArenaRun(
        run_id="AR_cand", model_version="seed-v0-rc1", ontology_version="onto-1.0",
        persona_state_version="none", extractor_versions={}, ktib_version="ktib-1",
        run_type=RUN_TYPE_BRAIN, metrics={"first_intent_accuracy": 0.95}, confusion_matrix=[],
    ))
    db_session.flush()

    body = api.get("/v1/observatory/brain").json()
    assert body["brain_version"] == "seed-v0"   # promote 없음 — 여전히 seed
    assert body["ktib_global"] == 0.42          # ★ 0.95가 아니다
    assert body["brain_stage"] != 5             # 목표 도달로 렌더되지 않는다


def test_candidate_run_excluded_from_stage4_window(db_session) -> None:
    """★ 같은 뿌리: Stage 4 추세 윈도도 현행 뇌를 잰 run만 본다."""
    from app.arena.stages import stage4_inputs

    db_session.add(KtibVersion(ktib_version="ktib-1", seq=1, extractor_versions={},
                               episode_count=1, content_hash="h1"))
    db_session.flush()
    for run_id, mv in (("AR_base", "seed-v0"), ("AR_cand", "seed-v0-rc1")):
        db_session.add(ArenaRun(
            run_id=run_id, model_version=mv, ontology_version="onto-1.0",
            persona_state_version="none", extractor_versions={}, ktib_version="ktib-1",
            run_type=RUN_TYPE_BRAIN, metrics={"by_node": {}}, confusion_matrix=[],
        ))
        db_session.flush()

    _edges, history = stage4_inputs(db_session, CFG)
    assert [r.run_id for r in history] == ["AR_base"]


# --- Persona Overlay ---


def test_persona_overlay_empty_without_clusters(api, db_session) -> None:
    """클러스터가 없으면 빈 목록 — 분포를 지어내지 않는다."""
    body = api.get("/v1/observatory/persona-overlay").json()
    assert body["clusters"] == []
    assert body["prior_cap"] == CFG.brain.persona_prior_cap


def test_persona_overlay_returns_cluster_prior_distribution(api, db_session) -> None:
    """§7-6 Persona Overlay: 클러스터별 prior 분포를 현재 state_version에서 읽는다."""
    a, b = _intent(0), _intent(1)
    db_session.add(PersonaStateVersion(version="ps-1", seq=1, reason="test"))
    db_session.add(PersonaCluster(cluster_id="PC_1", method="hdbscan", axes={},
                                  member_count=12, version="pv-1"))
    db_session.flush()
    db_session.add_all([
        PopulationPrior(cluster_id="PC_1", intent_id=a, prior=0.7, state_version="ps-1"),
        PopulationPrior(cluster_id="PC_1", intent_id=b, prior=0.3, state_version="ps-1"),
        # 구 state_version의 prior는 섞이지 않는다
        PopulationPrior(cluster_id="PC_1", intent_id=a, prior=0.1, state_version="ps-0"),
    ])
    db_session.flush()

    body = api.get("/v1/observatory/persona-overlay").json()
    assert body["state_version"] == "ps-1"
    assert len(body["clusters"]) == 1
    cluster = body["clusters"][0]
    assert cluster["cluster_id"] == "PC_1" and cluster["member_count"] == 12
    assert cluster["priors"] == {a: pytest.approx(0.7), b: pytest.approx(0.3)}
