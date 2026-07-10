"""T5.3 AC (§8-2·§5-6): Arena 러너.

- 산출: 노드/region/global heldout accuracy · 방향성 confusion matrix · calibration(ECE)
  · replay 4버전(model / ontology / persona_state / extractor)
- AC1: 동일 입력·동일 4버전으로 재실행 시 결과 재현
- AC2: confusion matrix가 confusion_edges(state=confirmed)를 갱신
- 절대 규칙 3·5: 러너는 밝기를 쓰지 않고, gold intent를 추론 입력에 넣지 않는다
"""
import pytest
from sqlalchemy import delete, select

from app.arena.ktib import EmptyKtib
from app.arena.runner import (
    ARENA_MODE,
    ARENA_TEACHER_REF,
    KtibAxisMismatch,
    apply_confusion_edges,
    baseline_run,
    build_outcome,
    core_signals_from_item,
    run_arena,
)
from app.brain.backfill import bootstrap_nodes, select_exemplars
from app.brain.promote import evaluate_promotion
from app.brain.version_gate import SEED_VERSION
from app.core.config import get_config
from app.core.ontology import load_ontology
from app.models.arena import NO_PERSONA_STATE, RUN_TYPE_BRAIN, ArenaRun, KtibItem, KtibVersion
from app.models.brain import BrainNode, BrainVersion, ConfusionEdge, Exemplar, InferenceLog
from app.models.episodes import Episode, Evidence
from app.models.foundry import AtlasEntry, CanonicalScenario
from tests.arena_helpers import domain_intents, seed_ktib
from tests.brain_helpers import _client as brain_client
from tests.brain_helpers import _embed, _gold, _SyntheticScorer

CFG = get_config()


@pytest.fixture(autouse=True)
def _empty(db_session):
    for model in (ArenaRun, KtibItem, KtibVersion, InferenceLog, ConfusionEdge, Exemplar,
                  Evidence, Episode, CanonicalScenario, AtlasEntry, BrainVersion, BrainNode):
        db_session.execute(delete(model))
    db_session.flush()


def _seed_brain(db, pairs):
    """노드 부트스트랩 + TRAIN GOLD exemplar 적재 (retrieval이 후보를 낼 수 있게)."""
    bootstrap_nodes(db, approved_by="lab")
    for k, (intent, prompt) in enumerate(pairs):
        _gold(db, f"EP_TRAIN_{k}", intent, prompt)
    db.flush()
    select_exemplars(db, CFG, _embed())
    db.flush()


def _fixture_brain_and_ktib(db):
    """훈련 exemplar 2개 + 벤치마크 4건(gold a×3, b×1).

    a가 3건인 이유: confusion_confirm_min(=config)만큼 오답이 쌓여야 edge가 confirmed로 간다.
    """
    a, b = domain_intents(2)
    assert CFG.arena.confusion_confirm_min <= 3  # 이 픽스처의 전제 — 바뀌면 아이템 수도 늘려야 함
    region_of = {i.intent_id: i.domain for i in load_ontology().intents}
    assert region_of[a] == region_of[b]  # 전제: 같은 region (region 회귀 기대값이 여기 의존)
    _seed_brain(db, [(a, "이 사진 자연스럽게 해줘"), (b, "이 문장 자연스럽게 해줘")])
    ktib = seed_ktib(db, [
        ("EP_K1", a, "다음엔 뭘 해주면 좋을까"),
        ("EP_K2", a, "이거 좀 더 확장해줘"),
        ("EP_K3", a, "놀이를 더 이어가고 싶어"),
        ("EP_K4", b, "이 문장 자연스럽게"),
    ])
    return ktib, a, b


def _forced_client(target: str):
    """모든 후보 중 target만 높게 채점 → 예측이 전부 target으로 쏠린다(결정론적 오답/정답 강제).

    합성 scorer의 순위는 mock 임베딩 근접도에 좌우되므로, confusion 시나리오는 이렇게 고정한다.
    """
    import json

    from app.llm.base import CompletionResult, Usage
    from app.llm.client import LLMClient
    from tests.brain_helpers import FAST

    class _Forced(_SyntheticScorer):
        name = "forced"

        def complete(self, request) -> CompletionResult:
            cands = self._candidates(request.prompt)
            scores = [{"intent_id": c, "activation": 0.99 if c == target else 0.01,
                       "rationale": "f"} for c in cands]
            text = json.dumps({"scores": scores}, ensure_ascii=False)
            return CompletionResult(text=text, model=request.model, provider=self.name,
                                    usage=Usage(prompt_tokens=1, completion_tokens=1),
                                    cost_usd=0.0)

    return LLMClient(_Forced(), FAST)


def _run(db, *, model_version="seed-v0", client=None):
    return run_arena(
        db, client or brain_client(), _embed(), CFG, model_version=model_version
    )


# --- 산출물 · replay 4버전 ---


def test_run_records_replay_four_versions_and_metrics(db_session) -> None:
    ktib, a, b = _fixture_brain_and_ktib(db_session)
    result = _run(db_session)
    run = result.run

    assert run.run_type == RUN_TYPE_BRAIN
    assert run.model_version == SEED_VERSION
    assert run.ontology_version                       # ② ontology
    assert run.persona_state_version == NO_PERSONA_STATE  # ③ persona (아직 발급 없음 — 명시)
    assert run.extractor_versions == ktib.extractor_versions  # ④ extractor (KTIB 동결 지문)
    assert run.ktib_version == ktib.ktib_version

    m = run.metrics
    assert m["item_count"] == 4
    assert m["first_intent_accuracy"] is not None
    assert set(m["by_node"]) == {a, b}                # 측정된 노드만 (나머지는 Dormant)
    assert m["by_region"]                             # region 분해 존재
    assert m["ece"] is not None                       # calibration


def test_run_freezes_gate_metrics_into_arena_run(db_session) -> None:
    """★ §10-2 4지표는 run 시점에 계산돼 metrics에 동결된다 — 게이트는 저장값만 읽는다."""
    _fixture_brain_and_ktib(db_session)
    m = _run(db_session).run.metrics

    assert m["risk_model_version"] == "rm-1.0"        # 어느 critical 집합으로 채점됐는지 귀속
    assert "recovery" in m and "critical" in m and "persona" in m
    # decision 분포가 남는다 — abstain_count(=후보 0)만으로는 decision abstain이 안 보인다
    assert set(m["decisions"]) == {"suggest", "clarify", "abstain"}
    assert sum(m["decisions"].values()) == m["item_count"]
    # 이 픽스처의 intent(play_*)는 critical이 아니다 → 안전 지표는 측정 대상 없음(null, 0% 아님)
    crit = m["critical"]
    assert crit["critical_set_size"] == len(CFG.arena.critical_intents) == 7
    assert crit["o_count"] == 0
    assert crit["cwar_fire"] is None and crit["cwar_miss"] is None and crit["ccc"] is None
    assert m["persona"] is None                       # persona_cluster 0개


def test_decision_postprocess_adds_no_inference_logs(db_session) -> None:
    """decide()·persona 재정렬은 순수 후처리다 — 추가 LLM 호출도, 로그 행도 만들지 않는다(§5-5)."""
    _fixture_brain_and_ktib(db_session)
    before = len(db_session.scalars(select(InferenceLog)).all())
    _run(db_session)
    after = len(db_session.scalars(select(InferenceLog)).all())
    assert after - before == 4                        # KTIB 아이템 수만큼만 (재랭킹은 0)


def test_predictions_carry_decision_and_top2(db_session) -> None:
    """Recovery·CWAR의 재료 — 모든 예측이 decision과 clarify 후보를 들고 있다."""
    _fixture_brain_and_ktib(db_session)
    preds = _run(db_session).predictions
    assert all(p.decision in {"suggest", "clarify", "abstain"} for p in preds)
    assert all(p.clarify_top2 is not None for p in preds)


def test_gold_intent_never_enters_inference_input(db_session) -> None:
    """★ 절대 규칙 5: 정답·에피소드 id가 Core 신호에 새지 않는다."""
    ktib, a, b = _fixture_brain_and_ktib(db_session)
    item = db_session.scalars(
        select(KtibItem).where(KtibItem.episode_id == "EP_K1")
    ).one()

    core = core_signals_from_item(item)
    assert core.prompt_text == item.teacher_prompt
    assert core.teacher_ref == ARENA_TEACHER_REF      # 개인 prior로 조건화되지 않는다
    blob = repr(core)
    assert item.gold_intent not in blob and item.episode_id not in blob


def test_inference_logs_recorded_with_arena_mode(db_session) -> None:
    """전건 로그는 남되 mode='arena'로 구분된다 (gym/live 로그와 섞이지 않는다)."""
    _fixture_brain_and_ktib(db_session)
    _run(db_session)
    logs = db_session.scalars(select(InferenceLog)).all()
    assert len(logs) == 4
    assert {log.mode for log in logs} == {ARENA_MODE}


def test_runner_never_writes_brightness(db_session) -> None:
    """★ 절대 규칙 3: 러너는 점수를 만들 뿐 밝기를 켜지 않는다 — 그건 promote의 일이다(§6-7 [9])."""
    _fixture_brain_and_ktib(db_session)
    _run(db_session)
    nodes = db_session.scalars(select(BrainNode)).all()
    assert all(n.heldout_accuracy is None and n.last_arena_run is None for n in nodes)
    assert all(n.calibration_ece is None for n in nodes)


def test_empty_ktib_raises(db_session) -> None:
    bootstrap_nodes(db_session, approved_by="lab")
    db_session.flush()
    with pytest.raises(EmptyKtib):
        _run(db_session)


# --- AC1: 재현성 ---


def test_same_input_same_versions_reproduces_result(db_session) -> None:
    """★ AC: 동일 입력·동일 4버전으로 재실행 → 동일 metrics·confusion_matrix."""
    _fixture_brain_and_ktib(db_session)
    first = _run(db_session)
    second = _run(db_session)

    assert first.run.run_id != second.run.run_id      # 다른 run 기록
    assert first.run.metrics == second.run.metrics    # 같은 점수
    assert first.run.confusion_matrix == second.run.confusion_matrix
    for axis in ("model_version", "ontology_version", "persona_state_version",
                 "extractor_versions", "ktib_version"):
        assert getattr(first.run, axis) == getattr(second.run, axis)


def test_predictions_order_is_deterministic(db_session) -> None:
    """아이템 순회는 episode_id 오름차순 — 재현성의 전제."""
    _fixture_brain_and_ktib(db_session)
    result = _run(db_session)
    assert [p.episode_id for p in result.predictions] == ["EP_K1", "EP_K2", "EP_K3", "EP_K4"]


# --- AC2: confusion matrix → confusion_edges(state=confirmed) ---


def test_confusion_matrix_confirms_edges(db_session) -> None:
    """★ AC: count ≥ confusion_confirm_min 방향성 pair → state='confirmed', origin=ARENA_MATRIX."""
    ktib, a, b = _fixture_brain_and_ktib(db_session)
    result = _run(db_session, client=_forced_client(b))  # 전부 b로 예측 → gold a 3건이 오답

    matrix = result.run.confusion_matrix
    row = next(r for r in matrix if r["from_true"] == a and r["to_predicted"] == b)
    assert row["count"] == 3 and row["confusion_rate"] == 1.0
    assert row["confirmed"] is True  # 3 ≥ config.arena.confusion_confirm_min

    assert apply_confusion_edges(db_session, result.run) >= 1
    edge = db_session.scalar(
        select(ConfusionEdge).where(
            ConfusionEdge.from_true == a, ConfusionEdge.to_predicted == b
        )
    )
    assert edge is not None
    assert edge.confusion_rate == 1.0        # 정답 a 3건 전부 b로 예측
    assert edge.state == "confirmed"         # §5-6 마지막 단계
    assert edge.origin == "ARENA_MATRIX"
    assert result.run.run_id in edge.evidence_runs
    # 역방향은 만들어지지 않는다 (b는 1건이고 정답이었다) — 방향성 보존
    assert db_session.scalar(
        select(ConfusionEdge).where(
            ConfusionEdge.from_true == b, ConfusionEdge.to_predicted == a
        )
    ) is None


def test_below_threshold_pair_updates_rate_but_not_state(db_session) -> None:
    """임계 미달 pair는 rate만 갱신하고 state를 올리지 않는다 (§5-6 상태 기계는 단조)."""
    ktib, a, b = _fixture_brain_and_ktib(db_session)
    result = _run(db_session, client=_forced_client(b))
    # 임계 미달 상황 모사: 이 run의 matrix에서 confirmed 플래그만 내린다
    result.run.confusion_matrix = [{**r, "confirmed": False} for r in result.run.confusion_matrix]
    db_session.flush()

    apply_confusion_edges(db_session, result.run)
    edge = db_session.scalar(
        select(ConfusionEdge).where(
            ConfusionEdge.from_true == a, ConfusionEdge.to_predicted == b
        )
    )
    assert edge.confusion_rate == 1.0     # rate(=flicker)는 갱신
    assert edge.state == "hypothesized"   # state는 승격되지 않음


def test_existing_confirmed_edge_not_downgraded(db_session) -> None:
    """이미 confirmed인 edge는 rate가 0이 돼도 state를 되돌리지 않는다 — 상태는 단조."""
    ktib, a, b = _fixture_brain_and_ktib(db_session)
    db_session.add(ConfusionEdge(
        edge_id="CE_pre", from_true=a, to_predicted=b, confusion_rate=0.4,
        state="confirmed", origin="GYM_CORRECTION", evidence_runs=[],
    ))
    db_session.flush()

    result = _run(db_session, client=_forced_client(a))  # 전부 a로 예측 → a→b 혼동 0건
    apply_confusion_edges(db_session, result.run)
    edge = db_session.scalar(select(ConfusionEdge).where(ConfusionEdge.edge_id == "CE_pre"))
    assert edge.state == "confirmed"    # 단조 — 되돌리지 않는다
    assert edge.confusion_rate == 0.0   # 혼동이 사라짐 → flicker 소등(§7-5)


def test_unmeasured_true_intent_edge_untouched(db_session) -> None:
    """이번 run에서 정답 A가 측정되지 않았으면 그 edge는 건드리지 않는다 (미측정 ≠ 0)."""
    ktib, a, b = _fixture_brain_and_ktib(db_session)
    ghost = domain_intents(4)[3]
    db_session.add(ConfusionEdge(
        edge_id="CE_ghost", from_true=ghost, to_predicted=a, confusion_rate=0.7,
        state="observed", origin="SKEPTIC", evidence_runs=[],
    ))
    db_session.flush()

    result = _run(db_session)
    apply_confusion_edges(db_session, result.run)
    edge = db_session.scalar(select(ConfusionEdge).where(ConfusionEdge.edge_id == "CE_ghost"))
    assert edge.confusion_rate == 0.7      # 그대로
    assert edge.state == "observed"
    assert edge.evidence_runs == []


# --- promote 판정 입력 (§6-6) ---


def test_build_outcome_without_baseline_blocks_promote(db_session) -> None:
    """기준 run이 없으면 상승을 지어내지 않는다 — global_delta=0 → promote 차단."""
    _fixture_brain_and_ktib(db_session)
    result = _run(db_session)
    outcome = build_outcome(result.run, None, CFG)
    assert outcome.global_delta == 0.0
    assert outcome.node_heldout  # 밝기 원천은 실려 있다
    assert evaluate_promotion(outcome, CFG).promote is False


def test_build_outcome_computes_delta_and_regressions(db_session) -> None:
    """global_delta(pp) + region 회귀 목록을 기준 run과 비교해 만든다."""
    ktib, a, b = _fixture_brain_and_ktib(db_session)
    base = _run(db_session, client=_forced_client(b)).run   # 1/4 정답
    cur = _run(db_session, client=_forced_client(a)).run    # 3/4 정답

    outcome = build_outcome(cur, base, CFG)
    assert base.metrics["first_intent_accuracy"] == 0.25
    assert cur.metrics["first_intent_accuracy"] == 0.75
    assert outcome.global_delta == pytest.approx(50.0, abs=1e-3)  # pp
    assert outcome.region_regressions == []
    assert outcome.critical_worse == []  # config.arena.critical_intents 비어 있음
    assert outcome.node_heldout[a] == 1.0 and outcome.node_heldout[b] == 0.0


def test_build_outcome_detects_region_regression(db_session) -> None:
    """region 정확도가 기준보다 떨어지면 회귀로 잡힌다 (promote 차단 조건, §6-6)."""
    ktib, a, b = _fixture_brain_and_ktib(db_session)
    base = _run(db_session, client=_forced_client(a)).run    # a-region 100%
    cur = _run(db_session, client=_forced_client(b)).run     # a-region 0%

    outcome = build_outcome(cur, base, CFG)
    region_of = {i.intent_id: i.domain for i in load_ontology().intents}
    assert region_of[a] in outcome.region_regressions

    decision = evaluate_promotion(outcome, CFG)
    assert decision.promote is False and "region_regression" in decision.reasons


def test_baseline_run_lookup_for_seed(db_session) -> None:
    """seed 상태의 기준 run = model_version='seed-v0'인 최신 brain run (같은 KTIB)."""
    ktib, _a, _b = _fixture_brain_and_ktib(db_session)
    run = _run(db_session, model_version=SEED_VERSION).run
    found = baseline_run(db_session, SEED_VERSION, ktib.ktib_version)
    assert found is not None and found.run_id == run.run_id


def test_baseline_run_rejects_cross_ktib_comparison(db_session) -> None:
    """★ §8-2: 다른 ktib_version에서 잰 기준 점수와 같은 축에 그리지 않는다."""
    ktib, a, _b = _fixture_brain_and_ktib(db_session)
    old_run = _run(db_session).run
    db_session.add(BrainVersion(
        version="v1", base=SEED_VERSION, trigger="t", delta={},
        arena_result={"run_id": old_run.run_id}, decision="promote",
    ))
    db_session.flush()

    with pytest.raises(KtibAxisMismatch):
        baseline_run(db_session, "v1", "ktib-999")
