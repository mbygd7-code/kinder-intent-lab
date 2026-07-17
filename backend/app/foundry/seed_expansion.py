"""S5 씨드 확장 — 수동 씨드(앵커)를 통제 어휘 안에서 변형 k개로 확장 (§1-S5).

"씨드가 최소기준대로 채워지면 그 씨드가 확장된다"(2026-07-17 사용자 요청):
- 앵커 자격은 expansion_unmet()==[] 인 씨드만 — 미달 씨드는 원본 그대로만 쓰인다
- 프롬프트 계약은 prompts/s5_situation_builder.md, 호출은 run_json_agent(교정 재시도 1회)
- 출력 전수 검증: §1-S5 스키마(ScenarioWorkspaceState) + 씨드 어휘 + 최소기준 정합.
  위반 변형이 하나라도 있으면 전체 거부 — 확장이 조용히 어휘를 오염시키지 못한다
- 확장 실패는 증산을 죽이지 않는다: variants_for_domain이 씨드 원본(pick_variants)으로 폴백
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict

from app.foundry.agents.runner import render_agent_prompt, run_json_agent
from app.foundry.prompts import load_prompt
from app.foundry.situation_seeds import (
    SeedVocabulary,
    SituationSeed,
    SituationSeedFile,
    expansion_unmet,
    pick_variants,
    vocabulary_violations,
)
from app.foundry.stages.s5_situation_builder import ScenarioWorkspaceState
from app.llm.client import LLMClient

logger = logging.getLogger(__name__)

PROMPT = load_prompt("s5_situation_builder")


class SeedExpansionError(Exception):
    """확장 출력이 계약 위반 — 변형 수 불일치, 어휘 밖 값, 최소기준 불일치."""


class SeedExpansionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    variants: list[ScenarioWorkspaceState]


def expand_variants(
    client: LLMClient,
    *,
    anchor: SituationSeed,
    vocabulary: SeedVocabulary,
    k: int,
    domain: str,
    model: str,
) -> list[dict[str, Any]]:
    """앵커 씨드의 자연스러운 변형 k개를 생성·전수 검증해 build_scenarios 입력으로 반환."""
    context = {
        "anchor_seed_id": anchor.seed_id,
        "anchor_workspace_state": anchor.workspace_state.model_dump(
            mode="json", exclude_none=True
        ),
        "allowed": {
            "surface_types": sorted(vocabulary.surface_types),
            "actions": sorted(vocabulary.actions),
            "object_kinds": sorted(vocabulary.object_kinds),
        },
        "variants_required": k,
        "domain": domain,
    }
    out = run_json_agent(client, render_agent_prompt(PROMPT, context), model, SeedExpansionOutput)

    if len(out.variants) != k:
        raise SeedExpansionError(f"변형 {len(out.variants)}개 ≠ 요구 {k}개 (§1-S5)")
    for i, ws in enumerate(out.variants):
        problems = vocabulary_violations(ws, vocabulary) + expansion_unmet(ws)
        if problems:
            raise SeedExpansionError(f"변형 {i} 위반: {' / '.join(problems)}")
    return [ws.model_dump(mode="json", exclude_none=True) for ws in out.variants]


def variants_for_domain(
    seed_file: SituationSeedFile,
    *,
    domain: str,
    k: int,
    salt: str,
    llm_client: LLMClient | None = None,
    model: str = "s5",
    enabled: bool = True,
) -> list[dict[str, Any]]:
    """도메인 변형 k개 — 확장 가능하면 LLM 확장, 아니면(또는 실패하면) 씨드 원본.

    폴백 정책은 에피소드 단위 실패 허용과 같은 철학: 확장 한 번의 실패가 증산을 멈추지 않는다.
    """
    if llm_client is None or not enabled:
        return pick_variants(seed_file, domain=domain, k=k, salt=salt)

    ready = sorted(
        (
            s for s in seed_file.seeds
            if (not s.domains or domain in s.domains) and not expansion_unmet(s.workspace_state)
        ),
        key=lambda s: s.seed_id,
    )
    if not ready:
        logger.warning("도메인 %s에 확장 가능한 씨드 없음 — 원본 사용", domain)
        return pick_variants(seed_file, domain=domain, k=k, salt=salt)

    offset = int.from_bytes(hashlib.sha256(salt.encode("utf-8")).digest()[:8], "big")
    anchor = ready[offset % len(ready)]
    try:
        return expand_variants(
            llm_client, anchor=anchor, vocabulary=seed_file.vocabulary,
            k=k, domain=domain, model=model,
        )
    except Exception as exc:  # noqa: BLE001 — LLM·계약 실패 전부 폴백 대상(증산 무중단)
        logger.warning("씨드 확장 실패(%s, anchor=%s) — 원본 폴백: %s", domain, anchor.seed_id, exc)
        return pick_variants(seed_file, domain=domain, k=k, salt=salt)
