"""S9. Domain Judge — 유아교육 타당성 검증 (§1-S9).

발달 적합성·누리과정 정합성·현장 개연성. reject 시 사유 코드 필수.
reject율 > config.foundry.judge_reject_max 감시는 배치 러너(S11/Pilot)의 몫.
"""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from app.foundry.agents.runner import render_agent_prompt, run_json_agent
from app.foundry.prompts import load_prompt
from app.llm.client import LLMClient

PROMPT = load_prompt("s9_judge")


class JudgeVerdict(BaseModel):
    model_config = ConfigDict(extra="forbid")

    verdict: Literal["accept", "reject"]
    reason_code: str | None = None
    note: str | None = None

    @model_validator(mode="after")
    def _reject_needs_reason(self) -> JudgeVerdict:
        if self.verdict == "reject" and not self.reason_code:
            raise ValueError("reject verdict는 reason_code 필수 (§1-S9)")
        return self


def judge(
    client: LLMClient, *, utterance: str, scenario_id: str, candidates: list[str], model: str
) -> JudgeVerdict:
    prompt = render_agent_prompt(
        PROMPT, {"utterance": utterance, "scenario_id": scenario_id, "candidates": candidates}
    )
    return run_json_agent(client, prompt, model, JudgeVerdict)
