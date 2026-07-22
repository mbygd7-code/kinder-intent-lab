"""S7. Intent Analyst — (발화 + scenario) → 잠재 intent 후보 + rationale (§1-S7).

온톨로지 v1의 intent_id만 사용. 매핑 불가한 후보는 UNKNOWN으로 라우팅하고 자유 서술을
보존한다(온톨로지 확장 큐 공급).

프롬프트에 온톨로지 목록(도메인별 id+definition)을 반드시 싣는다 — 2026-07-22 실측:
목록 없이 실 LLM을 부르면 유효 id를 몰라 자유 서술 → 전량 UNKNOWN 라우팅(94%),
예시의 play 2종만 앵무새로 살아남았다(camp_1b802fdf). mock은 온톨로지에서 뽑아
이 결함이 가려졌었다(07-09 run 0% UNKNOWN).
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.foundry.agents.runner import render_agent_prompt, run_json_agent
from app.foundry.prompts import load_prompt
from app.llm.client import LLMClient

PROMPT = load_prompt("s7_analyst")


@lru_cache(maxsize=1)
def _ontology_digest() -> tuple[tuple[str, tuple[tuple[str, str], ...]], ...]:
    """도메인별 (intent_id, definition) 목록 — 프롬프트 주입용(§1-S7 입력 계약).

    lru_cache를 위해 불변 튜플로 만들고, 사용처에서 dict로 푼다. UNKNOWN 등
    도메인 없는 특수 id는 제외(후보로 유도하지 않는다 — 라우팅이 알아서 붙인다).
    """
    by_domain: dict[str, list[tuple[str, str]]] = {}
    for i in load_ontology().intents:
        if not i.domain:
            continue
        by_domain.setdefault(i.domain, []).append((i.intent_id, i.definition))
    return tuple(sorted((d, tuple(rows)) for d, rows in by_domain.items()))


def ontology_prompt_block() -> dict[str, list[dict[str, str]]]:
    """analyze가 프롬프트 컨텍스트에 싣는 형태 (도메인 → [{intent_id, definition}])."""
    return {
        domain: [{"intent_id": iid, "definition": defn} for iid, defn in rows]
        for domain, rows in _ontology_digest()
    }


class IntentCandidate(BaseModel):
    # allow_inf_nan=False: weight에 inf/nan이 들어오면 거부 (분포 정규화 붕괴 방지)
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

    intent_id: str = Field(min_length=1)
    weight: float = Field(ge=0)
    rationale: str | None = None
    unmapped_from: str | None = None  # UNKNOWN 라우팅 시 원래 제안 id


class AnalystOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    candidates: list[IntentCandidate] = Field(min_length=1)


def route_to_ontology(
    candidates: list[IntentCandidate], valid_intent_ids: set[str]
) -> list[IntentCandidate]:
    """온톨로지 밖 intent_id는 UNKNOWN으로 라우팅 (원 id는 unmapped_from에 보존)."""
    routed: list[IntentCandidate] = []
    for c in candidates:
        if c.intent_id in valid_intent_ids:
            routed.append(c)
        else:
            routed.append(
                c.model_copy(update={"intent_id": UNKNOWN_INTENT_ID, "unmapped_from": c.intent_id})
            )
    return routed


def analyze(
    client: LLMClient,
    *,
    utterance: str,
    scenario_id: str,
    model: str,
    scenario_context: dict[str, Any] | None = None,
) -> list[IntentCandidate]:
    prompt = render_agent_prompt(
        PROMPT,
        {
            "utterance": utterance,
            "scenario_id": scenario_id,
            "scenario": scenario_context or {},
            # §1-S7 입력 계약: 온톨로지 목록 — 이게 빠지면 실 LLM은 유효 id를 모른다
            "ontology_intents": ontology_prompt_block(),
        },
    )
    out = run_json_agent(client, prompt, model, AnalystOutput)
    valid = {i.intent_id for i in load_ontology().intents}
    return route_to_ontology(out.candidates, valid)
