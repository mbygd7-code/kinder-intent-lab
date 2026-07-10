"""Risk Model 로더 — intent별 평가 위험 등급 (rm-1.x, 2026-07-10 확정).

`seeds/risk_model_v1.yaml`이 원천. **온톨로지가 아니라 여기에 두는 이유:**

- 위험 등급은 intent의 *의미*가 아니라 *평가 정책*이다. 의미 구조의 권한은 온톨로지에만 있다(§5-9).
- `arena_runs.ontology_version`은 replay 무결성 축이다(§8-2). 위험 등급을 온톨로지에 두면 등급을
  고칠 때마다 ontology_version이 올라가고, intent 집합·정의가 하나도 안 바뀌었는데도 과거 모든
  arena run이 "다른 온톨로지"가 되어 같은 축에서 비교할 수 없게 된다.
- 실제로 `OntologyIntent`는 `extra="forbid"`라 risk 필드를 받지 않는다.

**소비처는 `config.arena.critical_intents` 하나다.** 이 시드의 CRITICAL 집합과 config가 어긋나면
`scripts/validate_schemas.py`가 loud-fail한다 — 빈 목록으로 §6-6의 critical 절과 CWAR를 조용히
무력화하는 경로를 물리적으로 차단하기 위해서다.

위험 판정 원칙(감사 채택): **egress 경계에서 게이트하고, 그 하위 egress를 통해서만 비가역 피해가
실현되는 내부 변이는 이중 게이트하지 않는다.** 이중 게이트는 CWAR를 희석시킨다.
"""
from functools import lru_cache
from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, model_validator
from sqlalchemy.orm import Session

from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.models.governance import GovernanceEvent

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_RISK_MODEL_PATH = _REPO_ROOT / "seeds" / "risk_model_v1.yaml"

RISK_MODEL_EVENT = "RISK_MODEL_UPDATE"  # governance_events.event_type (자유 Text — enum 없음)

Tier = Literal["CRITICAL", "ELEVATED", "STANDARD"]
Axis = Literal["E", "D", "R"]


class RiskAxis(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    id: Axis
    name: str = Field(min_length=1)
    question: str = Field(min_length=1)


class RiskIntent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    intent_id: str = Field(min_length=1)
    tier: Tier
    axis: Axis | None  # CRITICAL이면 필수, 아니면 null
    rationale: str = Field(min_length=1)

    @model_validator(mode="after")
    def _critical_needs_axis(self) -> "RiskIntent":
        if self.tier == "CRITICAL" and self.axis is None:
            raise ValueError(f"{self.intent_id}: CRITICAL은 위험 축(E/D/R)을 명시해야 한다")
        if self.tier != "CRITICAL" and self.axis is not None:
            raise ValueError(f"{self.intent_id}: CRITICAL이 아닌 intent에 축을 달지 않는다")
        return self


class RiskModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    risk_model_version: str = Field(pattern=r"^rm-")
    axes: list[RiskAxis] = Field(min_length=1)
    tiers: list[Tier] = Field(min_length=1)
    intents: list[RiskIntent] = Field(min_length=1)

    @model_validator(mode="after")
    def _structural(self) -> "RiskModel":
        ids = [i.intent_id for i in self.intents]
        dups = sorted({x for x in ids if ids.count(x) > 1})
        if dups:
            raise ValueError(f"중복 intent_id: {dups}")

        # 유령 intent 금지 — 온톨로지에 실재하는 intent만 등급을 받는다
        real = {i.intent_id for i in load_ontology().intents if i.intent_id != UNKNOWN_INTENT_ID}
        ghosts = sorted(set(ids) - real)
        if ghosts:
            raise ValueError(f"온톨로지에 없는 intent: {ghosts}")

        declared = {a.id for a in self.axes}
        used = {i.axis for i in self.intents if i.axis is not None}
        if not used <= declared:
            raise ValueError(f"선언되지 않은 축 사용: {sorted(used - declared)}")
        return self

    @property
    def critical_intents(self) -> list[str]:
        """CWAR·§6-6 게이트 대상. 정렬된 목록 — config와의 비교가 순서에 흔들리지 않게."""
        return sorted(i.intent_id for i in self.intents if i.tier == "CRITICAL")

    def tier_of(self, intent_id: str) -> Tier:
        """등급표에 없는 intent는 STANDARD다 (되돌릴 수 있는 국소·생성적 제안)."""
        for i in self.intents:
            if i.intent_id == intent_id:
                return i.tier
        return "STANDARD"


def load_risk_model(path: Path | None = None) -> RiskModel:
    target = path or DEFAULT_RISK_MODEL_PATH
    return RiskModel.model_validate(yaml.safe_load(target.read_text(encoding="utf-8")))


@lru_cache(maxsize=1)
def get_risk_model() -> RiskModel:
    """전역 단일 접근점 — 프로세스당 1회 로드·검증 후 캐시 (load_ontology 관례)."""
    return load_risk_model()


def assert_config_coherence(critical_intents: list[str], model: RiskModel | None = None) -> None:
    """config.arena.critical_intents ↔ risk model CRITICAL 집합 정합 (drift 차단).

    어긋나면 loud-fail한다 — config만 비우면 §6-6 critical 절과 CWAR가 조용히 무력화된다.
    """
    rm = model or get_risk_model()
    expected, actual = rm.critical_intents, sorted(critical_intents)
    if expected != actual:
        raise ValueError(
            f"critical_intents 불일치: config={actual} != {rm.risk_model_version}={expected}"
        )


def record_risk_model_update(
    session: Session, *, approved_by: str, model: RiskModel | None = None
) -> GovernanceEvent:
    """위험 등급 지정·개정을 거버넌스 이벤트로 남긴다 (원칙 9의 정신 — 정책 변경은 승인 흔적).

    최초 지정(빈 목록 → 7종)은 promote 거동을 바꾼다: 이전에 통과하던 candidate가 critical 회귀로
    새로 차단될 수 있다(의도된 안전 강화). 그래서 승인 흔적이 선행해야 한다.
    """
    rm = model or get_risk_model()
    event = GovernanceEvent(
        event_id=f"GOV_RM_{rm.risk_model_version.replace('.', '_')}",
        event_type=RISK_MODEL_EVENT,
        payload={
            "risk_model_version": rm.risk_model_version,
            "critical_intents": rm.critical_intents,
            "axes": [a.id for a in rm.axes],
        },
        approved_by=approved_by,
    )
    session.add(event)
    session.flush()
    return event
