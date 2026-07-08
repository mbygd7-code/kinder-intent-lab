"""S4. Teacher Language Miner — 표현 패턴만 추출해 Atlas 적재 (§1-S4, §2).

절대 규칙 7: 원문 인용 저장 금지. 패러프레이즈된 대표형(surface_form)만 저장하며,
대표형이 원문과 임베딩 유사도 > config.foundry.paraphrase_max면 원문 잔존으로 간주해 폐기.
원문(raw_text)은 이 함수 어디에서도 저장하지 않는다 (in-memory 비교용).
"""
from __future__ import annotations

import math
import uuid
from collections.abc import Callable
from typing import Any

from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from app.core.config import ExperimentsConfig
from app.foundry.prompts import load_prompt
from app.models.foundry import AtlasEntry

PROMPT = load_prompt("s4_language_miner")

# texts -> 임베딩 벡터들 (production: get_embedding_client().embed(...).vectors)
EmbedFn = Callable[[list[str]], list[list[float]]]


class ParaphraseTooSimilar(Exception):
    """대표형이 원문과 너무 유사 — 원문 잔존 위험으로 폐기 (절대 규칙 7)."""


class AtlasInput(BaseModel):
    """S4 LLM 산출 — Atlas entry 후보. representative는 원문이 아닌 패러프레이즈."""

    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    representative: str = Field(min_length=1)
    pattern_cluster: str = Field(min_length=1)
    ambiguity_types: list[str]
    possible_intents: list[str]
    resolution_signals: list[dict[str, Any]]
    # 'register'는 BaseModel 속성과 충돌 → 내부 이름 분리, JSON 키는 alias로 유지
    register_info: dict[str, Any] | None = Field(default=None, alias="register")
    source_class_mix: dict[str, float] | None = None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b, strict=True))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def paraphrase_similarity(raw_text: str, representative: str, embed_fn: EmbedFn) -> float:
    raw_vec, rep_vec = embed_fn([raw_text, representative])
    return cosine_similarity(raw_vec, rep_vec)


def new_atlas_id() -> str:
    return f"ATL_{uuid.uuid4().hex[:12]}"


def mine_atlas_entry(
    session: Session,
    *,
    raw_text: str,
    atlas: AtlasInput,
    embed_fn: EmbedFn,
    config: ExperimentsConfig,
) -> AtlasEntry:
    """대표형을 Atlas에 적재한다. 원문 유사도 가드 통과 시에만 (원문은 저장 안 함)."""
    similarity = paraphrase_similarity(raw_text, atlas.representative, embed_fn)
    if similarity > config.foundry.paraphrase_max:
        raise ParaphraseTooSimilar(
            f"대표형 유사도 {similarity:.3f} > paraphrase_max "
            f"{config.foundry.paraphrase_max} — 원문 잔존, 폐기"
        )
    entry = AtlasEntry(
        atlas_id=new_atlas_id(),
        surface_form=atlas.representative,
        pattern_cluster=atlas.pattern_cluster,
        ambiguity_types=atlas.ambiguity_types,
        possible_intents=atlas.possible_intents,
        resolution_signals=atlas.resolution_signals,
        register=atlas.register_info,
        source_class_mix=atlas.source_class_mix,
    )
    session.add(entry)
    return entry
