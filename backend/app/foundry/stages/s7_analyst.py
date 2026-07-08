"""S7. Intent Analyst — (발화 + scenario) → 잠재 intent 후보 + rationale (§1-S7).

온톨로지 v1의 intent_id만 사용. 매핑 불가한 후보는 UNKNOWN으로 라우팅하고 자유 서술을
보존한다(온톨로지 확장 큐 공급).
"""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.foundry.agents.runner import render_agent_prompt, run_json_agent
from app.foundry.prompts import load_prompt
from app.llm.client import LLMClient

PROMPT = load_prompt("s7_analyst")


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
        {"utterance": utterance, "scenario_id": scenario_id, "scenario": scenario_context or {}},
    )
    out = run_json_agent(client, prompt, model, AnalystOutput)
    valid = {i.intent_id for i in load_ontology().intents}
    return route_to_ontology(out.candidates, valid)
