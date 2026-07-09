"""T3.2 AC (§5-4·§5-5): 추론 파이프라인 4단계.

- 4단계(retrieval/scorer/prior/normalize) 기여가 inference_log에 분리 기록
- persona 조회 실패 시 default(중립) prior + fallback_used
- 결과에 persona_state_version 포함
- 절대 규칙 5: 훈련 메타데이터(gym_extension)는 scorer 입력(Core)에 절대 안 들어간다
"""
import json

from app.brain.backfill import bootstrap_nodes, select_exemplars
from app.brain.inference import core_signals, infer, retrieve_candidates
from app.brain.priors import (
    issue_state_version,
    set_population_priors,
    set_teacher_priors,
)
from app.contracts.infer_request import (
    GymExtension,
    InferRequest,
    PromptInfo,
    SessionInfo,
    TeacherContext,
    WorkspaceContext,
)
from app.core.config import get_config
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.llm.base import CompletionResult, EmbeddingRequest, LLMProvider, Usage
from app.llm.client import LLMClient, LLMConfig
from app.llm.mock import MockProvider
from app.models.brain import InferenceLog
from app.models.episodes import Episode
from app.models.persona import PersonaCluster

CFG = get_config()
FAST = LLMConfig(max_retries=0, timeout_s=5.0, retry_backoff_s=0.0)


def _embed():
    p = MockProvider(embed_dim=1536)
    return lambda texts: p.embed(EmbeddingRequest(inputs=texts, model="e")).vectors


class _SyntheticScorer(LLMProvider):
    """프롬프트의 candidate_intents를 읽어 결정론적 activation을 돌려준다. 마지막 프롬프트 보관.

    fixed: 모든 후보에 이 activation(없으면 0.9,0.8,… 내림차순). omit: 출력에서 뺄 후보(LLM
    누락 모사). inject: 후보 밖 intent 주입(계약 위반 모사).
    """

    name = "synth-scorer"

    def __init__(self, fixed=None, omit=(), inject=()) -> None:
        self.last_prompt = ""
        self._fixed = fixed
        self._omit = set(omit)
        self._inject = list(inject)

    def complete(self, request) -> CompletionResult:
        self.last_prompt = request.prompt
        cands = self._candidates(request.prompt)
        scores = [
            {
                "intent_id": c,
                "activation": self._fixed if self._fixed is not None
                else round(max(0.1, 0.9 - 0.1 * i), 3),
                "rationale": "syn",
            }
            for i, c in enumerate(cands)
            if c not in self._omit
        ]
        scores += [{"intent_id": x, "activation": 0.99, "rationale": "bogus"} for x in self._inject]
        text = json.dumps({"scores": scores}, ensure_ascii=False)
        usage = Usage(prompt_tokens=max(1, len(request.prompt) // 4),
                      completion_tokens=max(1, len(text) // 4))
        return CompletionResult(text=text, model=request.model, provider=self.name,
                                usage=usage, cost_usd=0.0)

    @staticmethod
    def _candidates(prompt: str) -> list[str]:
        # 마지막 ```json 블록이 render_agent_prompt가 붙인 입력 컨텍스트(앞 블록은 출력 예시)
        start = prompt.rfind("```json")
        block = prompt[start + 7 : prompt.find("```", start + 7)]
        return json.loads(block).get("candidate_intents", [])

    def embed(self, request):  # pragma: no cover
        raise NotImplementedError


def _real_intents(n):
    return [i.intent_id for i in load_ontology().intents if i.intent_id != UNKNOWN_INTENT_ID][:n]


def _gold(db, ep_id, intent, prompt) -> None:
    db.add(Episode(
        episode_id=ep_id, ontology_version="onto-1.0", lang="ko", dataset_split="TRAIN",
        reliability_tier="GOLD", label_state="LABELED", origin_channel="FOUNDRY_SYNTHETIC",
        episode_creator_type="FOUNDRY_PIPELINE", primary_subject_type="SIMULATED_TEACHER",
        teacher_prompt=prompt, label_distribution={intent: 1.0},
    ))


def _seed(db, embed, pairs):
    """노드 부트스트랩 + (intent, prompt) GOLD 에피소드 → exemplar 적재."""
    bootstrap_nodes(db, approved_by="lab")
    for k, (intent, prompt) in enumerate(pairs):
        _gold(db, f"EP_SEED_{k}", intent, prompt)
    db.flush()
    select_exemplars(db, CFG, embed)
    db.flush()


def _request(prompt_text, *, mode="gym", teacher_ref="TR_1", gym_extension=None,
             cluster=None) -> InferRequest:
    tc = (TeacherContext(teacher_ref=teacher_ref, profile={"persona_cluster": cluster})
          if cluster is not None else TeacherContext(teacher_ref=teacher_ref))
    kwargs = dict(
        request_id="REQ_1", schema_version="ir-0.2", mode=mode,
        session=SessionInfo(session_id="S1", surface_type="play_board", conversation_history=[]),
        prompt=PromptInfo(text=prompt_text, lang="ko"),
        workspace_context=WorkspaceContext(objects=[], selection=[]),
        recent_actions=[],
        teacher_context=tc,
    )
    if gym_extension is not None:  # 명시적 null은 계약이 거부 — 없으면 키 생략
        kwargs["gym_extension"] = gym_extension
    return InferRequest(**kwargs)


def _client():
    return LLMClient(_SyntheticScorer(), FAST)


# --- AC 1: 4단계 분리 기록 ---


def test_infer_logs_four_stages(db_session) -> None:
    ints = _real_intents(3)
    _seed(db_session, _embed(), [(ints[0], "이거 자연스럽게 해줘"), (ints[1], "다음엔 뭐하지")])
    result = infer(db_session, _request("이거 자연스럽게 해줘"), _client(), _embed(), CFG)
    db_session.flush()
    log = db_session.get(InferenceLog, result.inference_id)
    assert log is not None
    assert set(log.stages.keys()) == {"retrieval", "scorer", "prior", "normalize"}
    assert log.stages["retrieval"] and log.stages["scorer"]
    assert log.stages["prior"] and log.stages["normalize"]
    assert log.request_id == "REQ_1" and log.top_intent == result.top_intent


def test_result_has_candidates_and_top(db_session) -> None:
    ints = _real_intents(3)
    _seed(db_session, _embed(), [(ints[0], "발화 A"), (ints[1], "발화 B")])
    result = infer(db_session, _request("발화 A"), _client(), _embed(), CFG)
    assert result.top_intent is not None
    assert 0.0 <= result.confidence <= 1.0
    assert 0.0 <= result.margin <= 1.0
    assert len(result.candidates) <= 5
    assert all(c["domain"] for c in result.candidates)  # 온톨로지 도메인 부착


# --- AC 2: persona 조회 실패 → default + fallback_used ---


def test_persona_missing_uses_default_and_fallback(db_session) -> None:
    ints = _real_intents(2)
    _seed(db_session, _embed(), [(ints[0], "발화 하나")])
    # teacher prior 미설정 → 중립 default, fallback_used
    result = infer(db_session, _request("발화 하나", teacher_ref="TR_NOPRIOR"),
                   _client(), _embed(), CFG)
    db_session.flush()
    assert result.fallback_used is True
    assert result.prior_tier == "neutral"
    log = db_session.get(InferenceLog, result.inference_id)
    # 중립 prior → 모든 factor 배수 1.0
    assert all(abs(f["factor"] - 1.0) < 1e-9 for f in log.stages["prior"]["factors"])


# --- AC 3: persona_state_version 포함 + prior 반영 ---


def test_persona_present_state_version_and_factor(db_session) -> None:
    ints = _real_intents(2)
    _seed(db_session, _embed(), [(ints[0], "성향 발화")])
    v = issue_state_version(db_session, reason="t")
    set_teacher_priors(db_session, "TR_P", {ints[0]: 0.9}, v)  # 강한 prior
    db_session.flush()
    result = infer(db_session, _request("성향 발화", teacher_ref="TR_P"),
                   _client(), _embed(), CFG)
    assert result.fallback_used is False
    assert result.prior_tier == "individual"
    assert result.persona_state_version == v  # replay용 버전 동반
    log = db_session.get(InferenceLog, result.inference_id)
    fac = {f["intent_id"]: f["factor"] for f in log.stages["prior"]["factors"]}
    assert fac[ints[0]] > 1.0  # prior 0.9 → 부양(>1)


def test_prior_factor_bounded_by_cap(db_session) -> None:
    """절대 규칙(§5-5): prior 배수는 ±persona_prior_cap을 넘지 못한다."""
    ints = _real_intents(2)
    _seed(db_session, _embed(), [(ints[0], "발화 x")])
    v = issue_state_version(db_session, reason="t")
    set_teacher_priors(db_session, "TR_EXT", {ints[0]: 1.0}, v)  # 극단 prior
    db_session.flush()
    result = infer(db_session, _request("발화 x", teacher_ref="TR_EXT"),
                   _client(), _embed(), CFG)
    cap = CFG.brain.persona_prior_cap
    log = db_session.get(InferenceLog, result.inference_id)
    for f in log.stages["prior"]["factors"]:
        assert 1.0 - cap - 1e-9 <= f["factor"] <= 1.0 + cap + 1e-9


# --- 절대 규칙 5: gym_extension은 scorer 입력에 안 들어간다 ---


def test_rule5_gym_extension_not_in_scorer_input(db_session) -> None:
    ints = _real_intents(2)
    _seed(db_session, _embed(), [(ints[0], "훈련 발화")])
    scorer = _SyntheticScorer()
    client = LLMClient(scorer, FAST)
    gym = GymExtension(scenario_id="SCENARIO_SECRET_X",
                       target_confusion=[["visual_naturalize", "text_naturalize"]],
                       training_strategy="TARGET_CONFUSION")
    infer(db_session, _request("훈련 발화", mode="gym", gym_extension=gym), client, _embed(), CFG)
    # scorer가 실제로 받은 프롬프트에 훈련 메타가 전혀 없어야 한다
    assert "SCENARIO_SECRET_X" not in scorer.last_prompt
    assert "target_confusion" not in scorer.last_prompt
    assert "training_strategy" not in scorer.last_prompt


def test_core_signals_excludes_gym_extension(db_session) -> None:
    gym = GymExtension(scenario_id="SEC", target_confusion=[["a", "b"]])
    core = core_signals(_request("발화", mode="gym", gym_extension=gym))
    dumped = json.dumps(core.__dict__, ensure_ascii=False)
    assert "SEC" not in dumped and "target_confusion" not in dumped


# --- [1] retrieval cap ---


def test_retrieval_capped_at_top_k(db_session) -> None:
    top_k = CFG.brain.retrieval_top_k
    ints = _real_intents(top_k + 5)  # top_k보다 많은 intent에 exemplar
    _seed(db_session, _embed(), [(it, f"고유 발화 {i}") for i, it in enumerate(ints)])
    uvec = _embed()(["임의 질의 발화"])[0]
    cands = retrieve_candidates(db_session, uvec, CFG, _embed())
    assert len(cands) <= top_k


# --- 리뷰 회귀 (adversarial 워크플로 findings) ---


def test_population_prior_used_when_individual_absent(db_session) -> None:
    """F1(§5-3): 개인 prior 없고 cluster가 있으면 population prior로 콜드스타트(중립 아님)."""
    ints = _real_intents(2)
    _seed(db_session, _embed(), [(ints[0], "콜드스타트 발화")])
    db_session.add(PersonaCluster(cluster_id="PC_c", method="HDBSCAN", axes={},
                                  member_count=3, version="pv-1"))
    v = issue_state_version(db_session, reason="pop")
    set_population_priors(db_session, "PC_c", {ints[0]: 0.9}, v)  # cluster prior
    db_session.flush()
    result = infer(db_session, _request("콜드스타트 발화", teacher_ref="TR_NEW", cluster="PC_c"),
                   _client(), _embed(), CFG)
    assert result.prior_tier == "population"   # 개인 아님·중립 아님
    assert result.fallback_used is False       # 유효한 tier가 있었다
    log = db_session.get(InferenceLog, result.inference_id)
    assert log.stages["prior"]["tier"] == "population"
    fac = {f["intent_id"]: f["factor"] for f in log.stages["prior"]["factors"]}
    assert fac[ints[0]] > 1.0  # population prior 0.9 반영


def test_single_candidate_confidence_vs_top_activation(db_session) -> None:
    """F3: 단일 후보는 정규화상 confidence/margin=1.0이지만 top_activation은 원 강도를 보존."""
    ints = _real_intents(1)
    _seed(db_session, _embed(), [(ints[0], "단일 후보 발화")])
    weak = LLMClient(_SyntheticScorer(fixed=0.05), FAST)  # 약한 활성도
    result = infer(db_session, _request("단일 후보 발화"), weak, _embed(), CFG)
    assert result.confidence == 1.0 and result.margin == 1.0  # 정규화상 단독 우세
    assert result.top_activation < 0.2  # 절대 강도는 약함 — 하류 abstain 근거


def test_scorer_omission_backfilled_and_out_of_set_ignored(db_session) -> None:
    """F4: scorer가 후보를 누락하면 0으로 백필(유실 방지), 후보 밖 intent는 무시."""
    ints = _real_intents(2)
    _seed(db_session, _embed(), [(ints[0], "발화 하나 고유"), (ints[1], "발화 둘 고유")])
    scorer = _SyntheticScorer(omit={ints[1]}, inject=["NOT_A_REAL_INTENT"])
    result = infer(db_session, _request("발화 하나 고유"), LLMClient(scorer, FAST), _embed(), CFG)
    db_session.flush()
    log = db_session.get(InferenceLog, result.inference_id)
    acts = {s["intent_id"]: s["activation"] for s in log.stages["scorer"]}
    assert acts.get(ints[1]) == 0.0                         # 누락 후보 0 백필
    assert "NOT_A_REAL_INTENT" not in acts                  # 후보 밖 intent 무시
    assert all(c["intent_id"] != "NOT_A_REAL_INTENT" for c in result.candidates)
