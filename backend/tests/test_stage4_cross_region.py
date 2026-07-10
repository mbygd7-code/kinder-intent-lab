"""Stage 4 = Semantic Cross-Region Flow AC (§7-6, 2026-07-10 확정).

- 인접 = `state='confirmed'`인 **cross-region** 혼동 edge (공간 인접 그래프를 발명하지 않는다)
- ★ 인접은 rate가 아니라 state로 판정한다 → 혼동이 0까지 줄어 목표를 달성해도 인접이 사라지지 않는다
  (rate로 정의하면 Stage 4는 도달하는 순간 스스로를 지운다)
- 추세 = 동일 ktib_version 최근 W개 brain run에서, **윈도 시작 run에 스냅샷된** 주요 다리의
  평균 confusion_rate가 min_drop 이상 순감소
- 미측정은 미충족이 아니다: run이 W개 미만이면 Stage 4 미방출
- region 단위는 여전히 0~3만 반환한다
"""
import pytest
from sqlalchemy import delete

from app.arena.stages import (
    STAGE_NAMES,
    RegionStage,
    adjacent_pairs,
    brain_stage,
    cross_region_flow,
    rate_in_run,
    region_stage,
    stage4_inputs,
)
from app.core.config import get_config
from app.core.ontology import load_ontology
from app.models.arena import RUN_TYPE_BRAIN, ArenaRun, KtibItem, KtibVersion
from app.models.brain import ConfusionEdge

CFG = get_config()


def _by_domain(domain: str, n: int = 2) -> list[str]:
    return [i.intent_id for i in load_ontology().intents if i.domain == domain][:n]


PLAY_A, PLAY_B = _by_domain("PLAY")
DOC_A, _DOC_B = _by_domain("DOCUMENT")
VIS_A, _VIS_B = _by_domain("VISUAL")


def _edge(from_true, to_predicted, state="confirmed") -> ConfusionEdge:
    return ConfusionEdge(
        edge_id=f"CE_{from_true}_{to_predicted}", from_true=from_true,
        to_predicted=to_predicted, confusion_rate=0.3, state=state, origin="ARENA_MATRIX",
    )


def _run(run_id, matrix, measured) -> ArenaRun:
    """confusion_matrix + by_node(측정된 정답 intent)만 갖춘 최소 run 객체(비영속)."""
    return ArenaRun(
        run_id=run_id, model_version="seed-v0", ontology_version="onto-1.0",
        persona_state_version="none", extractor_versions={}, ktib_version="ktib-1",
        run_type=RUN_TYPE_BRAIN,
        metrics={"by_node": {i: {"n": 1, "accuracy": 0.0, "ece": None, "correct": 0}
                             for i in measured}},
        confusion_matrix=matrix,
    )


def _row(from_true, to_predicted, rate) -> dict:
    return {"from_true": from_true, "to_predicted": to_predicted, "count": 3,
            "confusion_rate": rate, "confirmed": True}


def _online(*regions) -> dict[str, RegionStage]:
    out = {}
    for r in ("PLAY", "DOCUMENT", "VISUAL"):
        rel = 0.9 if r in regions else 0.1
        out[r] = RegionStage(r, 3 if r in regions else 1, "x", rel, 5, 5)
    return out


def _cfg(**stage_over):
    return CFG.model_copy(update={"stages": CFG.stages.model_copy(update=stage_over)})


# --- 인접 (adjacency) ---


def test_adjacency_needs_confirmed_cross_region_edge() -> None:
    edges = [_edge(PLAY_A, DOC_A)]
    assert adjacent_pairs(edges) == {frozenset(("PLAY", "DOCUMENT"))}


def test_same_region_confusion_is_not_flow() -> None:
    """region 내부 혼동은 '흐름'이 아니다."""
    assert adjacent_pairs([_edge(PLAY_A, PLAY_B)]) == set()


@pytest.mark.parametrize("state", ["hypothesized", "observed"])
def test_unconfirmed_edge_builds_no_bridge(state) -> None:
    """순간 잡음(미확정 edge)이 인접을 지어내지 못한다."""
    assert adjacent_pairs([_edge(PLAY_A, DOC_A, state=state)]) == set()


def test_adjacency_survives_rate_dropping_to_zero() -> None:
    """★ 인접은 state로 판정한다 — 혼동이 0까지 줄어도 다리는 남는다(자기소멸 방지)."""
    edge = _edge(PLAY_A, DOC_A)
    edge.confusion_rate = 0.0
    assert adjacent_pairs([edge]) == {frozenset(("PLAY", "DOCUMENT"))}


def test_unknown_intent_region_is_dropped_not_guessed() -> None:
    assert adjacent_pairs([_edge("UNKNOWN", DOC_A)]) == set()


# --- 추세 (trend) ---


def _window(start_rate, end_rate, n=3):
    runs = [_run("AR_0", [_row(PLAY_A, DOC_A, start_rate)], [PLAY_A])]
    runs += [_run(f"AR_{i}", [_row(PLAY_A, DOC_A, start_rate)], [PLAY_A])
             for i in range(1, n - 1)]
    runs.append(_run(f"AR_{n - 1}", [_row(PLAY_A, DOC_A, end_rate)], [PLAY_A]))
    return runs


def test_flow_when_major_bridge_rate_drops(db_session) -> None:
    """★ 두 인접 region이 Online ∧ 주요 다리 평균 rate가 min_drop 이상 순감소 → Stage 4."""
    edges = [_edge(PLAY_A, DOC_A)]
    runs = _window(0.40, 0.10)
    assert cross_region_flow(_online("PLAY", "DOCUMENT"), edges, runs, CFG) is True


def test_no_flow_when_rate_flat_or_rising() -> None:
    edges = [_edge(PLAY_A, DOC_A)]
    assert cross_region_flow(_online("PLAY", "DOCUMENT"), edges, _window(0.30, 0.30), CFG) is False
    assert cross_region_flow(_online("PLAY", "DOCUMENT"), edges, _window(0.30, 0.50), CFG) is False


def test_no_flow_when_a_region_is_not_online() -> None:
    """'인접 region ≥ 70%' — 한쪽이라도 미달(미측정 None 포함)이면 흐름이 아니다."""
    edges = [_edge(PLAY_A, DOC_A)]
    runs = _window(0.40, 0.10)
    assert cross_region_flow(_online("PLAY"), edges, runs, CFG) is False
    assert cross_region_flow(_online(), edges, runs, CFG) is False


def test_no_flow_when_window_incomplete() -> None:
    """★ 미측정은 미충족이 아니다 — run이 W개 미만이면 추세는 NULL이고 Stage 4를 방출하지 않는다."""
    edges = [_edge(PLAY_A, DOC_A)]
    short = _window(0.40, 0.10)[:2]
    assert CFG.stages.cross_region_trend_window == 3
    assert cross_region_flow(_online("PLAY", "DOCUMENT"), edges, short, CFG) is False


def test_no_flow_without_major_bridge_at_window_start() -> None:
    """윈도 시작에 '주요' 다리(rate ≥ major_edge_min)가 없으면 감소를 주장할 대상이 없다."""
    edges = [_edge(PLAY_A, DOC_A)]
    runs = _window(0.05, 0.0)  # 시작 rate < cross_region_major_edge_min(0.15)
    assert cross_region_flow(_online("PLAY", "DOCUMENT"), edges, runs, CFG) is False


def test_major_bridge_set_snapshotted_at_window_start() -> None:
    """★ 주요 다리는 시작 run에서 스냅샷된다 — 이후 rate가 떨어져도 집합이 바뀌지 않는다.

    (rate로 매번 다시 고르면, 개선된 다리가 집합에서 빠져 '감소'가 관측되지 않는다.)
    """
    edges = [_edge(PLAY_A, DOC_A)]
    runs = _window(0.40, 0.0)  # 최종 rate 0.0 — 재선택 방식이면 표본이 사라진다
    assert cross_region_flow(_online("PLAY", "DOCUMENT"), edges, runs, CFG) is True


def test_unmeasured_gold_not_treated_as_zero() -> None:
    """마지막 run에서 정답 A가 아예 측정되지 않았으면 0으로 채워 '개선'을 주장하지 않는다."""
    edges = [_edge(PLAY_A, DOC_A)]
    runs = _window(0.40, 0.10)
    runs[-1] = _run("AR_last", [], measured=[])  # A 미측정 + pair 부재
    assert cross_region_flow(_online("PLAY", "DOCUMENT"), edges, runs, CFG) is False


def test_rate_in_run_is_directional() -> None:
    run = _run("AR", [_row(PLAY_A, DOC_A, 0.31)], [PLAY_A])
    assert rate_in_run(run, PLAY_A, DOC_A) == 0.31
    assert rate_in_run(run, DOC_A, PLAY_A) is None  # 반대 방향은 별개


# --- brain_stage 삽입 ---


def test_region_stage_never_returns_4() -> None:
    """region 단위는 0~3만. Stage 4는 region *쌍* 사이의 흐름이라 brain_stage 소관이다."""
    assert all(region_stage(r, 10, m, CFG) != 4
               for r in (None, 0.0, 0.5, 0.7, 1.0) for m in (0, 1, 5, 10))


def test_stage5_beats_stage4() -> None:
    """highest-satisfied-wins — global이 목표를 넘으면 5다."""
    edges = [_edge(PLAY_A, DOC_A)]
    runs = _window(0.40, 0.10)
    target = CFG.arena.first_intent_accuracy_target
    assert brain_stage(target, _online("PLAY", "DOCUMENT"), CFG,
                       edges=edges, run_history=runs) == 5


def test_stage4_inserted_between_region_max_and_5() -> None:
    edges = [_edge(PLAY_A, DOC_A)]
    runs = _window(0.40, 0.10)
    regions = _online("PLAY", "DOCUMENT")
    assert brain_stage(0.5, regions, CFG, edges=edges, run_history=runs) == 4
    assert STAGE_NAMES[4] == "Semantic Cross-Region Flow"
    # 근거를 빼면 region 최고 단계로 떨어진다 — 4를 지어내지 않는다
    assert brain_stage(0.5, regions, CFG) == 3


def test_lightweight_caller_skips_stage4() -> None:
    """edges/run_history 없는 호출자는 Stage 4 평가를 생략한다(3-or-5 폴백)."""
    assert brain_stage(0.1, _online("PLAY"), CFG) == 3
    assert brain_stage(None, _online(), CFG) == 1


# --- stage4_inputs: 신·구 벤치마크를 섞지 않는다 (§8-2) ---


def test_stage4_inputs_scopes_runs_to_latest_ktib_version(db_session) -> None:
    for model in (ArenaRun, KtibItem, KtibVersion, ConfusionEdge):
        db_session.execute(delete(model))
    db_session.flush()
    for seq, name in ((1, "ktib-1"), (2, "ktib-2")):
        db_session.add(KtibVersion(ktib_version=name, seq=seq, extractor_versions={},
                                   episode_count=1, content_hash=f"h{seq}"))
    db_session.flush()
    db_session.add(_edge(PLAY_A, DOC_A))
    for i, ktib in enumerate(["ktib-1", "ktib-1", "ktib-2"]):
        run = _run(f"AR_{i}", [], [PLAY_A])
        run.ktib_version = ktib
        db_session.add(run)
        db_session.flush()  # created_at 순서 고정

    edges, history = stage4_inputs(db_session, CFG)
    assert len(edges) == 1
    assert {r.ktib_version for r in history} == {"ktib-2"}  # 최신 ktib만 — 축을 섞지 않는다
    assert len(history) == 1  # W(3)에 못 미침 → Stage 4 미방출
