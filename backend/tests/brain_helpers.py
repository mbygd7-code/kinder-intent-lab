"""Brain 추론/추론-API 테스트 공유 헬퍼 (T3.2·T3.3).

test_*가 아니므로 pytest가 수집하지 않는다. 결정론적 합성 scorer·임베딩·GOLD 시드·요청
빌더를 제공해 추론 파이프라인을 실 LLM/네트워크 없이 DB 위에서 재현한다.
"""
import json

from app.brain.backfill import bootstrap_nodes, select_exemplars
from app.contracts.infer_request import InferRequest
from app.core.config import get_config
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.llm.base import CompletionResult, EmbeddingRequest, LLMProvider, Usage
from app.llm.client import LLMClient, LLMConfig
from app.llm.mock import MockProvider
from app.models.episodes import Episode

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


def _payload(prompt_text, *, mode="gym", teacher_ref="TR_1", gym_extension=None,
             cluster=None, request_id="REQ_1") -> dict:
    """HTTP POST용 JSON-ready 요청 dict. 계약 위반(예: live+gym_extension) 모사도 여기서 만든다."""
    tc: dict = {"teacher_ref": teacher_ref}
    if cluster is not None:
        tc["profile"] = {"persona_cluster": cluster}
    payload: dict = {
        "request_id": request_id, "schema_version": "ir-0.2", "mode": mode,
        "session": {"session_id": "S1", "surface_type": "play_board", "conversation_history": []},
        "prompt": {"text": prompt_text, "lang": "ko"},
        "workspace_context": {"objects": [], "selection": []},
        "recent_actions": [],
        "teacher_context": tc,
    }
    if gym_extension is not None:  # 명시적 null은 계약이 거부 — 없으면 키 생략
        payload["gym_extension"] = gym_extension
    return payload


def _request(prompt_text, **kwargs) -> InferRequest:
    """유효한 InferRequest 객체(추론 파이프라인 직접 호출용)."""
    return InferRequest.model_validate(_payload(prompt_text, **kwargs))


def _client() -> LLMClient:
    return LLMClient(_SyntheticScorer(), FAST)
