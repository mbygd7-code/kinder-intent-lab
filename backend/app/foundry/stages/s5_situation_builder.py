"""S5. Situation Builder — situation_frame → canonical scenario (§1-S5).

- 같은 frame에서 workspace 변형 k개 생성 (k = config.foundry.scenario_variants).
- workspace_state의 visual_semantics는 vs-1.0 통제 어휘를 쓴다 (자유 서술 금지) — 실서비스
  Visual Context Gateway와 동일 스키마·어휘 (계약 대칭, runtime §3-1).
- 합성 생성분은 extractor_version을 SYNTH_BUILDER_*로 표기해 실측 extractor와 구분.
"""
from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from app.contracts.visual_semantics import VisualSemantics
from app.core.config import ExperimentsConfig
from app.foundry.prompts import load_prompt
from app.models.foundry import CanonicalScenario, SituationFrame

PROMPT = load_prompt("s5_situation_builder")

SYNTH_EXTRACTOR_PREFIX = "SYNTH_BUILDER_"  # §1-S5: 합성 표기 SYNTH_BUILDER_*


class ScenarioVariantCountError(Exception):
    """frame당 변형 수가 config.foundry.scenario_variants와 다름."""


class VisualSemanticsRejected(Exception):
    """workspace_state의 visual_semantics가 vs-1.0 계약 위반 (통제 어휘 밖·자유 서술 등)."""


class ScenarioVisualSemantics(VisualSemantics):
    """scenario workspace의 per-object descriptor — vs-1.0 + object_ref + 합성 표기."""

    object_ref: str = Field(min_length=1)

    @field_validator("extractor_version")
    @classmethod
    def _must_be_synthetic(cls, v: str) -> str:
        if not v.startswith(SYNTH_EXTRACTOR_PREFIX):
            raise ValueError(
                f"합성 생성분 extractor_version은 {SYNTH_EXTRACTOR_PREFIX}* 이어야 함 (§1-S5)"
            )
        return v


class ScenarioWorkspaceState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    surface_type: str
    objects_summary: dict[str, int]
    selection: dict[str, Any]
    recent_actions: list[str]
    visual_semantics: list[ScenarioVisualSemantics]


def new_scenario_id() -> str:
    return f"CS_{uuid.uuid4().hex[:12]}"


def build_scenarios(
    session: Session,
    frame: SituationFrame,
    variants: list[dict[str, Any]],
    config: ExperimentsConfig,
) -> list[CanonicalScenario]:
    """변형 k개를 검증·적재. k ≠ scenario_variants거나 vs-1.0 위반이면 거부."""
    expected = config.foundry.scenario_variants
    if len(variants) != expected:
        raise ScenarioVariantCountError(
            f"변형 {len(variants)}개 ≠ config.foundry.scenario_variants({expected})"
        )

    validated: list[ScenarioWorkspaceState] = []
    for variant in variants:
        try:
            validated.append(ScenarioWorkspaceState.model_validate(variant))
        except ValidationError as exc:
            raise VisualSemanticsRejected(str(exc)) from exc

    scenarios: list[CanonicalScenario] = []
    for i, ws in enumerate(validated):
        scenario = CanonicalScenario(
            scenario_id=new_scenario_id(),
            frame_id=frame.frame_id,
            workspace_state=ws.model_dump(mode="json"),
            variation_of=None,
            variation_axis=f"variant_{i}",
        )
        session.add(scenario)
        scenarios.append(scenario)
    return scenarios
