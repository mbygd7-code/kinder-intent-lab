"""T4.2 Challenge Pack 생성기 (§6-1·§6-3·§6-4).

Observatory에서 어두운 노드를 클릭하면: 진단(§7-3 실계산) → 강화 전략(§6-1 A/B/C/D, 복합) →
우선순위 target_edges(§6-3) → Challenge Pack(§6-4). A형(Data Coverage)은 사람 세션 없이
Foundry 작업 큐(foundry_work_queue)로 발행된다(§6-1 '사람 필요=아니오').

진단 코드는 서버가 실계산한다(프론트 입력 미신뢰) — §7-3 4축 + confusion_edges에서:
  COVERAGE_LOW            ← screen_context_coverage.level == LOW
  GOLD_LOW               ← gold_data.value < growth.gold_low_threshold  (B형 발동 기준)
  PERSONA_DIVERSITY_LOW  ← persona_diversity.level == LOW
  AMBIGUOUS_LANGUAGE_HIGH ← ambiguous_language.level == HIGH
  CONFUSION_HIGH         ← 노드발 edge 중 confusion_rate ≥ growth.confusion_trigger

전략 매핑(§6-1): A_DATA_COVERAGE / B_HUMAN_EVIDENCE / C_CONFUSION / D_MODEL. 복합 진단이면 조합.
모든 임계·우선순위 가중치는 config(절대 규칙 1). 이 모듈은 brightness에 접근하지 않는다(규칙 3).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.brain.diagnosis import NodeDiagnosis, diagnose_node
from app.contracts.challenge_pack import ChallengePack as ChallengePackContract
from app.core.config import ExperimentsConfig
from app.core.ontology import load_ontology
from app.models.brain import BrainNode, ConfusionEdge
from app.models.foundry import FoundryWorkOrder
from app.models.gym import ChallengePack
from app.models.persona import PersonaCluster

# evidence_stats 버킷(§5-1 계약 구조 상수 — 실험 임계값 아님). evidence 총량(size) 원천.
_EVIDENCE_BUCKETS = ("synthetic", "weak_behavioral", "human_confirmed", "gold", "expert")

# 진단 코드 → 강화 전략(§6-1). 미지 진단은 B(human evidence)로 안전 폴백.
STRATEGY_BY_DIAGNOSIS: dict[str, str] = {
    "COVERAGE_LOW": "A_DATA_COVERAGE",
    "GOLD_LOW": "B_HUMAN_EVIDENCE",
    "PERSONA_DIVERSITY_LOW": "B_HUMAN_EVIDENCE",
    "AMBIGUOUS_LANGUAGE_HIGH": "C_CONFUSION",
    "CONFUSION_HIGH": "C_CONFUSION",
    "PERFORMANCE_DROP": "D_MODEL",
}


# --- 우선순위 샘플링 (§6-3) ---


@dataclass
class NodeSignals:
    """§6-3 훈련 우선순위 순위 신호. 값은 [0,1]로 정규화된 축(높을수록 약함/시급)."""

    heldout: float | None        # ① heldout 정확도 (None=미측정=Dormant → 최우선 취급)
    confusion_rate: float | None # ② 최고 confusion edge rate (None/없음=0)
    performance_drop: float | None  # ③ 최근 하락폭 (None=0)
    evidence_ratio: float        # ④ evidence_total / 최대치 (0..1; 낮을수록 시급)
    persona_entropy: float | None   # ⑤ persona 다양성 엔트로피 (None=중립 0.5; 낮을수록 시급)
    service_importance: float    # ⑥ 서비스 중요도 (0..1)


def priority_score(sig: NodeSignals, config: ExperimentsConfig) -> float:
    """§6-3 순위 신호를 config 가중치로 합산 — 클수록 우선 훈련 대상.

    각 신호를 '시급도(높을수록 약함)'로 변환한다: heldout↓·evidence↓·persona↓ = 시급.
    미측정 heldout(Dormant)은 시급도 1.0(최우선) — 어두운 노드가 검증 대상이라는 §7-6 취지.
    """
    w = config.growth.priority_weights
    heldout_low = (1.0 - sig.heldout) if sig.heldout is not None else 1.0
    confusion = sig.confusion_rate or 0.0
    drop = sig.performance_drop or 0.0
    evidence_low = 1.0 - max(0.0, min(1.0, sig.evidence_ratio))
    persona_low = (1.0 - sig.persona_entropy) if sig.persona_entropy is not None else 0.5
    return (
        w.heldout_low * heldout_low
        + w.confusion_high * confusion
        + w.performance_drop * drop
        + w.evidence_low * evidence_low
        + w.persona_impact * persona_low
        + w.service_importance * sig.service_importance
    )


def rank_target_edges(
    edges: list[ConfusionEdge], config: ExperimentsConfig
) -> list[ConfusionEdge]:
    """C형 target: confusion_rate ≥ trigger인 edge를 rate 내림차순(§6-3 ②). rate None은 제외."""
    trigger = config.growth.confusion_trigger
    hot = [e for e in edges if e.confusion_rate is not None and e.confusion_rate >= trigger]
    return sorted(hot, key=lambda e: e.confusion_rate, reverse=True)


def _node_priority(
    session: Session,
    node_intent: str,
    dg: NodeDiagnosis,
    ranked: list[ConfusionEdge],
    config: ExperimentsConfig,
) -> float:
    """§6-3 순위 신호를 노드 실데이터에서 뽑아 priority_score로 합산 — 이 pack의 훈련 우선순위.

    heldout은 §6-3 ①이 명시적으로 요구하는 읽기 입력이다(읽기 전용; 절대 규칙 3은 brightness의
    '갱신'만 금지하며 여기선 쓰지 않는다). evidence_ratio는 노드 evidence 총량 / 최대 노드 총량.
    persona ⑤는 다양성 결핍(낮은 엔트로피)을 §7-3 약점 축과 정합하게 시급도로 본다(데이터측 프록시).
    """
    nodes = list(session.scalars(select(BrainNode)))
    totals: dict[str, int] = {}
    heldout: float | None = None
    for n in nodes:
        stats = n.evidence_stats or {}
        totals[n.intent_id] = sum(int(stats.get(b, 0) or 0) for b in _EVIDENCE_BUCKETS)
        if n.intent_id == node_intent:
            heldout = n.heldout_accuracy
    max_total = max(totals.values(), default=0)
    evidence_ratio = (totals.get(node_intent, 0) / max_total) if max_total else 0.0
    sig = NodeSignals(
        heldout=heldout,
        confusion_rate=(ranked[0].confusion_rate if ranked else None),
        performance_drop=None,   # 성능 하락 이력은 Arena 여러 회전 뒤에나 생김(T4.6) — 지금은 없음
        evidence_ratio=evidence_ratio,
        persona_entropy=dg.persona_diversity.value,
        service_importance=0.5,  # 서비스 중요도 데이터 없음 → 중립 (스케일 중앙값)
    )
    return round(priority_score(sig, config), 4)


# --- 진단 → 전략 ---


def derive_diagnosis_codes(
    dg: NodeDiagnosis, edges: list[ConfusionEdge], config: ExperimentsConfig
) -> list[str]:
    """§7-3 4축 + confusion_edges에서 진단 코드를 실계산한다(축 검사 순서대로 append).

    데이터 없는 축(level None)은 코드를 내지 않는다 — 없음 ≠ LOW(정직성). GOLD는 절대량
    < growth.gold_low_threshold를 B형 발동 기준으로 쓴다(패널 표시 버킷 diagnosis.gold_low와 별개).
    반환 순서는 이 함수의 검사 순서이며 계약 enum 순서와 무관하다 — 소비처는 순서에 의존하지 않는다
    (strategies_for는 set+정렬, delivery_modes/난이도는 membership).
    """
    codes: list[str] = []
    if dg.screen_context_coverage.level == "LOW":
        codes.append("COVERAGE_LOW")
    if (dg.gold_data.value or 0) < config.growth.gold_low_threshold:
        codes.append("GOLD_LOW")
    if dg.persona_diversity.level == "LOW":
        codes.append("PERSONA_DIVERSITY_LOW")
    if dg.ambiguous_language.level == "HIGH":
        codes.append("AMBIGUOUS_LANGUAGE_HIGH")
    if rank_target_edges(edges, config):
        codes.append("CONFUSION_HIGH")
    return codes


def strategies_for(codes: list[str]) -> list[str]:
    """진단 코드 집합 → 전략 집합(정렬·중복 제거). 코드 없으면 B로 폴백(사람 검증은 언제나 유효)."""
    strat = sorted({STRATEGY_BY_DIAGNOSIS[c] for c in codes if c in STRATEGY_BY_DIAGNOSIS})
    return strat or ["B_HUMAN_EVIDENCE"]


def delivery_modes_for(strategies: list[str], codes: list[str]) -> list[str]:
    """전략 → Gym 배달 모드(§6-4·§8-1). A/D형만이면 사람 배달 없음([]) — 사람 세션 불필요."""
    modes: list[str] = []
    if "B_HUMAN_EVIDENCE" in strategies:
        modes.append("choose_right_meaning")
    if "C_CONFUSION" in strategies:
        modes.append("correction_drill")
    if "PERSONA_DIVERSITY_LOW" in codes:
        modes.append("persona_contrast")
    seen: set[str] = set()
    return [m for m in modes if not (m in seen or seen.add(m))]


def _difficulty(codes: list[str]) -> str:
    """혼동·모호가 있으면 hard, 아니면 medium_to_hard (§6-4 difficulty_curve)."""
    if "CONFUSION_HIGH" in codes or "AMBIGUOUS_LANGUAGE_HIGH" in codes:
        return "hard"
    return "medium_to_hard"


def _persona_mix(session: Session) -> list[str] | None:
    """persona_clusters에서 상위 클러스터 id (member_count desc). 없으면 None(키 생략)."""
    clusters = session.scalars(
        select(PersonaCluster.cluster_id)
        .order_by(PersonaCluster.member_count.desc().nullslast())
        .limit(5)
    ).all()
    return list(clusters) or None


# --- pack 직렬화(스키마·API 공용) ---


def pack_to_dict(row: ChallengePack) -> dict:
    """저장된 ChallengePack을 challenge_pack.schema.json 형태 dict로 — null 필드는 생략."""
    out: dict = {
        "pack_id": row.pack_id,
        "origin": row.origin,
        "strategy": row.strategy,
        "items": row.items,
        "delivery_modes": row.delivery_modes,
    }
    if row.target_edges is not None:
        out["target_edges"] = row.target_edges
    if row.difficulty_curve is not None:
        out["difficulty_curve"] = row.difficulty_curve
    if row.persona_mix is not None:
        out["persona_mix"] = row.persona_mix
    if row.expected_yield is not None:
        out["expected_yield"] = row.expected_yield
    return out


# --- 생성 ---


@dataclass
class GeneratedPack:
    pack: ChallengePack
    diagnosis_codes: list[str]
    work_orders: list[FoundryWorkOrder]
    needs_human: bool
    node_priority: float   # §6-3 훈련 우선순위 점수 (클수록 시급)


def generate_pack(
    session: Session,
    *,
    node_intent: str,
    trigger: str,
    config: ExperimentsConfig,
    ontology=None,
) -> GeneratedPack:
    """노드 진단 → 전략 → target_edges → Challenge Pack. A형이면 Foundry 작업 큐로 발행.

    호출자(엔드포인트)가 node_intent의 온톨로지 유효성(404)을 먼저 검증한다고 가정한다.
    """
    onto = ontology or load_ontology()
    by_id = {i.intent_id: i for i in onto.intents}
    node = by_id.get(node_intent)
    region = node.domain if node else None

    dg = diagnose_node(session, node_intent, config)
    edges = list(
        session.scalars(select(ConfusionEdge).where(ConfusionEdge.from_true == node_intent))
    )
    ranked = rank_target_edges(edges, config)
    codes = derive_diagnosis_codes(dg, edges, config)
    strategy = strategies_for(codes)
    modes = delivery_modes_for(strategy, codes)
    needs_human = bool(modes)

    target_edges = (
        [{"from_true": e.from_true, "to_predicted": e.to_predicted} for e in ranked]
        if ranked else None
    )
    items = config.growth.default_pack_items
    priority = _node_priority(session, node_intent, dg, ranked, config)

    # §6-3 우선순위 점수를 pack에 기록 — 스케줄러/큐가 여러 pack을 견줄 때의 정렬 키.
    expected_yield: dict = {"node_priority": priority}
    if needs_human:
        expected_yield["human_evidence"] = items
    if "CONFUSION_HIGH" in codes:
        expected_yield["contrast_pairs"] = sum(len(e.contrast_exemplars or []) for e in ranked)

    persona_mix = _persona_mix(session)
    pack_id = "CP_" + uuid.uuid4().hex[:12]

    # 계약상 null 불가 필드(origin.diagnosis·target_edges·persona_mix 등)는 값 없으면 키를 생략
    # (_reject_explicit_null이 명시 None을 거부 → 미처리 시 500). node/region은 nullable.
    origin: dict = {"trigger": trigger, "node": node_intent, "region": region}
    if codes:
        origin["diagnosis"] = codes
    kwargs: dict = dict(
        pack_id=pack_id, origin=origin, strategy=strategy, items=items,
        difficulty_curve=_difficulty(codes), delivery_modes=modes,
    )
    if target_edges is not None:
        kwargs["target_edges"] = target_edges
    if persona_mix is not None:
        kwargs["persona_mix"] = persona_mix
    contract = ChallengePackContract(**kwargs)

    row = ChallengePack(
        pack_id=contract.pack_id,
        origin=contract.origin.model_dump(exclude_none=True),
        strategy=contract.strategy,
        target_edges=(
            [e.model_dump() for e in contract.target_edges] if contract.target_edges else None
        ),
        items=contract.items,
        difficulty_curve=contract.difficulty_curve,
        persona_mix=contract.persona_mix,
        delivery_modes=contract.delivery_modes,
        expected_yield=expected_yield or None,
    )
    session.add(row)
    session.flush()  # pack_id 먼저 — 작업주문이 FK로 참조

    # A형(Data Coverage): 사람 세션 없이 Foundry 시나리오 생성 주문을 큐에 발행 (§6-1)
    work_orders: list[FoundryWorkOrder] = []
    if "A_DATA_COVERAGE" in strategy:
        order = FoundryWorkOrder(
            order_id="FWO_" + uuid.uuid4().hex[:12],
            intent_id=node_intent, region=region, order_type="SCENARIO_COVERAGE",
            status="PENDING", requested_items=config.growth.coverage_order_items,
            strategy=strategy, diagnosis=codes or None, pack_id=row.pack_id,
            payload={"reason": "COVERAGE_LOW", "coverage_value": dg.screen_context_coverage.value},
        )
        session.add(order)
        work_orders.append(order)
    if work_orders:
        expected_yield_update = dict(row.expected_yield or {})
        expected_yield_update["coverage_orders"] = len(work_orders)
        row.expected_yield = expected_yield_update
    session.flush()

    return GeneratedPack(
        pack=row, diagnosis_codes=codes, work_orders=work_orders,
        needs_human=needs_human, node_priority=priority,
    )
