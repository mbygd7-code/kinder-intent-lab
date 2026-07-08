"""S6. Teacher Simulator — persona lens × scenario → 교사 발화 생성 (§1-S6).

- persona lens는 생성 도구이지 라벨이 아니다 — 발화에 정답 intent를 붙이지 않는다(역방향 생성 금지).
- 중복 통제: 신규 발화가 기존과 임베딩 유사도 ≥ config.foundry.dedup_similarity면 폐기.
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.config import ExperimentsConfig
from app.foundry.agents.runner import render_agent_prompt, run_json_agent
from app.foundry.prompts import load_prompt
from app.foundry.stages.s4_language_miner import cosine_similarity
from app.llm.client import LLMClient

PROMPT = load_prompt("s6_simulator")

EmbedFn = Callable[[list[str]], list[list[float]]]


class SimulatorOutput(BaseModel):
    """S6 LLM 산출 — 발화 텍스트만. 정답 intent는 포함하지 않는다."""

    model_config = ConfigDict(extra="forbid")

    utterance: str = Field(min_length=1)


@dataclass(frozen=True)
class SimulatedUtterance:
    utterance: str
    scenario_id: str
    persona_lens_used: str  # 생성 도구(provenance)이지 라벨이 아니다


def simulate(
    client: LLMClient,
    *,
    scenario_id: str,
    persona_lens: str,
    model: str,
    scenario_context: dict[str, Any] | None = None,
) -> SimulatedUtterance:
    prompt = render_agent_prompt(
        PROMPT,
        {"scenario_id": scenario_id, "persona_lens": persona_lens,
         "scenario": scenario_context or {}},
    )
    out = run_json_agent(client, prompt, model, SimulatorOutput)
    return SimulatedUtterance(
        utterance=out.utterance, scenario_id=scenario_id, persona_lens_used=persona_lens
    )


def is_duplicate(
    utterance: str,
    existing: list[str],
    embed_fn: EmbedFn,
    config: ExperimentsConfig,
) -> bool:
    """기존 발화 중 임베딩 유사도 ≥ dedup_similarity가 하나라도 있으면 중복(폐기 대상)."""
    if not existing:
        return False
    vectors = embed_fn([utterance, *existing])
    new_vec, existing_vecs = vectors[0], vectors[1:]
    threshold = config.foundry.dedup_similarity
    return any(cosine_similarity(new_vec, ev) >= threshold for ev in existing_vecs)
