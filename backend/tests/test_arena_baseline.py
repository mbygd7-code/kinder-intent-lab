"""T5.2 AC (§8-2 베이스라인 규칙): zero-shot 베이스라인 러너 + 리포트.

- AC: 베이스라인 리포트에 **노드/도메인별 분해** 포함
- run_type='zero_shot_baseline' — 3D 밝기 원천(brain run)과 물리적으로 분리
- zero-shot은 exemplar·prior를 쓰지 않는다 (프롬프트 입력에 훈련 산출물·정답이 없다)
- 목표 수치를 여기서 확정하지 않는다 — 제안서만 생성
"""
import json

import pytest
from sqlalchemy import delete, select

from app.arena.baseline import baseline_report, intent_catalog, run_zero_shot_baseline
from app.arena.ktib import EmptyKtib
from app.core.config import get_config
from app.core.ontology import UNKNOWN_INTENT_ID
from app.llm.client import LLMClient
from app.models.arena import RUN_TYPE_BASELINE, ArenaRun, KtibItem, KtibVersion
from app.models.brain import Exemplar
from app.models.episodes import Episode, Evidence
from app.models.foundry import CanonicalScenario
from tests.arena_helpers import (
    FAST,
    ScriptedZeroShot,
    domain_intents,
    seed_ktib,
    zero_shot_client,
)

CFG = get_config()


@pytest.fixture(autouse=True)
def _empty(db_session):
    for model in (ArenaRun, KtibItem, KtibVersion, Exemplar, Evidence, Episode, CanonicalScenario):
        db_session.execute(delete(model))
    db_session.flush()


def _three_item_ktib(db):
    """gold: EP_1=A, EP_2=A, EP_3=B (발화-EP_n 형식)."""
    a, b = domain_intents(2)
    ktib = seed_ktib(db, [("EP_1", a), ("EP_2", a), ("EP_3", b)])
    return ktib, a, b


def test_baseline_run_records_run_type_and_replay_axes(db_session) -> None:
    """베이스라인 run은 run_type으로 분리되고, replay 4종을 모두 기록한다."""
    ktib, a, b = _three_item_ktib(db_session)
    client = zero_shot_client({"발화-EP_1": (a, 0.8), "발화-EP_2": (b, 0.6), "발화-EP_3": (b, 0.9)})

    result = run_zero_shot_baseline(db_session, client, CFG, model="generic-llm")
    run = result.run

    assert run.run_type == RUN_TYPE_BASELINE
    assert run.model_version == "zero_shot:generic-llm"
    assert run.ktib_version == ktib.ktib_version
    assert run.extractor_versions == ktib.extractor_versions  # KTIB가 동결한 지문 그대로
    assert run.ontology_version and run.persona_state_version
    assert run.metrics["first_intent_accuracy"] == pytest.approx(2 / 3, abs=1e-4)
    assert run.metrics["baseline_model"] == "generic-llm"


def test_report_contains_node_and_domain_breakdown(db_session) -> None:
    """★ AC: 리포트에 노드별·도메인(region)별 분해가 들어간다."""
    ktib, a, b = _three_item_ktib(db_session)
    client = zero_shot_client({"발화-EP_1": (a, 0.8), "발화-EP_2": (b, 0.6), "발화-EP_3": (b, 0.9)})
    result = run_zero_shot_baseline(db_session, client, CFG, model="generic-llm")

    report = baseline_report(result, CFG)
    assert "## 노드(intent)별 분해" in report
    assert "## 도메인(region)별 분해" in report
    assert f"`{a}`" in report and f"`{b}`" in report
    # 두 intent의 region이 표에 나온다
    regions = {m for m in result.run.metrics["by_region"]}
    assert regions and all(r in report for r in regions)
    # 방향성 혼동 쌍(A→B)도 리포트에 남는다
    assert "P(예측=B | 정답=A)" in report


def test_report_proposes_target_without_deciding(db_session) -> None:
    """§8-2: 목표 수치를 자동 확정하지 않는다 — 격차·상대 오류 감소율만 제시하고 승인 요청."""
    ktib, a, b = _three_item_ktib(db_session)
    client = zero_shot_client({"발화-EP_1": (a, 0.8), "발화-EP_2": (b, 0.6), "발화-EP_3": (b, 0.9)})
    result = run_zero_shot_baseline(db_session, client, CFG, model="generic-llm")

    report = baseline_report(result, CFG)
    assert "제안서" in report
    assert "상대 오류 감소율" in report
    assert "사람 승인이 필요한 결정" in report
    assert "이 러너는 어떤 수치도 자동 변경하지 않는다" in report
    # 실제로 config를 건드리지 않았다
    assert get_config().arena.first_intent_accuracy_target == CFG.arena.first_intent_accuracy_target


def test_zero_shot_prompt_has_no_exemplars_or_priors_or_gold(db_session) -> None:
    """★ 베이스라인 정의: 훈련 산출물(exemplar)·prior·정답 라벨이 프롬프트에 새지 않는다."""
    ktib, a, b = _three_item_ktib(db_session)
    provider = ScriptedZeroShot({"발화-EP_1": (a, 0.9)})
    run_zero_shot_baseline(db_session, LLMClient(provider, FAST), CFG, model="m")
    assert provider.calls == 3  # 아이템 수만큼 호출

    prompt = provider.last_prompt
    start = prompt.rfind("```json")
    context_json = prompt[start + 7 : prompt.find("```", start + 7)]
    context = json.loads(context_json)

    # 입력 컨텍스트 키 화이트리스트 — 정답(gold_intent)·계보(episode_id)조차 넣지 않는다.
    # (정적 프롬프트 본문은 "exemplar를 보지 못한다"고 *말하므로* 컨텍스트 블록만 검사한다.)
    assert set(context) == {"intent_catalog", "utterance", "lang", "workspace"}
    for forbidden in ("gold_intent", "exemplar", "persona_prior", "label_distribution",
                      "episode_id", "scenario_id"):
        assert forbidden not in context_json, f"입력 컨텍스트에 {forbidden} 유출"

    catalog_ids = {c["intent_id"] for c in intent_catalog()}
    assert UNKNOWN_INTENT_ID in catalog_ids  # '해당 없음'을 고를 수 있어야 한다(§5-8)
    assert {c["intent_id"] for c in context["intent_catalog"]} == catalog_ids


def test_unknown_prediction_is_abstain_not_confusion(db_session) -> None:
    """UNKNOWN 예측은 abstain — 다른 intent와의 혼동 쌍을 만들지 않는다."""
    ktib, a, b = _three_item_ktib(db_session)
    client = zero_shot_client({}, default_intent=UNKNOWN_INTENT_ID, default_conf=0.05)
    result = run_zero_shot_baseline(db_session, client, CFG, model="m")

    assert result.abstained == 3
    assert result.invalid_predictions == 0  # UNKNOWN은 카탈로그 안 — 계약 위반 아님
    assert result.run.metrics["first_intent_accuracy"] == 0.0
    assert result.run.confusion_matrix == []  # abstain은 혼동 쌍이 아니다


def test_out_of_catalog_prediction_counted_as_violation(db_session) -> None:
    """카탈로그 밖 id는 abstain 처리 + 계약 위반으로 집계 — 조용히 새 intent를 만들지 않는다."""
    ktib, a, b = _three_item_ktib(db_session)
    client = zero_shot_client({}, default_intent="NOT_AN_INTENT", default_conf=0.99)
    result = run_zero_shot_baseline(db_session, client, CFG, model="m")

    assert result.invalid_predictions == 3 and result.abstained == 3
    assert result.run.metrics["invalid_prediction_count"] == 3
    assert result.run.confusion_matrix == []


def test_bad_json_does_not_kill_run_nor_score_as_correct(db_session) -> None:
    """스키마 위반 출력은 abstain으로 처리 — 러너가 죽지도, 정답으로 세지도 않는다."""
    _three_item_ktib(db_session)
    client = zero_shot_client({}, bad_json=True)
    result = run_zero_shot_baseline(db_session, client, CFG, model="m")
    assert result.invalid_predictions == 3
    assert result.run.metrics["first_intent_accuracy"] == 0.0


def test_baseline_does_not_touch_brightness(db_session) -> None:
    """절대 규칙 3: 베이스라인 run은 brain_nodes를 건드리지 않는다."""
    from app.brain.backfill import bootstrap_nodes
    from app.models.brain import BrainNode

    bootstrap_nodes(db_session, approved_by="lab")
    db_session.flush()
    ktib, a, b = _three_item_ktib(db_session)
    client = zero_shot_client({"발화-EP_1": (a, 0.9)})
    run_zero_shot_baseline(db_session, client, CFG, model="m")

    nodes = db_session.scalars(select(BrainNode)).all()
    assert all(n.heldout_accuracy is None and n.last_arena_run is None for n in nodes)


def test_no_ktib_raises(db_session) -> None:
    """발급된 ktib_version이 없으면 0%가 아니라 EmptyKtib."""
    with pytest.raises(EmptyKtib):
        run_zero_shot_baseline(db_session, zero_shot_client({}), CFG, model="m")
