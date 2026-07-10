"""Arena 테스트 공유 헬퍼 (T5.2·T5.3·T5.4·T5.5).

test_*가 아니므로 pytest가 수집하지 않는다. KTIB 시드 + 결정론적 zero-shot provider를 제공해
실 LLM/네트워크 없이 벤치마크 러너를 DB 위에서 재현한다.
"""
import json

from app.arena.ktib import build_ktib
from app.core.config import get_config
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.llm.base import CompletionResult, LLMProvider, Usage
from app.llm.client import LLMClient, LLMConfig
from app.models.episodes import Episode
from app.models.foundry import CanonicalScenario

CFG = get_config()
FAST = LLMConfig(max_retries=0, timeout_s=5.0, retry_backoff_s=0.0)


def domain_intents(n: int = 4) -> list[str]:
    """region(domain)을 가진 실 intent — UNKNOWN 제외."""
    return [i.intent_id for i in load_ontology().intents if i.domain][:n]


def workspace(extractor: str = "SYNTH_BUILDER_v1") -> dict:
    return {
        "surface_type": "play_board",
        "objects_summary": {"photo": 2},
        "selection": {"type": "photo", "count": 1},
        "recent_actions": ["move_object"],
        "visual_semantics": [{
            "object_ref": "photo_0",
            "schema_version": "vs-1.0",
            "extractor_version": extractor,
            "scene_type": ["INDOOR_CLASSROOM"],
            "identity_removed": True,
        }],
    }


def add_scenario(db, scenario_id: str, extractor: str = "SYNTH_BUILDER_v1") -> CanonicalScenario:
    row = CanonicalScenario(
        scenario_id=scenario_id, frame_id=None, workspace_state=workspace(extractor),
        variation_of=None, variation_axis=None,
    )
    db.add(row)
    db.flush()
    return row


def add_benchmark_episode(db, epid, intent, *, prompt=None, scenario_id=None) -> Episode:
    """KTIB 자격을 갖춘 벤치마크 에피소드 (BENCHMARK_HOLDOUT ∧ GOLD ∧ LABELED ∧ 비합성)."""
    ep = Episode(
        episode_id=epid, ontology_version="onto-1.0", lang="ko",
        dataset_split="BENCHMARK_HOLDOUT", reliability_tier="GOLD", label_state="LABELED",
        origin_channel="EXPERT_AUTHORED", episode_creator_type="HUMAN_ANNOTATOR",
        primary_subject_type="TEACHER", scenario_id=scenario_id,
        teacher_prompt=prompt or f"발화-{epid}", label_distribution={intent: 1.0},
    )
    db.add(ep)
    db.flush()
    return ep


def seed_ktib(db, rows: list[tuple], *, with_scenario: bool = False):
    """벤치마크를 채우고 ktib_version을 발급한다.

    rows: `(episode_id, gold_intent)` 또는 `(episode_id, gold_intent, teacher_prompt)`.
    발화를 생략하면 `발화-<episode_id>`가 되므로, 발화에 계보가 새면 안 되는 테스트는
    반드시 발화를 명시한다.
    """
    for row in rows:
        epid, intent = row[0], row[1]
        prompt = row[2] if len(row) > 2 else None
        scenario_id = None
        if with_scenario:
            scenario_id = f"CS_{epid}"
            add_scenario(db, scenario_id)
        add_benchmark_episode(db, epid, intent, prompt=prompt, scenario_id=scenario_id)
    return build_ktib(db, CFG)


class ScriptedZeroShot(LLMProvider):
    """발화 → (intent_id, confidence) 스크립트를 따르는 결정론적 zero-shot provider.

    answers에 없는 발화는 default_intent(기본 UNKNOWN)로 답한다. bad_json=True면 계약 위반 모사.
    """

    name = "scripted-zero-shot"

    def __init__(self, answers: dict[str, tuple[str, float]], *,
                 default_intent: str = UNKNOWN_INTENT_ID, default_conf: float = 0.1,
                 bad_json: bool = False) -> None:
        self._answers = answers
        self._default = (default_intent, default_conf)
        self._bad_json = bad_json
        self.calls = 0
        self.last_prompt = ""

    def complete(self, request) -> CompletionResult:
        self.calls += 1
        self.last_prompt = request.prompt
        if self._bad_json:
            return self._result(request, "설명만 하고 JSON을 안 준다")
        utterance = self._context(request.prompt)["utterance"]
        intent, conf = self._answers.get(utterance, self._default)
        return self._result(
            request,
            json.dumps({"intent_id": intent, "confidence": conf, "rationale": "s"},
                       ensure_ascii=False),
        )

    @staticmethod
    def _context(prompt: str) -> dict:
        # 마지막 ```json 블록이 render_agent_prompt가 붙인 입력 컨텍스트(앞 블록은 출력 예시)
        start = prompt.rfind("```json")
        return json.loads(prompt[start + 7 : prompt.find("```", start + 7)])

    @staticmethod
    def _result(request, text: str) -> CompletionResult:
        usage = Usage(prompt_tokens=max(1, len(request.prompt) // 4),
                      completion_tokens=max(1, len(text) // 4))
        return CompletionResult(text=text, model=request.model, provider="scripted-zero-shot",
                                usage=usage, cost_usd=0.0)

    def embed(self, request):  # pragma: no cover
        raise NotImplementedError


def zero_shot_client(answers: dict[str, tuple[str, float]], **kwargs) -> LLMClient:
    return LLMClient(ScriptedZeroShot(answers, **kwargs), FAST)
