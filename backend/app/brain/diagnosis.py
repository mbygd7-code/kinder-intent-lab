"""Weakness Diagnosis Engine — 4축 실계산 (§7-3, T4.1).

§7-3 표의 계산 정의와 1:1:
| 축 | 계산 | 원천 |
| Ambiguous Language | intent가 든 Atlas 패턴들의 평균 경쟁 intent 수 | Atlas possible_intents |
| Screen Context Coverage | 노드 episode들의 workspace 조합 커버리지 | S5 변형축 |
| Persona Diversity | 노드 episode의 persona 분포 엔트로피 | Episode(§3-1) |
| Gold Data | GOLD evidence 절대량 | Episode Bank(§3-3) |

값이 계산 불가(데이터 없음)면 None — 지어내지 않는다(정보 정직성). 레벨 버킷(HIGH/MED/LOW)
임계는 config.diagnosis에만 있다(절대 규칙 1). 이 엔진은 brightness를 건드리지 않는다(규칙 3).
"""
from __future__ import annotations

import math
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import ExperimentsConfig
from app.core.datasets import is_training_gold
from app.models.episodes import Episode
from app.models.foundry import AtlasEntry, CanonicalScenario

Level = str  # "HIGH" | "MED" | "LOW"


@dataclass
class Axis:
    value: float | None      # 원값 (§7-3 계산). None = 데이터 없음(계산 불가)
    level: Level | None      # config.diagnosis 임계로 버킷. value None이면 None


@dataclass
class NodeDiagnosis:
    intent_id: str
    ambiguous_language: Axis
    screen_context_coverage: Axis
    persona_diversity: Axis
    gold_data: Axis


def _level(value: float | None, low: float, high: float) -> Level | None:
    if value is None:
        return None
    if value >= high:
        return "HIGH"
    if value >= low:
        return "MED"
    return "LOW"


def _norm_entropy(counts: list[int]) -> float:
    """정규화 섀넌 엔트로피 [0,1]. 종류 1개 이하면 0."""
    total = sum(counts)
    live = [c for c in counts if c > 0]
    if total <= 0 or len(live) <= 1:
        return 0.0
    entropy = -sum((c / total) * math.log(c / total) for c in live)
    return entropy / math.log(len(live))


def _node_episodes(session: Session, intent_id: str) -> list[Episode]:
    """이 노드에 귀속되는 에피소드 — label_distribution 최상위 intent가 이 intent."""
    rows = session.scalars(
        select(Episode).where(Episode.label_distribution.has_key(intent_id))
    )
    def _top(dist: dict) -> str:
        return max(dist, key=dist.get)

    return [e for e in rows if e.label_distribution and _top(e.label_distribution) == intent_id]


def _ambiguous_language(session: Session, intent_id: str) -> float | None:
    """이 intent가 possible_intents에 든 Atlas 패턴들의 평균 경쟁 intent 수(자신 제외)."""
    rows = session.scalars(
        select(AtlasEntry.possible_intents).where(
            AtlasEntry.possible_intents.contains([intent_id])
        )
    ).all()
    competitors = [max(0, len(pi) - 1) for pi in rows if pi and intent_id in pi]
    if not competitors:
        return None
    return sum(competitors) / len(competitors)


def _screen_context_coverage(session: Session, node_eps: list[Episode]) -> float | None:
    """노드 에피소드가 커버한 S5 변형축 / 전체 변형축 수. 노드가 시나리오에 안 붙었으면 None."""
    node_scenarios = [e.scenario_id for e in node_eps if e.scenario_id]
    if not node_scenarios:
        return None
    total_axes = session.scalar(
        select(func.count(func.distinct(CanonicalScenario.variation_axis)))
        .where(CanonicalScenario.variation_axis.isnot(None))
    )
    if not total_axes:
        return None
    covered = session.scalars(
        select(CanonicalScenario.variation_axis).where(
            CanonicalScenario.scenario_id.in_(node_scenarios),
            CanonicalScenario.variation_axis.isnot(None),
        )
    ).all()
    return len(set(covered)) / total_axes


def _persona_diversity(node_eps: list[Episode]) -> float | None:
    personas = [e.persona_lens_used for e in node_eps if e.persona_lens_used]
    if not personas:
        return None
    counts: dict[str, int] = {}
    for p in personas:
        counts[p] = counts.get(p, 0) + 1
    return _norm_entropy(list(counts.values()))


def _gold_count(node_eps: list[Episode]) -> int:
    """GOLD_LOW 축의 표본 — 벤치마크 에피소드는 학습 자산이 아니므로 세지 않는다(§8-2)."""
    return sum(1 for e in node_eps if is_training_gold(e))


def diagnose_node(
    session: Session, intent_id: str, config: ExperimentsConfig
) -> NodeDiagnosis:
    d = config.diagnosis
    node_eps = _node_episodes(session, intent_id)

    amb = _ambiguous_language(session, intent_id)
    cov = _screen_context_coverage(session, node_eps)
    per = _persona_diversity(node_eps)
    gold = float(_gold_count(node_eps))  # 절대량은 항상 계산 가능(0 포함)

    return NodeDiagnosis(
        intent_id=intent_id,
        ambiguous_language=Axis(
            amb, _level(amb, d.ambiguous_competitors_low, d.ambiguous_competitors_high)
        ),
        screen_context_coverage=Axis(
            cov, _level(cov, d.screen_coverage_low, d.screen_coverage_high)
        ),
        persona_diversity=Axis(
            per, _level(per, d.persona_entropy_low, d.persona_entropy_high)
        ),
        gold_data=Axis(gold, _level(gold, d.gold_low, d.gold_high)),
    )


def diagnose_all(
    session: Session, intent_ids: list[str], config: ExperimentsConfig
) -> dict[str, NodeDiagnosis]:
    """노드별 4축 배치 계산."""
    return {i: diagnose_node(session, i, config) for i in intent_ids}
