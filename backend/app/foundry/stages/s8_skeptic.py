"""S8. Skeptic — Analyst 해석에 반대, 혼동 후보 쌍 제시 (§1-S8, §5-6).

confusion edge의 최초 공급자. Skeptic이 제시한 쌍은 state=hypothesized로 confusion_edges에
적재된다. 방향성 edge: (A,B) ≠ (B,A). 이미 존재하는 쌍은 재생성하지 않는다.
"""
from __future__ import annotations

import uuid

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.foundry.agents.runner import render_agent_prompt, run_json_agent
from app.foundry.prompts import load_prompt
from app.llm.client import LLMClient
from app.models.brain import ConfusionEdge

PROMPT = load_prompt("s8_skeptic")


class ConfusionPair(BaseModel):
    model_config = ConfigDict(extra="forbid")

    from_true: str = Field(min_length=1)
    to_predicted: str = Field(min_length=1)
    note: str | None = None


class SkepticOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    pairs: list[ConfusionPair] = Field(default_factory=list)


def new_edge_id() -> str:
    return f"CE_{uuid.uuid4().hex[:12]}"


def record_confusion_edges(
    session: Session, pairs: list[ConfusionPair], origin: str = "SKEPTIC"
) -> list[ConfusionEdge]:
    """혼동 쌍을 state=hypothesized로 적재. 이미 있는 (from_true,to_predicted)는 건너뛴다."""
    created: list[ConfusionEdge] = []
    seen: set[tuple[str, str]] = set()  # 같은 호출 내 중복 (autoflush 설정 무관하게 방어)
    for pair in pairs:
        if pair.from_true == pair.to_predicted:
            continue  # 자기 혼동은 의미 없음
        key = (pair.from_true, pair.to_predicted)
        if key in seen:
            continue
        seen.add(key)
        exists = session.scalar(
            select(ConfusionEdge).where(
                ConfusionEdge.from_true == pair.from_true,
                ConfusionEdge.to_predicted == pair.to_predicted,
            )
        )
        if exists is not None:
            continue
        edge = ConfusionEdge(
            edge_id=new_edge_id(),
            from_true=pair.from_true,
            to_predicted=pair.to_predicted,
            state="hypothesized",
            origin=origin,
            contrast_exemplars=[{"note": pair.note}] if pair.note else None,
        )
        session.add(edge)
        created.append(edge)
    return created


def challenge(
    client: LLMClient, *, utterance: str, scenario_id: str, candidates: list[str], model: str
) -> list[ConfusionPair]:
    prompt = render_agent_prompt(
        PROMPT,
        {"utterance": utterance, "scenario_id": scenario_id, "analyst_candidates": candidates},
    )
    out = run_json_agent(client, prompt, model, SkepticOutput)
    return out.pairs
