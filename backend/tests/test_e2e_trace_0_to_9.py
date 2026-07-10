"""T5.5 AC: §6-7 End-to-End Trace [0]~[9] 전체 체인 통합 테스트.

    [0] 관찰     3D Brain에서 노드가 어둡다 (brightness = Arena run의 heldout)
    [1] 클릭     진단 엔진(§7-3): CONFUSION_HIGH + GOLD_LOW
    [2] 전략     진단 → 강화 유형(§6-1) → Challenge Pack(§6-4)
    [3] 출제     Gym trainer 큐로 발행
    [4] 상호작용 세션 산출 → HUMAN evidence 적재
    [5] 집계     Label Aggregator(§3-6) → LABEL_CANDIDATE·SILVER → 사람 검수 → LABELED·GOLD
    [6] 즉시반영 size↑ density↑ + pending_evaluation 링. **brightness 불변** (원칙 8)
    [7] 후보     Version Gate(§6-6) 충족 → candidate 빌드
    [8] 시험     Arena 전체 실행 — replay 무결성 4버전 기록
    [9] 판정     promote 규칙 → brightness 상승 · edge flicker 감소 · pending 소등 · Resonance

"이 체인의 어느 단계도 건너뛸 수 없다 — 특히 [4]→[6]에서 밝기가 바로 오르는 지름길은
구조적으로 존재하지 않는다." (§6-7)

각 단계의 산출물(pack / evidence / aggregation / candidate / arena run / promote)이 DB에
계보로 남는지 함께 단언한다.
"""
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, func, select

from app.aggregator.state_machine import advance_label_state
from app.arena.ktib import build_ktib
from app.arena.reflect import reflect_arena_run
from app.arena.runner import baseline_run, build_outcome, run_arena
from app.brain.backfill import aggregate_evidence_stats, bootstrap_nodes, select_exemplars
from app.brain.diagnosis import diagnose_node
from app.brain.promote import RESONANCE_EVENT, resolve_candidate
from app.brain.version_gate import build_candidate, version_gate_status
from app.core.config import get_config
from app.core.db import get_session
from app.core.ontology import load_ontology
from app.gym.challenge import generate_pack
from app.gym.growth import finalize_session
from app.gym.pack import build_items
from app.gym.session import start_session, submit_results
from app.llm.base import CompletionResult, Usage
from app.llm.client import LLMClient
from app.main import app
from app.models.arena import RUN_TYPE_BRAIN, ArenaRun, KtibItem, KtibVersion
from app.models.brain import BrainNode, BrainVersion, ConfusionEdge, Exemplar, InferenceLog
from app.models.episodes import Episode, Evidence
from app.models.foundry import AtlasEntry, CanonicalScenario, FoundryWorkOrder
from app.models.governance import GovernanceEvent
from app.models.guards import promote_tier
from app.models.gym import ChallengePack, GymSession
from app.models.persona import PersonaCluster, PopulationPrior
from tests.arena_helpers import add_benchmark_episode
from tests.brain_helpers import FAST, _SyntheticScorer, _embed, _gold

CFG = get_config()
BUCKETS = ("synthetic", "weak_behavioral", "human_confirmed", "gold", "expert")

# KTIB 5문항: node 정답 4 + other 정답 1
KTIB_ROWS = [
    ("EP_K1", "node", "다음엔 뭘 해주면 좋을까"),
    ("EP_K2", "node", "이거 좀 더 확장해줘"),
    ("EP_K3", "node", "놀이를 더 이어가고 싶어"),
    ("EP_K4", "node", "여기서 뭘 더 붙이지"),
    ("EP_K5", "other", "다음 단계로 넘어가자"),
]


@pytest.fixture(autouse=True)
def _empty(db_session):
    for model in (ArenaRun, KtibItem, KtibVersion, InferenceLog, Evidence, Exemplar,
                  FoundryWorkOrder, GymSession, ChallengePack, Episode, CanonicalScenario,
                  AtlasEntry, ConfusionEdge, PopulationPrior, PersonaCluster,
                  BrainVersion, GovernanceEvent, BrainNode):
        db_session.execute(delete(model))
    db_session.flush()


def _intents() -> tuple[str, str]:
    xs = [i.intent_id for i in load_ontology().intents if i.domain]
    return xs[0], xs[1]


def _scripted_client(answers: dict[str, str]) -> LLMClient:
    """발화 → 예측 intent를 결정론적으로 강제하는 scorer.

    Arena 재현성의 전제(같은 입력 → 같은 점수)를 유지하면서, '뇌가 얼마나 맞히는가'를
    시나리오로 고정한다. answers에 없는 발화는 첫 후보를 고른다.
    """
    class _Scripted(_SyntheticScorer):
        name = "scripted"

        def complete(self, request) -> CompletionResult:
            ctx_start = request.prompt.rfind("```json")
            ctx = json.loads(
                request.prompt[ctx_start + 7 : request.prompt.find("```", ctx_start + 7)]
            )
            cands = ctx["candidate_intents"]
            target = answers.get(ctx["utterance"], cands[0] if cands else None)
            scores = [{"intent_id": c, "activation": 0.9 if c == target else 0.05,
                       "rationale": "s"} for c in cands]
            text = json.dumps({"scores": scores}, ensure_ascii=False)
            return CompletionResult(text=text, model=request.model, provider=self.name,
                                    usage=Usage(prompt_tokens=1, completion_tokens=1),
                                    cost_usd=0.0)

    return LLMClient(_Scripted(), FAST)


def _size(node_row) -> int:
    stats = node_row.evidence_stats or {}
    return sum(int(stats.get(b, 0) or 0) for b in BUCKETS)


def _run_gym_session(db, *, node, pack, mode, trainer):
    items = build_items(node_intent=node, mode=mode, config=CFG)
    gym = start_session(db, trainer_ref=trainer, mode=mode, pack=pack, items=items)
    submit_results(
        db, gym, [{"item_id": it["item_id"], "chosen_intent": node} for it in items], CFG
    )
    db.flush()
    return gym, items


def test_e2e_trace_0_to_9(db_session) -> None:
    node, other = _intents()
    gold_of = {"node": node, "other": other}

    # ── 준비: 노드 부트스트랩 + 학습 GOLD exemplar 2건 + KTIB 5문항 ──────────────────────
    bootstrap_nodes(db_session, approved_by="lab")
    _gold(db_session, "EP_TRAIN_N", node, "이 놀이 더 확장해줘")
    _gold(db_session, "EP_TRAIN_O", other, "다음 단계 알려줘")
    db_session.flush()
    select_exemplars(db_session, CFG, _embed())
    for epid, which, prompt in KTIB_ROWS:
        add_benchmark_episode(db_session, epid, gold_of[which], prompt=prompt)
    ktib = build_ktib(db_session, CFG)
    assert ktib.episode_count == 5
    # ★ 벤치마크가 exemplar로 새지 않았다 (§8-2) — 학습 exemplar는 2건 그대로
    assert db_session.scalar(select(func.count()).select_from(Exemplar)) == 2

    # ── [0] 관찰: 정기 Arena run이 현행 뇌(seed-v0)를 재고, 노드가 어둡다 ────────────────
    weak = _scripted_client({  # node 4문항 중 3개를 other로 오답 → node heldout 25%
        "다음엔 뭘 해주면 좋을까": other,
        "이거 좀 더 확장해줘": other,
        "놀이를 더 이어가고 싶어": other,
        "여기서 뭘 더 붙이지": node,
        "다음 단계로 넘어가자": other,
    })
    base_result = run_arena(db_session, weak, _embed(), CFG, model_version="seed-v0", ktib=ktib)
    reflect_arena_run(db_session, base_result.run, CFG, promoted=False)
    db_session.flush()

    node_row = db_session.scalar(select(BrainNode).where(BrainNode.intent_id == node))
    assert node_row.heldout_accuracy == 0.25          # 어두운 노드 (§6-7 [0])
    assert node_row.last_arena_run == base_result.run.run_id
    assert base_result.run.metrics["first_intent_accuracy"] == 0.4  # global 2/5
    dark_brightness = node_row.heldout_accuracy

    # [0] edge flicker: node→other 오답 3건 → confusion_rate 0.75, confirmed(§5-6)
    edge = db_session.scalar(
        select(ConfusionEdge).where(
            ConfusionEdge.from_true == node, ConfusionEdge.to_predicted == other
        )
    )
    assert edge is not None and edge.confusion_rate == 0.75
    assert edge.state == "confirmed" and edge.origin == "ARENA_MATRIX"
    dark_flicker = edge.confusion_rate

    # ── [1] 클릭: 진단 엔진 (§7-3) ─────────────────────────────────────────────────────
    aggregate_evidence_stats(db_session)
    db_session.flush()
    dg = diagnose_node(db_session, node, CFG)
    assert dg.gold_data.value == 1 and dg.gold_data.level == "LOW"   # GOLD_LOW (벤치마크 미포함)
    assert edge.confusion_rate >= CFG.growth.confusion_trigger       # CONFUSION_HIGH 전제

    # ── [2] 전략: 진단 → 강화 유형 → Challenge Pack (§6-1·§6-4) ────────────────────────
    gp = generate_pack(db_session, node_intent=node, trigger="observatory_click", config=CFG)
    db_session.flush()
    assert "C_CONFUSION" in gp.pack.strategy
    assert gp.pack.target_edges[0]["to_predicted"] == other
    # 계보: pack이 DB에 남는다
    pack_row = db_session.get(ChallengePack, gp.pack.pack_id)
    assert pack_row is not None and (pack_row.origin or {})["node"] == node

    # ── [3][4] 출제·상호작용: 트레이너 2인 세션 → HUMAN evidence ────────────────────────
    gym1, items = _run_gym_session(
        db_session, node=node, pack=gp.pack, mode="choose_right_meaning", trainer="TR_A"
    )
    fin1 = finalize_session(db_session, gym1, CFG)
    db_session.flush()
    assert fin1.episodes_aggregated == 0  # 1인 신호 — §3-6 축적 유지

    gym2, _ = _run_gym_session(
        db_session, node=node, pack=gp.pack, mode="choose_right_meaning", trainer="TR_B"
    )
    fin2 = finalize_session(db_session, gym2, CFG)
    db_session.flush()

    # 계보: 세션 2건 + evidence 2×items, 전부 TEACHER_TRAINER·비adversarial
    assert db_session.scalar(select(func.count()).select_from(GymSession)) == 2
    human_ev = db_session.scalars(
        select(Evidence).where(Evidence.evidence_type == "HUMAN_CONFIRMATION")
    ).all()
    assert len(human_ev) == 2 * len(items)
    assert all(e.actor_type == "TEACHER_TRAINER" and e.adversarial is False for e in human_ev)

    # ── [5] 집계: 2인 일치 → LABEL_CANDIDATE·SILVER, 이어서 사람 검수 → LABELED·GOLD ────
    assert fin2.episodes_aggregated == len(items)
    gym_eps = db_session.scalars(
        select(Episode).where(Episode.origin_channel == "GYM_HUMAN")
    ).all()
    assert all(e.label_state == "LABEL_CANDIDATE" and e.reliability_tier == "SILVER"
               for e in gym_eps)

    # ── [6] 즉시 반영: size↑ density↑ + pending 링. **brightness 불변** (원칙 8) ─────────
    db_session.refresh(node_row)
    assert _size(node_row) >= 2 * len(items)
    assert node_row.pending_evaluation is True            # 훈련됨·검증 대기
    assert node_row.heldout_accuracy == dark_brightness   # ★ 밝기는 그대로 어둡다
    assert node_row.last_arena_run == base_result.run.run_id

    # 사람 검수(§3-3) — 자동 클릭-투-트레인 루프 밖. 2인 검수 일치를 가정한다.
    for ep in gym_eps:
        advance_label_state(ep, "LABELED")
        promote_tier(ep, "GOLD")
        ep.human_review = {"reviewers": ["HR_1", "HR_2"], "agreed": True}
    db_session.flush()
    aggregate_evidence_stats(db_session)
    db_session.flush()
    db_session.refresh(node_row)
    assert node_row.heldout_accuracy == dark_brightness   # 검수도 밝기를 못 바꾼다

    # ── [7] 후보: Version Gate 충족 → candidate 빌드 (§6-6) ────────────────────────────
    expected_gold = 2 + len(items)  # 학습 GOLD 2 + 검수 통과 gym 에피소드
    cfg = CFG.model_copy(update={
        "version_gate": CFG.version_gate.model_copy(update={"min_new_gold": expected_gold})
    })
    status = version_gate_status(db_session, cfg)
    assert status.new_gold == expected_gold and status.condition_met is True
    assert status.base_version == "seed-v0"

    cand = build_candidate(db_session, cfg, trigger="e2e")
    db_session.flush()
    assert cand is not None and cand.decision == "candidate" and cand.base == "seed-v0"
    assert node in cand.delta["updated_nodes"]
    assert db_session.scalar(select(BrainNode).where(
        BrainNode.intent_id == node
    )).heldout_accuracy == dark_brightness  # 후보 빌드도 밝기 불변

    # ── [8] 시험: candidate를 KTIB로 재평가 (replay 4버전 기록) ─────────────────────────
    strong = _scripted_client({row[2]: gold_of[row[1]] for row in KTIB_ROWS})  # 전부 정답
    cand_result = run_arena(
        db_session, strong, _embed(), CFG, model_version=cand.version, ktib=ktib
    )
    db_session.flush()
    run = cand_result.run
    assert run.run_type == RUN_TYPE_BRAIN and run.model_version == "seed-v0-rc1"
    for axis in ("model_version", "ontology_version", "persona_state_version",
                 "extractor_versions", "ktib_version"):
        assert getattr(run, axis)                          # replay 무결성 4종 + ktib
    assert run.metrics["first_intent_accuracy"] == 1.0
    # 아직 밝기는 candidate의 것 — 뇌의 것이 아니다
    db_session.refresh(node_row)
    assert node_row.heldout_accuracy == dark_brightness

    # ── [9] 판정: promote → 밝기↑ · flicker↓ · pending 소등 · Resonance ─────────────────
    base_run = baseline_run(db_session, "seed-v0", ktib.ktib_version)
    assert base_run is not None and base_run.run_id == base_result.run.run_id
    outcome = build_outcome(run, base_run, cfg)
    assert outcome.global_delta == pytest.approx(60.0)  # 0.4 → 1.0 = +60pp
    assert outcome.region_regressions == [] and outcome.critical_worse == []

    decision = resolve_candidate(db_session, cand, outcome, cfg)
    reflected = reflect_arena_run(db_session, run, cfg, promoted=True)
    db_session.flush()

    assert decision.decision == "promote" and decision.version == "v1"
    assert reflected.resonance is True
    assert reflected.nodes_brightened == 0  # promote 경로가 이미 썼다 — 이중 쓰기 없음

    db_session.refresh(node_row)
    assert node_row.heldout_accuracy == 1.0                # 0.25 → 1.00 (§6-7 [9])
    assert node_row.heldout_accuracy > dark_brightness
    assert node_row.last_arena_run == run.run_id
    assert node_row.pending_evaluation is False            # 링 소등

    db_session.refresh(edge)
    assert edge.confusion_rate == 0.0 < dark_flicker       # flicker 감소(§7-5)
    assert edge.state == "confirmed"                       # 상태는 단조

    # Full Brain Resonance 1회 (§6-6 버전 업의 시각 서명)
    events = db_session.scalars(
        select(GovernanceEvent).where(GovernanceEvent.event_type == RESONANCE_EVENT)
    ).all()
    assert len(events) == 1
    assert events[0].payload["version"] == "v1" and events[0].payload["run_id"] == run.run_id

    # ── 계보: 각 단계의 산출물이 DB에 남았다 ────────────────────────────────────────────
    assert db_session.scalar(select(func.count()).select_from(KtibVersion)) == 1
    assert db_session.scalar(select(func.count()).select_from(ArenaRun)) == 2      # base + cand
    assert db_session.scalar(select(func.count()).select_from(ChallengePack)) == 1
    assert db_session.scalar(select(func.count()).select_from(GymSession)) == 2
    assert db_session.scalar(select(func.count()).select_from(BrainVersion)) == 1  # candidate→v1
    assert cand.arena_result["run_id"] == run.run_id       # 승격 근거 run으로 되짚어진다
    assert db_session.scalar(select(func.count()).select_from(InferenceLog)) == 10  # 5문항 × 2 run


def test_e2e_reject_branch_preserves_everything(db_session) -> None:
    """§6-7 [9] FAIL 경로: reject → evidence 전량 보존, 밝기·링 불변, 원인 리포트, Resonance 없음."""
    node, other = _intents()
    gold_of = {"node": node, "other": other}

    bootstrap_nodes(db_session, approved_by="lab")
    _gold(db_session, "EP_TRAIN_N", node, "이 놀이 더 확장해줘")
    _gold(db_session, "EP_TRAIN_O", other, "다음 단계 알려줘")
    db_session.flush()
    select_exemplars(db_session, CFG, _embed())
    for epid, which, prompt in KTIB_ROWS:
        add_benchmark_episode(db_session, epid, gold_of[which], prompt=prompt)
    ktib = build_ktib(db_session, CFG)

    strong = _scripted_client({row[2]: gold_of[row[1]] for row in KTIB_ROWS})
    base = run_arena(db_session, strong, _embed(), CFG, model_version="seed-v0", ktib=ktib)
    reflect_arena_run(db_session, base.run, CFG, promoted=False)
    db_session.flush()
    node_row = db_session.scalar(select(BrainNode).where(BrainNode.intent_id == node))
    node_row.pending_evaluation = True  # 훈련됨·검증 대기
    db_session.flush()
    assert node_row.heldout_accuracy == 1.0

    cfg = CFG.model_copy(update={
        "version_gate": CFG.version_gate.model_copy(update={"min_new_gold": 2})
    })
    cand = build_candidate(db_session, cfg, trigger="e2e-reject")
    db_session.flush()

    weak = _scripted_client({row[2]: other for row in KTIB_ROWS})  # 후보가 더 나빠졌다
    cand_run = run_arena(db_session, weak, _embed(), CFG, model_version=cand.version, ktib=ktib)
    db_session.flush()
    ev_before = db_session.scalar(select(func.count()).select_from(Evidence))

    outcome = build_outcome(cand_run.run, base.run, cfg)
    assert outcome.global_delta < 0
    decision = resolve_candidate(db_session, cand, outcome, cfg)
    reflect_arena_run(db_session, cand_run.run, cfg, promoted=False)
    db_session.flush()

    assert decision.decision == "reject" and "global_not_up" in decision.reasons
    assert decision.nodes_brightened == 0
    db_session.refresh(node_row)
    assert node_row.heldout_accuracy == 1.0        # 밝기 불변 — 후보 숫자는 폐기됐다
    assert node_row.pending_evaluation is True     # 링 유지(아직 검증 대기)
    assert node_row.last_arena_run == base.run.run_id
    assert db_session.scalar(select(func.count()).select_from(Evidence)) == ev_before  # 전량 보존
    assert cand.arena_result["report"]["reasons"] == decision.reasons
    assert db_session.scalar(select(func.count()).select_from(GovernanceEvent).where(
        GovernanceEvent.event_type == RESONANCE_EVENT
    )) == 0                                         # Resonance 없음


@pytest.fixture()
def api(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        yield client
    app.dependency_overrides.clear()


def test_observatory_reflects_promoted_brain(api, db_session) -> None:
    """[9] 이후 3D Brain이 새 버전·밝기·Stage를 그대로 읽는다 (§7-1·§7-6)."""
    node, other = _intents()
    gold_of = {"node": node, "other": other}
    bootstrap_nodes(db_session, approved_by="lab")
    # 두 intent 모두 exemplar가 있어야 retrieval 후보에 오른다 — 후보 밖 intent는 예측될 수 없다
    _gold(db_session, "EP_TRAIN_N", node, "이 놀이 더 확장해줘")
    _gold(db_session, "EP_TRAIN_O", other, "다음 단계 알려줘")
    db_session.flush()
    select_exemplars(db_session, CFG, _embed())
    for epid, which, prompt in KTIB_ROWS:
        add_benchmark_episode(db_session, epid, gold_of[which], prompt=prompt)
    ktib = build_ktib(db_session, CFG)

    strong = _scripted_client({row[2]: gold_of[row[1]] for row in KTIB_ROWS})
    base = run_arena(db_session, strong, _embed(), CFG, model_version="seed-v0", ktib=ktib)
    reflect_arena_run(db_session, base.run, CFG, promoted=False)
    db_session.flush()

    body = api.get("/v1/observatory/brain").json()
    assert body["ktib_global"] == 1.0
    assert body["brain_stage"] == 5                     # global ≥ 목표 → Whole Brain Resonance
    assert body["brain_stage_name"] == "Whole Brain Resonance"
    n = next(x for x in body["nodes"] if x["intent_id"] == node)
    assert n["heldout_accuracy"] == 1.0
    assert n["last_arena_run"] == base.run.run_id
