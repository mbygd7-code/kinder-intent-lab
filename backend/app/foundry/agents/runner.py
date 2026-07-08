"""LLM 에이전트 공통 실행기 — 프롬프트 호출 → JSON 파싱 → 스키마 검증.

S6~S10 각 에이전트는 프롬프트 계약(입력·출력 스키마·금지사항)을 갖고, 출력은 JSON이다.
LLM이 코드펜스(```json)로 감싸는 경우까지 관대하게 파싱한다.
"""
from __future__ import annotations

import json
import re
from typing import TypeVar

from pydantic import BaseModel, ValidationError

from app.llm.client import CompletionRequest, LLMClient

T = TypeVar("T", bound=BaseModel)

_FENCE = re.compile(r"```(?:json)?\s*(.*?)\s*```", re.DOTALL)


class AgentOutputError(Exception):
    """에이전트 출력이 JSON이 아니거나 스키마에 맞지 않음."""


def _extract_json(text: str) -> object:
    candidate = text.strip()
    fenced = _FENCE.search(candidate)
    if fenced:
        candidate = fenced.group(1).strip()
    try:
        return json.loads(candidate)
    except json.JSONDecodeError as exc:
        # 본문 어딘가의 첫 { … } 블록을 시도
        start, end = candidate.find("{"), candidate.rfind("}")
        if 0 <= start < end:
            try:
                return json.loads(candidate[start : end + 1])
            except json.JSONDecodeError:
                pass
        raise AgentOutputError(f"JSON 파싱 실패: {text[:120]!r}") from exc


def render_agent_prompt(base_prompt: str, context: dict[str, object]) -> str:
    """프롬프트 계약(정적) 뒤에 이번 호출의 입력 컨텍스트(JSON)를 붙인다.

    이 조립을 거치지 않으면 LLM은 정적 템플릿만 받아 발화·시나리오에 조건화되지 못한다.
    """
    body = json.dumps(context, ensure_ascii=False, indent=2)
    return f"{base_prompt}\n\n## 입력 컨텍스트 (이번 호출)\n```json\n{body}\n```\n"


def run_json_agent(client: LLMClient, prompt: str, model: str, schema: type[T]) -> T:
    result = client.complete(CompletionRequest(prompt=prompt, model=model))
    data = _extract_json(result.text)
    try:
        return schema.model_validate(data)
    except ValidationError as exc:
        raise AgentOutputError(f"출력이 {schema.__name__} 계약 위반: {exc}") from exc
