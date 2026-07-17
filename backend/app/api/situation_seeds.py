"""화면 씨드 웹 관리 — /v1/situation-seeds (2026-07-17 사용자 요청).

seeds/situation_seeds_v1.yaml(수동 작성 원천)의 웹 편집 문이다:
- 저장은 **전체 파일 재검증**(로더와 동일 계약: 어휘·vs-1.0·도메인 커버리지) 통과 후에만.
  우회 저장 경로 없음 — 웹에서 넣어도 파일이 곧 원천이고, 이력은 git 커밋이 남긴다.
- PIN+작성자 필수(오클릭 방지·감사), 모든 변경은 governance_events 기록.
- 확장 미리보기는 저장 없이 LLM 1회 — "채우면 확장된다"를 증산 전에 눈으로 확인하는 용도.
"""
from __future__ import annotations

import hmac
import os
import re
import uuid
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal, get_args

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, ValidationError, field_validator
from sqlalchemy.orm import Session

from app.contracts.visual_semantics import (
    ActivityType,
    GroupSizeBand,
    InteractionPattern,
    Material,
    ObservedAction,
    SceneType,
    SpatialPattern,
)
from app.core.config import get_config
from app.core.db import get_session
from app.core.ontology import CANONICAL_DOMAINS
from app.foundry.seed_expansion import expand_variants
from app.foundry.situation_seeds import (
    DEFAULT_SITUATION_SEED_PATH,
    SituationSeed,
    SituationSeedError,
    SituationSeedFile,
    expansion_unmet,
    load_situation_seeds,
    save_situation_seeds,
)
from app.llm.client import LLMClient, get_llm_client
from app.models.governance import GovernanceEvent

router = APIRouter(prefix="/v1/situation-seeds", tags=["situation-seeds"])

SEED_EDIT_EVENT = "SITUATION_SEED_EDIT"


def _pin() -> str:
    """오클릭 방지 자물쇠 — 의도 목록·채점 PIN과 동일 관례(기본 2341, env로 교체)."""
    return os.environ.get("SITUATION_SEED_PIN") or os.environ.get("ARENA_PIN") or "2341"


def _check_pin(pin: str) -> None:
    if not hmac.compare_digest(pin, _pin()):
        raise HTTPException(status_code=401, detail="비밀번호가 달라요")


def get_seed_path() -> Path:
    return DEFAULT_SITUATION_SEED_PATH


@lru_cache(maxsize=1)
def get_expand_client() -> LLMClient:
    return get_llm_client()


# --- 조회: 폼을 그리는 데 필요한 전부 (어휘·vs-1.0·씨드·최소기준 판정) ---


class SeedItem(BaseModel):
    seed_id: str
    domains: list[str]
    workspace_state: dict[str, Any]
    ready: bool                # 확장 최소기준 충족 여부
    unmet: list[str]           # 미달 사유 (체크리스트용)


class SeedCatalogOut(BaseModel):
    version: str
    domains: list[str]
    scenario_variants: int     # config 에코 — 프론트 하드코딩 금지
    vocabulary: dict[str, dict[str, str]]
    vs_vocabulary: dict[str, list[str]]
    seeds: list[SeedItem]


@router.get("", response_model=SeedCatalogOut)
def seed_catalog(seed_path: Path = Depends(get_seed_path)) -> SeedCatalogOut:
    sf = _load(seed_path)
    items = []
    for s in sf.seeds:
        unmet = expansion_unmet(s.workspace_state)
        items.append(SeedItem(
            seed_id=s.seed_id, domains=s.domains,
            workspace_state=s.workspace_state.model_dump(mode="json", exclude_none=True),
            ready=not unmet, unmet=unmet,
        ))
    return SeedCatalogOut(
        version=sf.version,
        domains=list(CANONICAL_DOMAINS),
        scenario_variants=get_config().foundry.scenario_variants,
        vocabulary={
            "surface_types": sf.vocabulary.surface_types,
            "object_kinds": sf.vocabulary.object_kinds,
            "actions": sf.vocabulary.actions,
        },
        vs_vocabulary={
            "scene_type": list(get_args(SceneType)),
            "activity_types": list(get_args(ActivityType)),
            "materials": list(get_args(Material)),
            "observed_actions": list(get_args(ObservedAction)),
            "interaction_pattern": list(get_args(InteractionPattern)),
            "group_size_band": list(get_args(GroupSizeBand)),
            "spatial_pattern": list(get_args(SpatialPattern)),
        },
        seeds=items,
    )


# --- 작성·수정·삭제: PIN+작성자, 전체 재검증, 감사 기록 ---


class SeedBody(BaseModel):
    seed_id: str = Field(min_length=1)
    domains: list[str] = Field(default_factory=list)
    workspace_state: dict[str, Any]


class EditIn(BaseModel):
    pin: str
    editor: str = Field(min_length=1)

    @field_validator("editor")
    @classmethod
    def _editor_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("작성자 이름을 입력하세요")
        return v.strip()


class SeedEditIn(EditIn):
    seed: SeedBody


def _load(seed_path: Path) -> SituationSeedFile:
    try:
        return load_situation_seeds(seed_path)
    except SituationSeedError as exc:
        raise HTTPException(status_code=500, detail=f"씨드 원천 파일이 손상됨: {exc}") from exc


def _rebuild_and_save(
    current: SituationSeedFile, seeds: list[SituationSeed], seed_path: Path,
) -> SituationSeedFile:
    """전체 파일 재검증 → 통과 시에만 저장. 위반은 422(한글 사유) — 파일 무변경."""
    try:
        new_file = SituationSeedFile(
            version=current.version, vocabulary=current.vocabulary, seeds=seeds
        )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_first_error(exc)) from exc
    save_situation_seeds(new_file, seed_path)
    return new_file


def _first_error(exc: ValidationError) -> str:
    first = exc.errors()[0]
    msg = str(first.get("msg", exc)).removeprefix("Value error, ")  # pydantic 접두어 제거
    loc = ".".join(str(x) for x in first.get("loc", ()))
    return f"{msg}{f' (위치: {loc})' if loc else ''}"


def _parse_seed(body: SeedBody) -> SituationSeed:
    try:
        return SituationSeed.model_validate(body.model_dump())
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=_first_error(exc)) from exc


def _audit(
    session: Session, *, action: str, seed_id: str, editor: str,
    extra: dict[str, Any] | None = None,
) -> None:
    session.add(GovernanceEvent(
        event_id="GOV_" + uuid.uuid4().hex[:12],
        event_type=SEED_EDIT_EVENT,
        payload={"action": action, "seed_id": seed_id, **(extra or {})},
        approved_by=editor,
    ))
    session.flush()


@router.post("/seeds")
def create_seed(
    payload: SeedEditIn,
    session: Session = Depends(get_session),
    seed_path: Path = Depends(get_seed_path),
) -> dict:
    _check_pin(payload.pin)
    current = _load(seed_path)
    if any(s.seed_id == payload.seed.seed_id for s in current.seeds):
        raise HTTPException(status_code=409, detail="이미 있는 씨드 id예요 — 다른 이름을 쓰세요")
    new_seed = _parse_seed(payload.seed)
    new_file = _rebuild_and_save(current, [*current.seeds, new_seed], seed_path)
    _audit(session, action="create", seed_id=new_seed.seed_id, editor=payload.editor)
    return {"ok": True, "total": len(new_file.seeds)}


class SeedBulkIn(EditIn):
    seeds: list[SeedBody] = Field(min_length=1)


@router.post("/seeds/bulk")
def bulk_upsert_seeds(
    payload: SeedBulkIn,
    session: Session = Depends(get_session),
    seed_path: Path = Depends(get_seed_path),
) -> dict:
    """CSV 일괄 반영 — 기존 id는 교체, 새 id는 추가. 한 행이라도 위반이면 전부 거부(원자성)."""
    _check_pin(payload.pin)
    current = _load(seed_path)

    ids = [b.seed_id for b in payload.seeds]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    if dupes:
        raise HTTPException(status_code=422, detail=f"CSV 안에 씨드 id 중복: {', '.join(dupes)}")

    parsed: list[SituationSeed] = []
    for body in payload.seeds:
        try:
            parsed.append(_parse_seed(body))
        except HTTPException as exc:
            raise HTTPException(
                status_code=422, detail=f"[{body.seed_id}] {exc.detail}"
            ) from exc

    existing_ids = {s.seed_id for s in current.seeds}
    by_id = {p.seed_id: p for p in parsed}
    seeds = [by_id.get(s.seed_id, s) for s in current.seeds]
    seeds += [p for p in parsed if p.seed_id not in existing_ids]
    created = sum(1 for p in parsed if p.seed_id not in existing_ids)
    updated = len(parsed) - created

    new_file = _rebuild_and_save(current, seeds, seed_path)
    _audit(
        session, action="bulk_upsert", seed_id="(csv)", editor=payload.editor,
        extra={"created": created, "updated": updated, "seed_ids": ids},
    )
    return {"ok": True, "created": created, "updated": updated, "total": len(new_file.seeds)}


@router.put("/seeds/{seed_id}")
def update_seed(
    seed_id: str,
    payload: SeedEditIn,
    session: Session = Depends(get_session),
    seed_path: Path = Depends(get_seed_path),
) -> dict:
    _check_pin(payload.pin)
    current = _load(seed_path)
    if all(s.seed_id != seed_id for s in current.seeds):
        raise HTTPException(status_code=404, detail="없는 씨드예요")
    body = payload.seed.model_copy(update={"seed_id": seed_id})  # id는 경로가 기준(불변)
    new_seed = _parse_seed(body)
    seeds = [new_seed if s.seed_id == seed_id else s for s in current.seeds]
    _rebuild_and_save(current, seeds, seed_path)
    _audit(session, action="update", seed_id=seed_id, editor=payload.editor)
    return {"ok": True}


@router.post("/seeds/{seed_id}/delete")
def delete_seed(
    seed_id: str,
    payload: EditIn,
    session: Session = Depends(get_session),
    seed_path: Path = Depends(get_seed_path),
) -> dict:
    _check_pin(payload.pin)
    current = _load(seed_path)
    if all(s.seed_id != seed_id for s in current.seeds):
        raise HTTPException(status_code=404, detail="없는 씨드예요")
    seeds = [s for s in current.seeds if s.seed_id != seed_id]
    _rebuild_and_save(current, seeds, seed_path)  # 도메인 공백이면 여기서 422
    _audit(session, action="delete", seed_id=seed_id, editor=payload.editor)
    return {"ok": True}


# --- 어휘 관리: 보고 있던 화면·행동·카드 목록 (씨드·CSV·검수 라벨의 단일 원천) ---

_VOCAB_ID_RE = re.compile(r"^[a-z][a-z0-9_]{1,40}$")
VocabTable = Literal["surface_types", "object_kinds", "actions"]


class VocabUpsertIn(EditIn):
    table: VocabTable
    vocab_id: str
    label_ko: str = Field(min_length=1)

    @field_validator("vocab_id")
    @classmethod
    def _id_shape(cls, v: str) -> str:
        if not _VOCAB_ID_RE.match(v):
            raise ValueError("id는 영문 소문자·숫자·밑줄(snake_case)이어야 해요 — 예: photo_editor")
        return v

    @field_validator("label_ko")
    @classmethod
    def _label_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("한글 라벨을 입력하세요")
        return v.strip()


class VocabDeleteIn(EditIn):
    table: VocabTable
    vocab_id: str


def _save_vocab_table(
    current: SituationSeedFile, table_name: str, table: dict[str, str], seed_path: Path,
) -> SituationSeedFile:
    new_vocab = current.vocabulary.model_copy(update={table_name: table})
    try:
        new_file = SituationSeedFile(
            version=current.version, vocabulary=new_vocab, seeds=current.seeds
        )
    except ValidationError as exc:  # 삭제로 씨드가 어휘 밖이 되는 경우 등 — 씨드 id 포함 사유
        raise HTTPException(status_code=422, detail=_first_error(exc)) from exc
    save_situation_seeds(new_file, seed_path)
    return new_file


@router.post("/vocabulary")
def upsert_vocabulary(
    payload: VocabUpsertIn,
    session: Session = Depends(get_session),
    seed_path: Path = Depends(get_seed_path),
) -> dict:
    """어휘 추가·라벨 수정 — id는 킨더버스 화면 계약과 동일해야 한다(불변 권장), 라벨은 자유."""
    _check_pin(payload.pin)
    current = _load(seed_path)
    table = dict(getattr(current.vocabulary, payload.table))
    existed = payload.vocab_id in table
    table[payload.vocab_id] = payload.label_ko
    _save_vocab_table(current, payload.table, table, seed_path)
    _audit(
        session, action="vocab_upsert", seed_id=f"{payload.table}:{payload.vocab_id}",
        editor=payload.editor,
        extra={"table": payload.table, "vocab_id": payload.vocab_id,
               "label_ko": payload.label_ko, "updated": existed},
    )
    return {"ok": True, "updated": existed}


@router.post("/vocabulary/delete")
def delete_vocabulary(
    payload: VocabDeleteIn,
    session: Session = Depends(get_session),
    seed_path: Path = Depends(get_seed_path),
) -> dict:
    """어휘 삭제 — 씨드가 쓰는 항목이면 전체 재검증이 거부한다(사유에 씨드 id·값 표시)."""
    _check_pin(payload.pin)
    current = _load(seed_path)
    table = dict(getattr(current.vocabulary, payload.table))
    if payload.vocab_id not in table:
        raise HTTPException(status_code=404, detail="없는 어휘예요")
    del table[payload.vocab_id]
    _save_vocab_table(current, payload.table, table, seed_path)
    _audit(
        session, action="vocab_delete", seed_id=f"{payload.table}:{payload.vocab_id}",
        editor=payload.editor,
        extra={"table": payload.table, "vocab_id": payload.vocab_id},
    )
    return {"ok": True}


# --- 확장 미리보기: 저장 없음, LLM 1회 ---


class ExpandPreviewIn(BaseModel):
    pin: str
    seed_id: str


@router.post("/expand-preview")
def expand_preview(
    payload: ExpandPreviewIn,
    seed_path: Path = Depends(get_seed_path),
    client: LLMClient = Depends(get_expand_client),
) -> dict:
    _check_pin(payload.pin)
    sf = _load(seed_path)
    anchor = next((s for s in sf.seeds if s.seed_id == payload.seed_id), None)
    if anchor is None:
        raise HTTPException(status_code=404, detail="없는 씨드예요")
    unmet = expansion_unmet(anchor.workspace_state)
    if unmet:
        raise HTTPException(status_code=422, detail="최소기준 미달: " + " / ".join(unmet))

    domain = anchor.domains[0] if anchor.domains else CANONICAL_DOMAINS[0]
    try:
        variants = expand_variants(
            client, anchor=anchor, vocabulary=sf.vocabulary,
            k=get_config().foundry.scenario_variants, domain=domain,
            model=os.environ.get("LLM_MODEL", "s5-expand"),
        )
    except Exception as exc:  # noqa: BLE001 — LLM·계약 실패를 사용자 문장(502)으로
        raise HTTPException(
            status_code=502, detail=f"확장 생성이 실패했어요 — 잠시 후 다시: {exc}"
        ) from exc
    return {"anchor_seed_id": anchor.seed_id, "domain": domain, "variants": variants}
