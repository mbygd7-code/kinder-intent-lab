"""Intent Ontology 로더 (§5-9: domain → intent 2계층 — 의미 구조의 유일한 권한).

- seeds/ontology_v1.yaml이 원천
- UNKNOWN intent는 domain을 갖지 않는다 (미분류 pool, §5-8)
- 여기서 brain_nodes를 만들지 않는다 (절대 규칙 4) — ontology_versions 기록만
"""
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.core.config import ExperimentsConfig, get_config
from app.models.governance import OntologyVersion

# onto-2.0 (마스터 문서 v1.5, §5-10 v2): STUDIO(자료 만들기) 신설 — 8번째가 마지막 원소.
# 순서는 프론트 regions.ts·3D 좌표계와 1:1이므로 재배열 금지.
CANONICAL_DOMAINS = (
    "PLAY", "OBSERVATION", "DOCUMENT", "VISUAL", "COMMUNICATION", "OPERATION", "REFLECTION",
    "STUDIO",
)
UNKNOWN_INTENT_ID = "UNKNOWN"

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_SEED_PATH = _REPO_ROOT / "seeds" / "ontology_v1.yaml"


class OntologyIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intent_id: str = Field(min_length=1)
    domain: str | None
    definition: str = Field(min_length=1)
    positive_examples: list[str] = Field(min_length=1)
    negative_examples: list[str] = Field(min_length=1)
    confusable_with: list[str] = []


class Ontology(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    version: str = Field(min_length=1)
    change_type: Literal["major", "minor"]
    domains: list[str]
    intents: list[OntologyIntent]

    @model_validator(mode="after")
    def _structural(self) -> "Ontology":
        if tuple(self.domains) != CANONICAL_DOMAINS:
            raise ValueError("domains는 정본 도메인 집합·순서여야 한다 (§5-9·§5-10)")

        ids = [i.intent_id for i in self.intents]
        dups = sorted({x for x in ids if ids.count(x) > 1})
        if dups:
            raise ValueError(f"중복 intent_id: {dups}")

        id_set = set(ids)
        if UNKNOWN_INTENT_ID not in id_set:
            raise ValueError("UNKNOWN intent 필수 (§5-8 미분류 pool)")

        for intent in self.intents:
            if intent.intent_id == UNKNOWN_INTENT_ID:
                if intent.domain is not None:
                    raise ValueError("UNKNOWN은 domain을 갖지 않는다")
            elif intent.domain not in self.domains:
                raise ValueError(f"{intent.intent_id}: 미정의 domain {intent.domain!r}")
            for ref in intent.confusable_with:
                if ref == intent.intent_id:
                    raise ValueError(f"{intent.intent_id}: 자기 참조 혼동")
                if ref not in id_set:
                    raise ValueError(f"{intent.intent_id}: 존재하지 않는 혼동 참조 {ref!r}")
        return self


def load_ontology(path: Path | None = None) -> Ontology:
    """시드 yaml을 읽어 구조 검증 후 반환."""
    target = path or DEFAULT_SEED_PATH
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    return Ontology.model_validate(data)


def validate_seed_quality(ontology: Ontology, config: ExperimentsConfig | None = None) -> None:
    """시드 수용 기준 — 임계값은 전부 config (절대 규칙 1)."""
    cfg = (config or get_config()).ontology
    real = [i for i in ontology.intents if i.intent_id != UNKNOWN_INTENT_ID]

    if len(real) < cfg.min_intents:
        raise ValueError(f"intent {len(real)}개 < ontology.min_intents({cfg.min_intents})")

    missing = set(CANONICAL_DOMAINS) - {i.domain for i in real}
    if missing:
        raise ValueError(f"도메인 커버리지 누락: {sorted(missing)}")

    for intent in real:
        if (
            len(intent.positive_examples) < cfg.min_examples_per_side
            or len(intent.negative_examples) < cfg.min_examples_per_side
        ):
            raise ValueError(
                f"{intent.intent_id}: 예시 부족 "
                f"(min_examples_per_side={cfg.min_examples_per_side})"
            )


def register_ontology(session: Session, ontology: Ontology) -> OntologyVersion:
    """ontology_versions에 버전 기록 (멱등). 노드 생성은 하지 않는다 (절대 규칙 4)."""
    existing = session.get(OntologyVersion, ontology.version)
    if existing is not None:
        return existing
    row = OntologyVersion(
        version=ontology.version, change_type=ontology.change_type, migration_map=None
    )
    session.add(row)
    session.flush()
    return row
