"""T1.9 AC (§1-S6~S10, §5-6).

- S6: 신규 발화가 기존과 임베딩 유사도 ≥ dedup_similarity면 폐기
- S7: 온톨로지 밖 intent → UNKNOWN 라우팅
- S8: Skeptic 산출 → confusion_edges(state=hypothesized) 적재
- S10: label_distribution 합 = 1 ± 0.01
"""
import json
import math

import pytest
from pydantic import ValidationError

from app.core.config import get_config
from app.foundry.agents.runner import AgentOutputError, run_json_agent
from app.foundry.stages.s6_simulator import (
    SimulatorOutput,
    is_duplicate,
    simulate,
)
from app.foundry.stages.s7_analyst import (
    IntentCandidate,
    analyze,
    route_to_ontology,
)
from app.foundry.stages.s8_skeptic import ConfusionPair, record_confusion_edges
from app.foundry.stages.s9_judge import judge
from app.foundry.stages.s10_consensus import build_consensus, build_label_distribution
from app.llm.base import CompletionResult, EmbeddingResult, LLMProvider, Usage
from app.llm.client import LLMClient, LLMConfig
from app.llm.mock import MockProvider
from app.models.brain import ConfusionEdge

CFG = get_config()
FAST = LLMConfig(max_retries=0, timeout_s=2.0, retry_backoff_s=0.0)


class _JsonLLM(LLMProvider):
    """지정 payload를 JSON으로 반환하는 테스트용 provider (에이전트 실행기 검증)."""

    name = "json"

    def __init__(self, payload: object) -> None:
        self._payload = payload

    def complete(self, request) -> CompletionResult:
        return CompletionResult(
            text=json.dumps(self._payload, ensure_ascii=False),
            model=request.model, provider=self.name, usage=Usage(1, 1), cost_usd=0.0,
        )

    def embed(self, request) -> EmbeddingResult:
        return MockProvider().embed(request)


def _client(payload: object) -> LLMClient:
    return LLMClient(_JsonLLM(payload), FAST)


def _unit(v: list[float]) -> list[float]:
    n = math.sqrt(sum(x * x for x in v)) or 1.0
    return [x / n for x in v]


def _embed_fn(mapping: dict[str, list[float]]):
    return lambda texts: [mapping[t] for t in texts]


# --- 에이전트 실행기 (JSON 파싱) ---


def test_run_json_agent_parses_fenced_json() -> None:
    class Provider(_JsonLLM):
        def complete(self, request):
            return CompletionResult(
                text='```json\n{"utterance": "다음엔 뭐 할까?"}\n```',
                model=request.model, provider="json", usage=Usage(1, 1), cost_usd=0.0,
            )

    client = LLMClient(Provider(None), FAST)
    out = run_json_agent(client, "prompt", "m", SimulatorOutput)
    assert out.utterance == "다음엔 뭐 할까?"


def test_run_json_agent_rejects_non_json() -> None:
    class Provider(_JsonLLM):
        def complete(self, request):
            return CompletionResult(
                text="이건 JSON이 아니라 그냥 설명입니다",
                model=request.model, provider="json", usage=Usage(1, 1), cost_usd=0.0,
            )

    client = LLMClient(Provider(None), FAST)
    with pytest.raises(AgentOutputError):
        run_json_agent(client, "prompt", "m", SimulatorOutput)


# --- S6: dedup (AC 3) ---


def test_duplicate_utterance_discarded() -> None:
    existing = ["이거 좀 정리해줘"]
    new = "이거 좀 정리해줘"  # 동일 → 유사도 1.0
    embed = _embed_fn({existing[0]: _unit([1.0, 0.0]), new: _unit([1.0, 0.0])})
    assert is_duplicate(new, existing, embed, CFG) is True


def test_distinct_utterance_kept() -> None:
    existing = ["이거 좀 정리해줘"]
    new = "다음 활동 추천해줘"
    embed = _embed_fn({existing[0]: _unit([1.0, 0.0]), new: _unit([0.0, 1.0])})  # 직교
    assert is_duplicate(new, existing, embed, CFG) is False


def test_dedup_boundary_is_inclusive() -> None:
    """유사도 == dedup_similarity면 폐기 (가드는 ≥)."""
    d = CFG.foundry.dedup_similarity
    existing = ["기존 발화"]
    new = "신규 발화"
    a = _unit([1.0, 0.0])
    b = _unit([d, math.sqrt(1 - d * d)])  # cos(a,b) == d
    embed = _embed_fn({existing[0]: a, new: b})
    assert is_duplicate(new, existing, embed, CFG) is True


def test_empty_pool_never_duplicate() -> None:
    assert is_duplicate("첫 발화", [], _embed_fn({}), CFG) is False


def test_simulate_runner_returns_utterance() -> None:
    client = _client({"utterance": "얘들아 이것 좀 봐"})
    out = simulate(client, scenario_id="CS_1", persona_lens="P_hypo_3", model="m")
    assert out.utterance == "얘들아 이것 좀 봐"
    assert out.persona_lens_used == "P_hypo_3"
    assert out.scenario_id == "CS_1"


class _SpyLLM(_JsonLLM):
    """전송된 프롬프트를 캡처해 컨텍스트 주입 여부를 검증."""

    def __init__(self, payload: object) -> None:
        super().__init__(payload)
        self.last_prompt = ""

    def complete(self, request):
        self.last_prompt = request.prompt
        return super().complete(request)


def test_analyze_injects_utterance_into_prompt() -> None:
    """AC 회귀: 에이전트가 발화·시나리오를 실제로 프롬프트에 주입한다 (dead param 방지)."""
    spy = _SpyLLM({"candidates": [{"intent_id": "play_expand", "weight": 1.0}]})
    client = LLMClient(spy, FAST)
    analyze(client, utterance="블록 무너뜨렸어요 어떡하죠", scenario_id="CS_9", model="m")
    assert "블록 무너뜨렸어요 어떡하죠" in spy.last_prompt
    assert "CS_9" in spy.last_prompt


def test_distinct_utterances_produce_distinct_prompts() -> None:
    spy = _SpyLLM({"candidates": [{"intent_id": "play_expand", "weight": 1.0}]})
    client = LLMClient(spy, FAST)
    analyze(client, utterance="첫 발화", scenario_id="CS_1", model="m")
    p1 = spy.last_prompt
    analyze(client, utterance="완전히 다른 발화", scenario_id="CS_2", model="m")
    assert p1 != spy.last_prompt


# --- S7: UNKNOWN 라우팅 (AC 2) ---


def test_unmapped_intent_routed_to_unknown() -> None:
    valid = {"play_expand", "text_naturalize", "UNKNOWN"}
    cands = [
        IntentCandidate(intent_id="play_expand", weight=0.6),
        IntentCandidate(intent_id="flying_unicorn_intent", weight=0.4, rationale="근거"),
    ]
    routed = route_to_ontology(cands, valid)
    by_orig = {c.unmapped_from or c.intent_id: c for c in routed}
    assert by_orig["play_expand"].intent_id == "play_expand"
    unicorn = next(c for c in routed if c.unmapped_from == "flying_unicorn_intent")
    assert unicorn.intent_id == "UNKNOWN"
    assert unicorn.rationale == "근거"  # 자유 서술 보존 (온톨로지 확장 큐)


def test_valid_intents_unchanged() -> None:
    valid = {"play_expand", "UNKNOWN"}
    routed = route_to_ontology([IntentCandidate(intent_id="play_expand", weight=1.0)], valid)
    assert routed[0].intent_id == "play_expand"
    assert routed[0].unmapped_from is None


def test_unknown_stays_unknown() -> None:
    valid = {"play_expand", "UNKNOWN"}
    routed = route_to_ontology([IntentCandidate(intent_id="UNKNOWN", weight=1.0)], valid)
    assert routed[0].intent_id == "UNKNOWN"


# --- S8: confusion edges (AC 4) ---


def test_skeptic_pairs_persisted_as_hypothesized(db_session) -> None:
    pairs = [ConfusionPair(from_true="visual_naturalize", to_predicted="text_naturalize")]
    created = record_confusion_edges(db_session, pairs)
    db_session.flush()
    assert len(created) == 1
    edge = created[0]
    assert edge.state == "hypothesized"
    assert edge.origin == "SKEPTIC"
    assert edge.edge_id.startswith("CE_")


def test_duplicate_edge_not_recreated(db_session) -> None:
    pairs = [ConfusionPair(from_true="a_intent", to_predicted="b_intent")]
    record_confusion_edges(db_session, pairs)
    db_session.flush()
    again = record_confusion_edges(db_session, pairs)
    db_session.flush()
    assert again == []
    count = (
        db_session.query(ConfusionEdge)
        .filter(ConfusionEdge.from_true == "a_intent", ConfusionEdge.to_predicted == "b_intent")
        .count()
    )
    assert count == 1


def test_edge_is_directional(db_session) -> None:
    record_confusion_edges(db_session, [ConfusionPair(from_true="x1", to_predicted="y1")])
    created = record_confusion_edges(db_session, [ConfusionPair(from_true="y1", to_predicted="x1")])
    db_session.flush()
    assert len(created) == 1  # (x,y) != (y,x)


# --- S9: judge ---


def test_judge_accept_parsed() -> None:
    client = _client({"verdict": "accept", "reason_code": None, "note": "적합"})
    v = judge(client, utterance="발화", scenario_id="CS_1", candidates=["play_expand"], model="m")
    assert v.verdict == "accept"


def test_judge_reject_requires_reason() -> None:
    """reject인데 reason_code가 없으면 계약 위반 → 실행기가 AgentOutputError로 감싼다."""
    client = _client({"verdict": "reject", "reason_code": None})
    with pytest.raises(AgentOutputError):
        judge(client, utterance="발화", scenario_id="CS_1", candidates=["play_expand"], model="m")


def test_judge_reject_with_reason_ok() -> None:
    client = _client({"verdict": "reject", "reason_code": "DEV_INAPPROPRIATE", "note": "부적합"})
    v = judge(client, utterance="발화", scenario_id="CS_1", candidates=["play_expand"], model="m")
    assert v.verdict == "reject" and v.reason_code == "DEV_INAPPROPRIATE"


# --- S10: label distribution (AC 1) ---


def test_label_distribution_sums_to_one() -> None:
    dist = build_label_distribution({"play_expand": 3.0, "text_naturalize": 1.0})
    assert abs(sum(dist.values()) - 1.0) <= 0.01
    assert all(0 <= p <= 1 for p in dist.values())
    assert dist["play_expand"] == pytest.approx(0.75)


def test_all_zero_weights_route_to_unknown() -> None:
    dist = build_label_distribution({"play_expand": 0.0, "text_naturalize": 0.0})
    assert dist == {"UNKNOWN": 1.0}


def test_empty_weights_route_to_unknown() -> None:
    assert build_label_distribution({}) == {"UNKNOWN": 1.0}


def test_non_finite_weight_rejected_at_contract() -> None:
    """inf/nan weight는 IntentCandidate 계약에서 거부 (분포 붕괴 방지)."""
    with pytest.raises(ValidationError):
        IntentCandidate(intent_id="play_expand", weight=float("inf"))


def test_non_finite_weight_defensively_routed_to_unknown() -> None:
    """직접 호출 방어: inf/nan은 무시되어 분포에 들어가지 않는다."""
    dist = build_label_distribution({"a": float("inf"), "b": float("nan")})
    assert dist == {"UNKNOWN": 1.0}
    mixed = build_label_distribution({"a": float("inf"), "b": 1.0})
    assert mixed == {"b": 1.0}


def test_consensus_flags_close_analyst_candidates() -> None:
    """상위 두 후보가 margin 이내면 disagreement로 기록 (§5-6 CONSENSUS_DISAGREEMENT)."""
    result = build_consensus(
        [
            IntentCandidate(intent_id="play_expand", weight=0.5),
            IntentCandidate(intent_id="play_transition_next_step", weight=0.5),
        ]
    )
    assert ["play_expand", "play_transition_next_step"] in result.disagreement_pairs


def test_consensus_distribution_valid() -> None:
    candidates = [
        IntentCandidate(intent_id="play_expand", weight=0.57),
        IntentCandidate(intent_id="play_transition_next_step", weight=0.25),
        IntentCandidate(intent_id="UNKNOWN", weight=0.08),
    ]
    result = build_consensus(candidates)
    assert abs(sum(result.label_distribution.values()) - 1.0) <= 0.01
    assert result.top_intent == "play_expand"
    assert 0 <= result.consensus <= 1


def test_consensus_records_disagreement() -> None:
    candidates = [
        IntentCandidate(intent_id="play_expand", weight=0.5),
        IntentCandidate(intent_id="play_transition_next_step", weight=0.5),
    ]
    result = build_consensus(
        candidates,
        confusion_pairs=[ConfusionPair(from_true="play_expand",
                                       to_predicted="play_transition_next_step")],
    )
    assert ["play_expand", "play_transition_next_step"] in result.disagreement_pairs
