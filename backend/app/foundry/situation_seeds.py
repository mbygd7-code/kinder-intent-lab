"""킨더버스 화면 씨드 — seeds/situation_seeds_v1.yaml(수동 작성) 로더 + 결정론 선택.

S5 workspace 변형의 유일한 원천이다. 2026-07-17까지 변형이 pilot의 코드 템플릿
(_make_variant) 복제라 전 시나리오가 play_board 단일 화면으로 굳었던 사고의 재발 방지:
- 화면 기본값은 사람이 씨드 파일에 작성하고, 코드는 고르기만 한다
- 어휘 밖 값·vs-1.0 위반·도메인 공백은 로드 시점(=증산 시작 전)에 거부한다
- 같은 salt → 같은 변형 (재현 가능한 증산, §1-S5 변형 수 계약은 build_scenarios가 강제)
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator

from app.core.ontology import CANONICAL_DOMAINS
from app.foundry.stages.s5_situation_builder import ScenarioWorkspaceState

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SITUATION_SEED_PATH = _REPO_ROOT / "seeds" / "situation_seeds_v1.yaml"


class SituationSeedError(Exception):
    """씨드 파일이 계약 위반 — 어휘 밖 값, vs-1.0 위반, 도메인 공백, 중복 id 등."""


def vocabulary_violations(ws: ScenarioWorkspaceState, vocab: SeedVocabulary) -> list[str]:
    """씨드 어휘 밖 값 목록 — 로더와 확장 검증이 같은 잣대를 쓴다(이중 기준 방지)."""
    problems: list[str] = []
    if ws.surface_type not in vocab.surface_types:
        problems.append(f"어휘에 없는 surface_type '{ws.surface_type}'")
    bad_actions = set(ws.recent_actions) - set(vocab.actions)
    if bad_actions:
        problems.append(f"어휘에 없는 action {sorted(bad_actions)}")
    bad_objects = set(ws.objects_summary) - set(vocab.object_kinds)
    if bad_objects:
        problems.append(f"어휘에 없는 object {sorted(bad_objects)}")
    sel_type = ws.selection.get("type")
    if sel_type is not None and sel_type not in vocab.object_kinds:
        problems.append(f"어휘에 없는 selection.type '{sel_type}'")
    return problems


def expansion_unmet(ws: ScenarioWorkspaceState) -> list[str]:
    """확장 최소기준 미달 사유 — 빈 화면·사진↔서술 불일치·과다 선택은 확장 앵커가 못 된다.

    로더 통과(스키마·어휘)보다 한 단계 높은 '작성 완성도' 기준이다. 미달 씨드는 저장은
    되지만 확장에는 쓰이지 않는다(원본 그대로만 사용) — UI가 이 목록을 체크리스트로 보여준다.
    """
    unmet: list[str] = []
    if sum(ws.objects_summary.values()) < 1:
        unmet.append("화면에 카드가 하나도 없음 — 카드(사진·글 등)를 1개 이상 놓아주세요")
    photos = ws.objects_summary.get("photo", 0)
    if photos > 0 and not ws.visual_semantics:
        unmet.append("사진이 있는데 사진 서술(visual_semantics)이 없음 — 최소 1장 서술 필요")
    if photos == 0 and ws.visual_semantics:
        unmet.append("사진이 없는데 사진 서술이 있음 — 서술을 지우거나 사진을 추가하세요")
    sel_type = ws.selection.get("type")
    if sel_type:
        have = ws.objects_summary.get(sel_type, 0)
        count = ws.selection.get("count")
        want = count if isinstance(count, int) else 1
        if want > have:
            unmet.append(f"'{sel_type}' {want}개 선택인데 화면에는 {have}개뿐 — 수를 맞춰주세요")
    return unmet


class SeedVocabulary(BaseModel):
    """씨드가 쓸 수 있는 화면 어휘 — {id: 한글 라벨}. 검수 화면 라벨 맵과 같은 집합을 유지한다."""

    model_config = ConfigDict(extra="forbid")

    surface_types: dict[str, str] = Field(min_length=1)
    object_kinds: dict[str, str] = Field(min_length=1)
    actions: dict[str, str] = Field(min_length=1)


class SituationSeed(BaseModel):
    model_config = ConfigDict(extra="forbid")

    seed_id: str = Field(min_length=1)
    domains: list[str] = Field(default_factory=list)  # 빈 리스트 = 모든 도메인 후보
    workspace_state: ScenarioWorkspaceState


class SituationSeedFile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(min_length=1)
    vocabulary: SeedVocabulary
    seeds: list[SituationSeed] = Field(min_length=1)

    @model_validator(mode="after")
    def _coherent(self) -> SituationSeedFile:
        seen: set[str] = set()
        for seed in self.seeds:
            if seed.seed_id in seen:
                raise ValueError(f"seed_id 중복: {seed.seed_id}")
            seen.add(seed.seed_id)

            unknown_domains = set(seed.domains) - set(CANONICAL_DOMAINS)
            if unknown_domains:
                raise ValueError(f"{seed.seed_id}: 정본에 없는 도메인 {sorted(unknown_domains)}")

            problems = vocabulary_violations(seed.workspace_state, self.vocabulary)
            if problems:
                raise ValueError(
                    f"{seed.seed_id}: {' / '.join(problems)} — vocabulary에 먼저 등록하세요"
                )

        # 도메인 공백 = 증산 배분 단계에서의 즉사 — 로드 시점에 거부한다
        for domain in CANONICAL_DOMAINS:
            if not any(not s.domains or domain in s.domains for s in self.seeds):
                raise ValueError(f"도메인 {domain}에 후보 씨드가 없음 — 씨드를 추가하세요")
        return self


def load_situation_seeds(path: str | Path | None = None) -> SituationSeedFile:
    """씨드 파일을 로드·검증한다. 계약 위반이면 SituationSeedError (증산 시작 전 조기 실패)."""
    seed_path = Path(path) if path is not None else DEFAULT_SITUATION_SEED_PATH
    try:
        raw = yaml.safe_load(seed_path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise SituationSeedError(f"씨드 파일을 읽을 수 없음: {seed_path} — {exc}") from exc
    except yaml.YAMLError as exc:
        raise SituationSeedError(f"씨드 파일 YAML 오류: {seed_path} — {exc}") from exc
    try:
        return SituationSeedFile.model_validate(raw)
    except ValidationError as exc:
        raise SituationSeedError(f"씨드 파일 계약 위반: {seed_path}\n{exc}") from exc


def save_situation_seeds(seed_file: SituationSeedFile, path: str | Path | None = None) -> None:
    """검증된 씨드 파일을 YAML 원천에 되쓴다 — 헤더 주석 보존, 원자적 교체.

    웹 편집기(/v1/situation-seeds)의 유일한 저장 경로다. 본문(seeds 항목 옆) 주석은
    기계 재작성 때 유지되지 않는다 — 설명은 헤더 주석이나 seed_id에 담을 것.
    """
    seed_path = Path(path) if path is not None else DEFAULT_SITUATION_SEED_PATH
    header_lines: list[str] = []
    if seed_path.exists():
        for line in seed_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("#") or not line.strip():
                header_lines.append(line)
            else:
                break
    body = yaml.safe_dump(
        seed_file.model_dump(mode="json", exclude_none=True),
        allow_unicode=True, sort_keys=False, width=100,
    )
    text = ("\n".join(header_lines) + "\n" if header_lines else "") + body
    tmp = seed_path.with_suffix(".yaml.tmp")
    tmp.write_text(text, encoding="utf-8")
    tmp.replace(seed_path)


def pick_variants(
    seed_file: SituationSeedFile, *, domain: str, k: int, salt: str
) -> list[dict[str, Any]]:
    """도메인 후보 씨드에서 변형 k개를 결정론으로 고른다(같은 salt → 같은 결과).

    후보가 k보다 적으면 순환 재사용한다 — 수동 값을 그대로 존중하고, 임의 변형을 만들지 않는다.
    반환은 build_scenarios 입력 형태(dict)이며, 최종 검증·적재는 §1-S5 유일문이 맡는다.
    """
    candidates = sorted(
        (s for s in seed_file.seeds if not s.domains or domain in s.domains),
        key=lambda s: s.seed_id,
    )
    if not candidates:  # 로더가 도메인 공백을 거부하므로 외부 seed_file 직조립 시에만 도달
        raise SituationSeedError(f"도메인 {domain}에 후보 씨드가 없음")
    offset = int.from_bytes(hashlib.sha256(salt.encode("utf-8")).digest()[:8], "big")
    return [
        # exclude_none: vs-1.0은 명시적 null 금지(값이 없으면 키 생략) — §1-S5 재검증 통과 형태
        candidates[(offset + i) % len(candidates)].workspace_state.model_dump(
            mode="json", exclude_none=True
        )
        for i in range(k)
    ]
