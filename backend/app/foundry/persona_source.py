"""Gym 상호작용 → Persona 행동 벡터 입력 (§4-1 [2]).

`foundry.persona`는 `Interaction` 목록을 받아 클러스터링하지만, **DB에서 그 목록을 만드는
어댑터가 없었다** — 그래서 Persona Discovery는 코드가 있어도 실행할 수 없는 상태였다.

## 무엇을 상호작용으로 세는가

트레이너가 Gym에서 남긴 **human evidence**다(§8-1 "세션 산출은 전부 §3-1 evidence로 적재된다").
`evidence` 한 행이 상호작용 한 건이다:

| evidence_type | action |
|---|---|
| `HUMAN_CORRECTION` | correction |
| `HUMAN_CONFIRMATION` | confirmation |
| 그 밖(전문가 검토 등) | selection |

## 배제 규칙

- **`adversarial=true`는 제외한다** (절대 규칙 6). Break the Brain(§8-1)의 스트레스 표본으로
  교사 성향을 추정하면, 그건 성향이 아니라 그 교사가 뇌를 어떻게 괴롭혔는지를 잰 것이다.
- `trainer_ref`가 없는 evidence는 제외한다 — 누구의 행동인지 모르는 것은 행동 벡터가 못 된다.
- 사람이 아닌 actor(`LLM_ANALYST`·`RULE_ENGINE`·`BEHAVIOR_SIGNAL`)는 제외한다. persona는
  **교사의** 성향이다.
- 온톨로지에 domain이 없는 intent(UNKNOWN 등)는 domain 편향에 기여하지 못하므로 드롭한다 —
  region을 추측하지 않는다.

`min_interactions`(config) 미만인 트레이너는 벡터를 만들지 않는다. 상호작용 두세 건으로 성향을
주장하면 그 prior가 추론을 오염시킨다(§5-5 cap이 있어도 방향은 틀린다).
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import ExperimentsConfig
from app.core.ontology import load_ontology
from app.foundry.persona import Interaction
from app.models.episodes import Evidence

# persona는 '교사의' 성향이다 — 사람 트레이너 actor만 센다 (§4-1)
TRAINER_ACTORS = ("TEACHER_TRAINER", "STAFF_TRAINER")

_ACTION_BY_EVIDENCE = {
    "HUMAN_CORRECTION": "correction",
    "HUMAN_CONFIRMATION": "confirmation",
}
_DEFAULT_ACTION = "selection"


def load_interactions(session: Session) -> list[Interaction]:
    """자연 분포의 사람 트레이너 상호작용 (adversarial 제외, §8-1·절대 규칙 6).

    `evidence_id` 오름차순 — 클러스터링 재현성의 전제(HDBSCAN은 입력 순서에 민감하다).
    """
    domains = {i.intent_id: i.domain for i in load_ontology().intents}
    rows = session.scalars(
        select(Evidence)
        .where(
            Evidence.actor_type.in_(TRAINER_ACTORS),
            Evidence.trainer_ref.isnot(None),
            Evidence.adversarial.is_(False),  # 절대 규칙 6
        )
        .order_by(Evidence.evidence_id)
    ).all()

    interactions: list[Interaction] = []
    for row in rows:
        domain = domains.get(row.intent_id)
        if domain is None:
            continue  # UNKNOWN·온톨로지 밖 — domain을 추측하지 않는다
        interactions.append(Interaction(
            trainer_ref=row.trainer_ref,
            domain=domain,
            action=_ACTION_BY_EVIDENCE.get(row.evidence_type, _DEFAULT_ACTION),
            intent_id=row.intent_id,
        ))
    return interactions


def eligible_interactions(
    interactions: list[Interaction], config: ExperimentsConfig
) -> tuple[list[Interaction], dict[str, int]]:
    """`persona.min_interactions` 이상 남긴 트레이너의 상호작용만.

    `(걸러진 상호작용, 트레이너별 건수)`를 반환한다.
    표본이 얇은 트레이너를 클러스터에 넣으면 그 클러스터의 prior가 소음이 된다.
    """
    counts: dict[str, int] = {}
    for it in interactions:
        counts[it.trainer_ref] = counts.get(it.trainer_ref, 0) + 1
    floor = config.persona.min_interactions
    keep = {ref for ref, n in counts.items() if n >= floor}
    return [it for it in interactions if it.trainer_ref in keep], counts
