"""Persona Lift / Harm — prior가 정확도를 올린/내린 정도 (§4-2·§5-5, 문서 ③ §4-3).

§4-2: "**Persona Lift**(persona 덕에 맞춘 비율)와 **Persona Harm**(persona 탓에 틀린 비율)을
항상 함께 측정. Harm > Lift인 클러스터는 prior 비활성화."

§5-5가 prior를 **LLM 밖에서** 곱하는 첫 번째 이유가 바로 "Persona Lift/Harm을 측정 가능"이다.
그 설계 덕에 여기서는 **LLM을 한 번도 다시 부르지 않는다**: run이 이미 만들어 둔 per-item
`activations`(prior 곱하기 전)를 클러스터 prior로 재정렬하기만 하면 된다.

**격리(§8-2):**
- 재정렬에 쓰는 prior는 **그 run에 stamp된** `persona_state_version`의 것이다. 오늘의 prior로
  과거 run을 다시 채점하면 replay가 무너진다.
- Arena는 persona_state를 **절대 변이하지 않는다.** Harm > Lift여도 `deactivate_recommended`
  플래그만 남긴다 — KTIB 수치가 추론 상태로 자동 역류하면 벤치마크 격리가 깨진다.
  실제 비활성화는 사람·거버넌스 소관이다.

**해석 주의(문서에도 명기):** KTIB 아이템에는 클러스터 귀속이 없다. 따라서 이 값은
"클러스터 c의 prior를 벤치마크 분포 **전체**에 적용했을 때의 순이득/손해"이지
"클러스터 c 교사의 실제 정확도"가 아니다.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import distinct, select
from sqlalchemy.orm import Session

from app.brain.inference import normalize_and_rank
from app.brain.priors import capped_prior_factor, get_population_priors
from app.core.config import ExperimentsConfig
from app.models.persona import PopulationPrior

_NEUTRAL_PRIOR = 0.5  # 구조 상수(=배수 1.0), 실험 임계값 아님 — inference._NEUTRAL_PRIOR와 동일


@dataclass(frozen=True)
class ItemActivation:
    """아이템 1건의 채점 재료. gold는 채점에만 쓰고 scorer 입력에 넣지 않는다(절대 규칙 5)."""

    gold_intent: str
    activations: dict[str, float]  # prior 곱하기 전


def _rerank_top(activations: dict[str, float], priors: dict[str, float], cap: float) -> str | None:
    """activation × capped prior 배수 → top-1. 후보가 없으면 None."""
    if not activations:
        return None
    reranked = {
        intent: act * capped_prior_factor(priors.get(intent, _NEUTRAL_PRIOR), cap)
        for intent, act in activations.items()
    }
    return normalize_and_rank(reranked).top_intent


def clusters_with_prior(session: Session, state_version: str) -> list[str]:
    """이 state_version에 population prior가 적재된 클러스터 (정렬 — 결정론)."""
    return sorted(session.scalars(
        select(distinct(PopulationPrior.cluster_id)).where(
            PopulationPrior.state_version == state_version
        )
    ).all())


def persona_lift_harm(
    session: Session,
    items: list[ItemActivation],
    state_version: str,
    config: ExperimentsConfig,
) -> dict | None:
    """클러스터별 Lift/Harm. 클러스터가 없으면 None (0%가 아니라 '측정 대상 없음').

    Lift(c) = |{neutral 오답 ∧ persona_c 정답}| / N   (persona 덕에 맞춘 비율, §4-2)
    Harm(c) = |{neutral 정답 ∧ persona_c 오답}| / N   (persona 탓에 틀린 비율, §4-2)
    예측이 뒤집히지 않은 아이템은 어느 쪽에도 세지 않는다.
    """
    if not items:
        return None
    clusters = clusters_with_prior(session, state_version)
    if not clusters:
        return None  # Persona Discovery 미실행 — 분포를 지어내지 않는다

    cap = config.brain.persona_prior_cap
    margin = config.gate.persona_harm_margin
    min_items = config.gate.persona_eval_min_items

    out: dict[str, dict] = {}
    for cluster in clusters:
        priors = get_population_priors(session, cluster, state_version=state_version).priors
        if not priors:
            continue  # 이 버전엔 prior가 없다 — 재정렬할 것이 없음
        lift = harm = 0
        for item in items:
            neutral = normalize_and_rank(dict(item.activations)).top_intent
            persona = _rerank_top(item.activations, priors, cap)
            if neutral == persona:
                continue  # prior가 예측을 바꾸지 못함 — lift도 harm도 아니다
            if neutral != item.gold_intent and persona == item.gold_intent:
                lift += 1
            elif neutral == item.gold_intent and persona != item.gold_intent:
                harm += 1
        n = len(items)
        net = (lift - harm) / n
        out[cluster] = {
            "lift": round(lift / n, 4),
            "harm": round(harm / n, 4),
            "net": round(net, 4),
            "n": n,
            "flips_lift": lift,
            "flips_harm": harm,
            # §4-2 "Harm > Lift인 클러스터는 prior 비활성화" — Arena는 **제안만** 한다(§8-2 격리)
            "deactivate_recommended": bool((harm - lift) / n > margin and n >= min_items),
            "sample_below_floor": n < min_items,
        }
    return out or None
