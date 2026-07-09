"""Challenge Pack + 플레이 아이템 (§6-4·§7-4·§8-1).

강화하기(§7-4) → ChallengePack(메타) + 아이템(온톨로지 positive_examples에서 발화 추출).
아이템 발화를 온톨로지 시드에서 뽑으므로 에피소드 뱅크가 비어 있어도 세션이 돌아간다
(GYM_HUMAN 에피소드는 submit 시 생성 — session.py). Pack 생성은 governance 대상 아님(노드 아님).
"""
from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from app.contracts.challenge_pack import ChallengePack as ChallengePackContract
from app.core.config import ExperimentsConfig
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.models.gym import ChallengePack

# 진단(§7-3 mock 포함) → 강화 전략(§6-1). 미지 진단은 B(human evidence)로 안전 폴백.
_STRATEGY_BY_DIAGNOSIS: dict[str, str] = {
    "CONFUSION_HIGH": "C_CONFUSION",
    "AMBIGUOUS_LANGUAGE_HIGH": "C_CONFUSION",
    "GOLD_LOW": "B_HUMAN_EVIDENCE",
    "PERSONA_DIVERSITY_LOW": "B_HUMAN_EVIDENCE",
    "COVERAGE_LOW": "A_DATA_COVERAGE",
    "PERFORMANCE_DROP": "D_MODEL",
}
# 이 티켓의 3모드 (§8-1 배달 계층)
GYM_MODES = ["guess_my_intent", "choose_right_meaning", "correction_drill"]


def build_pack(
    session: Session,
    *,
    trigger: str,
    node: str,
    region: str | None,
    diagnosis: list[str] | None,
    target_confusion: str | None,
    config: ExperimentsConfig,
) -> ChallengePack:
    """§7-4 강화하기 결과 ChallengePack을 만들어 적재한다. 계약으로 형태를 검증 후 ORM 저장."""
    strategy = sorted(
        {_STRATEGY_BY_DIAGNOSIS.get(d, "B_HUMAN_EVIDENCE") for d in (diagnosis or [])}
    ) or ["B_HUMAN_EVIDENCE"]
    target_edges = (
        [{"from_true": node, "to_predicted": target_confusion}] if target_confusion else None
    )
    pack_id = "CP_" + uuid.uuid4().hex[:12]

    # 계약상 null 불가 필드(origin.diagnosis·target_edges)는 값이 없으면 키를 생략한다 —
    # 명시 None은 _reject_explicit_null이 거부(→ 미처리 시 500). region/node는 nullable.
    origin: dict = {"trigger": trigger, "node": node, "region": region}
    if diagnosis is not None:
        origin["diagnosis"] = diagnosis
    kwargs = dict(
        pack_id=pack_id,
        origin=origin,
        strategy=strategy,
        items=config.growth.default_pack_items,
        difficulty_curve="medium_to_hard",
        persona_mix=[f"persona_{i}" for i in range(1, 6)],
        delivery_modes=GYM_MODES,
        expected_yield={"human_evidence_per_item": 1},
    )
    if target_edges is not None:
        kwargs["target_edges"] = target_edges
    contract = ChallengePackContract(**kwargs)
    row = ChallengePack(
        pack_id=contract.pack_id,
        # exclude_none: diagnosis/region이 None이면 키 자체를 빼 저장 — 저장값이 PackOrigin
        # 계약을 다시 통과(_reject_explicit_null이 명시 null을 거부하므로 landmine 방지)
        origin=contract.origin.model_dump(exclude_none=True),
        strategy=contract.strategy,
        target_edges=(
            [e.model_dump() for e in contract.target_edges] if contract.target_edges else None
        ),
        items=contract.items,
        difficulty_curve=contract.difficulty_curve,
        persona_mix=contract.persona_mix,
        delivery_modes=contract.delivery_modes,
        expected_yield=contract.expected_yield,
    )
    session.add(row)
    session.flush()
    return row


def build_items(
    *,
    node_intent: str,
    mode: str,
    config: ExperimentsConfig,
    ontology=None,
) -> list[dict]:
    """플레이 아이템 — 노드 intent와 혼동 상대의 온톨로지 발화(positive_examples)로 구성.

    각 아이템: 발화 + 후보 intent 목록 + true_intent(교정드릴 브레인 오답 세팅용, 온톨로지 정답).
    trainer가 고른 답이 evidence가 되지 true_intent가 자동 라벨이 되지 않는다(§8-1).
    """
    onto = ontology or load_ontology()
    by_id = {i.intent_id: i for i in onto.intents}
    node = by_id.get(node_intent)
    if node is None or node.intent_id == UNKNOWN_INTENT_ID:
        return []

    # 후보: 노드 + 혼동 상대(없으면 같은 domain의 다른 intent로 보강)
    confusables = [c for c in node.confusable_with if c in by_id][:3]
    if not confusables:
        confusables = [
            i.intent_id for i in onto.intents
            if i.domain == node.domain and i.intent_id != node_intent
        ][:2]
    candidates = [node_intent, *confusables]

    n = config.gym.session_items
    examples = node.positive_examples
    items: list[dict] = []
    for k in range(min(n, len(examples))):
        # correction_drill: 브레인이 혼동 상대로 오답했다고 제시 → 트레이너가 node로 교정
        brain_guess = (
            confusables[k % len(confusables)]
            if (mode == "correction_drill" and confusables) else None
        )
        items.append({
            "item_id": f"GI_{k}",
            "utterance": examples[k],
            "true_intent": node_intent,
            "candidate_intents": candidates,
            "brain_guess": brain_guess,
        })
    return items
