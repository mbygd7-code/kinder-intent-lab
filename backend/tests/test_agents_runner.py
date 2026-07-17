"""run_json_agent 교정 재시도 AC — 실 LLM의 여분 키(sim-to-real) 흡수 (2026-07-17).

실측 사고: 증산 중 claude가 S7 출력에 'notes' 키를 덧붙여 extra=forbid 계약 위반 →
재시도 없이 전체 런 크래시. mock은 여분 키를 절대 안 넣어 실전에서만 드러났다.
고침: 위반 내용을 프롬프트에 붙여 1회 교정 재시도 — 그래도 위반이면 지금처럼 폭발(정직).
"""
import json

import pytest
from pydantic import BaseModel, ConfigDict

from app.foundry.agents.runner import AgentOutputError, run_json_agent


class _Out(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: str


class _Result:
    def __init__(self, text: str) -> None:
        self.text = text


class _StubClient:
    """호출 순서대로 준비된 응답을 돌려주는 완성 클라이언트 스텁."""

    def __init__(self, responses: list[str]) -> None:
        self._responses = responses
        self.prompts: list[str] = []

    def complete(self, request) -> _Result:
        self.prompts.append(request.prompt)
        return _Result(self._responses[min(len(self.prompts) - 1, len(self._responses) - 1)])


GOOD = json.dumps({"value": "ok"})
EXTRA_KEY = json.dumps({"value": "ok", "notes": "재호출을 권장"})  # 실측 사고 재현


def test_clean_output_single_call() -> None:
    client = _StubClient([GOOD])
    out = run_json_agent(client, "p", "m", _Out)
    assert out.value == "ok" and len(client.prompts) == 1


def test_contract_violation_retries_once_with_correction() -> None:
    """★ 여분 키 1회 → 위반 내용을 붙여 재호출 → 성공. 런 전체가 죽지 않는다."""
    client = _StubClient([EXTRA_KEY, GOOD])
    out = run_json_agent(client, "p", "m", _Out)
    assert out.value == "ok"
    assert len(client.prompts) == 2
    # 재시도 프롬프트에 교정 지시(위반 사실 + 스키마 밖 키 금지)가 실려야 한다
    assert "계약 위반" in client.prompts[1] and "notes" in client.prompts[1]


def test_persistent_violation_still_raises() -> None:
    """교정해도 위반이면 조용히 통과시키지 않는다 — 지금처럼 폭발(정직)."""
    client = _StubClient([EXTRA_KEY, EXTRA_KEY])
    with pytest.raises(AgentOutputError):
        run_json_agent(client, "p", "m", _Out)
    assert len(client.prompts) == 2  # 1회만 재시도


def test_json_parse_failure_also_retries() -> None:
    client = _StubClient(["이건 JSON이 아님", GOOD])
    out = run_json_agent(client, "p", "m", _Out)
    assert out.value == "ok" and len(client.prompts) == 2
