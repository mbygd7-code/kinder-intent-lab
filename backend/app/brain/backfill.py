"""S13 Seed Brain Backfill — 노드 부트스트랩 + exemplar 선정 + evidence_stats 집계 (§5-7).

규칙:
- 노드 생성은 governance_events 승인 플로우로만(절대 규칙 4) — 자동 INSERT 금지.
- exemplar는 GOLD+LABELED 에피소드만; label_distribution 상위 intent에 귀속하되 기존 exemplar와
  임베딩 거리 ≥ config.brain.exemplar_min_dist (중복으로 다양성 부풀리기 방지, §5-7).
- 분포 라벨(BRONZE/SILVER)은 evidence_stats에만 반영, exemplar 채택 금지.
- adversarial=true evidence는 집계에서 분리(절대 규칙 6).
- brightness(heldout_accuracy 등)는 절대 건드리지 않는다(절대 규칙 3) — Arena 전용.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import ExperimentsConfig
from app.core.datasets import training_gold
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.foundry.stages.s4_language_miner import cosine_similarity
from app.models.brain import BrainNode, Exemplar
from app.models.episodes import Episode, Evidence
from app.models.governance import GovernanceEvent

EmbedFn = Callable[[list[str]], list[list[float]]]

# evidence_type → evidence_stats 버킷(계약 EvidenceStats). DOMAIN_RULE은 이 5버킷에 대응이
# 없어 미집계. HUMAN_CORRECTION은 human_confirmed 버킷 — §6-5 "교정 20개가 들어오면 …
# 즉시 변하는 것: evidence 카운트·density"와 §6-7 [4](HUMAN_CORRECTION도 human evidence
# 20건에 포함)·[6](size↑)가 교정 evidence의 즉시 반영을 명시한다 (T4.3 리뷰 MAJOR).
_TYPE_BUCKET = {
    "SYNTHETIC_CONSENSUS": "synthetic",
    "WEAK_BEHAVIORAL": "weak_behavioral",
    "HUMAN_CONFIRMATION": "human_confirmed",
    "HUMAN_CORRECTION": "human_confirmed",
    "EXPERT_REVIEW": "expert",
}
_BUCKETS = ("synthetic", "weak_behavioral", "human_confirmed", "gold", "expert")


def _cosine_distance(a, b) -> float:
    return 1.0 - cosine_similarity(list(a), list(b))


# --- 노드 부트스트랩 (절대 규칙 4) ---


def bootstrap_nodes(
    session: Session, *, approved_by: str, ontology=None
) -> str | None:
    """ontology 실 intent마다 brain_node 생성 — governance_event 근거. 멱등(있으면 None)."""
    onto = ontology or load_ontology()
    real = [i for i in onto.intents if i.intent_id != UNKNOWN_INTENT_ID]
    existing = set(session.scalars(select(BrainNode.intent_id)))
    to_create = [i for i in real if i.intent_id not in existing]
    if not to_create:
        return None
    event_id = "GOV_" + uuid.uuid4().hex[:12]
    session.add(
        GovernanceEvent(
            event_id=event_id,
            event_type="NODE_BOOTSTRAP",
            payload={
                "intents": [i.intent_id for i in to_create],
                "ontology_version": onto.version,
            },
            approved_by=approved_by,
        )
    )
    session.flush()  # 이벤트 먼저 — 노드는 created_by_event로 이 이벤트를 근거로 삼는다
    for i in to_create:
        session.add(
            BrainNode(
                node_id="N_" + i.intent_id,
                intent_id=i.intent_id,
                region=i.domain,
                definition_ref=f"{onto.version}#{i.intent_id}",
                created_by_event=event_id,
                # pending_evaluation은 기본 False — §6-5 Pending Ring은 "훈련됨·검증 대기"라
                # 훈련 세션 종료가 켠다(§7-4). 미측정(Dormant)은 brightness NULL이 표현한다(§7-6).
            )
        )
    session.flush()
    return event_id


def sync_node_regions(
    session: Session, *, approved_by: str, ontology=None
) -> str | None:
    """온톨로지 domain과 어긋난 기존 노드의 region을 정렬 — governance_event 근거.

    온톨로지 major에서 intent가 region을 옮길 때(예: onto-2.0 B안
    visual_image_generate VISUAL→STUDIO)의 유일한 이동 경로다(절대 규칙 4의 이동판).
    intent_id·측정값(brightness 등)은 건드리지 않는다 — region과 definition_ref만.
    히스토리(episodes·과거 run)는 재작성하지 않는다. 멱등(어긋남 없으면 None).
    """
    onto = ontology or load_ontology()
    domain_of = {i.intent_id: i.domain for i in onto.intents if i.intent_id != UNKNOWN_INTENT_ID}
    moves = [
        (node, domain_of[node.intent_id])
        for node in session.scalars(select(BrainNode))
        if node.intent_id in domain_of and node.region != domain_of[node.intent_id]
    ]
    if not moves:
        return None
    event_id = "GOV_" + uuid.uuid4().hex[:12]
    session.add(
        GovernanceEvent(
            event_id=event_id,
            event_type="NODE_REGION_MOVE",
            payload={
                "moves": [
                    {"intent_id": n.intent_id, "from": n.region, "to": to}
                    for n, to in moves
                ],
                "ontology_version": onto.version,
            },
            approved_by=approved_by,
        )
    )
    session.flush()
    for node, to in moves:
        node.region = to
        node.definition_ref = f"{onto.version}#{node.intent_id}"
    session.flush()
    return event_id


# --- exemplar 선정 (§5-7) ---


def _diversity(vecs: list[list[float]]) -> float:
    """exemplar 집합의 평균 쌍거리(1−cos). 2개 미만이면 0."""
    n = len(vecs)
    if n < 2:
        return 0.0
    total = 0.0
    pairs = 0
    for i in range(n):
        for j in range(i + 1, n):
            total += _cosine_distance(vecs[i], vecs[j])
            pairs += 1
    return round(total / pairs, 4) if pairs else 0.0


def select_exemplars(session: Session, config: ExperimentsConfig, embed_fn: EmbedFn) -> int:
    """GOLD+LABELED에서 exemplar 선정(dedup ≥ exemplar_min_dist). exemplar_stats 갱신. 멱등."""
    min_dist = config.brain.exemplar_min_dist
    nodes = {n.intent_id: n for n in session.scalars(select(BrainNode))}

    existing_vecs: dict[str, list[list[float]]] = {intent: [] for intent in nodes}
    existing_eps: set[str] = set()
    for ex in session.scalars(select(Exemplar)):
        existing_vecs.setdefault(ex.intent_id, []).append(list(ex.embedding))
        existing_eps.add(ex.episode_id)

    # ORDER BY로 처리 순서를 고정 — dedup 시 어느 near-중복이 남는지 재현 가능하게(멱등·결정론)
    # §8-2: BENCHMARK_HOLDOUT은 학습 파이프라인이 접근할 수 없다 — exemplar로 뽑으면 Arena
    # 점수가 '암기'의 측정치가 된다.
    golds = session.execute(
        select(Episode.episode_id, Episode.teacher_prompt, Episode.label_distribution)
        .where(training_gold())
        .order_by(Episode.episode_id)
    ).all()

    selected = 0
    for ep_id, prompt, dist in golds:
        if ep_id in existing_eps or not dist:
            continue
        top = max(dist, key=dist.get)
        if top == UNKNOWN_INTENT_ID or top not in nodes:
            continue
        vec = embed_fn([prompt])[0]
        # 기존 exemplar와 너무 가까우면(거리 < min_dist) 채택하지 않는다(다양성 부풀리기 방지)
        if any(_cosine_distance(vec, v) < min_dist for v in existing_vecs[top]):
            continue
        session.add(
            Exemplar(
                exemplar_id="EX_" + uuid.uuid4().hex[:12],
                node_id=nodes[top].node_id,
                intent_id=top,
                episode_id=ep_id,
                embedding=vec,
            )
        )
        existing_vecs[top].append(vec)
        existing_eps.add(ep_id)
        selected += 1
    session.flush()

    for intent, node in nodes.items():
        vecs = existing_vecs.get(intent, [])
        node.exemplar_stats = {
            "count": len(vecs),
            "index": "exemplars",
            "diversity": _diversity(vecs),
        }
    session.flush()
    return selected


# --- evidence_stats 집계 (절대 규칙 6) ---


def aggregate_evidence_stats(session: Session) -> None:
    """노드의 지지 evidence를 타입별로 카운트 + GOLD 에피소드 수 → evidence_stats.

    polarity='supports'만 집계한다 — refutes(해당 intent에 반대)는 노드 자신의 근거가 아니라
    혼동 상대에 대한 대비(§5-2 counter-exemplars 소관)이므로 support 통계를 부풀리면 안 된다.
    adversarial=true는 자연 분포 집계에서 분리한다(절대 규칙 6).
    """
    nodes = {n.intent_id: n for n in session.scalars(select(BrainNode))}
    buckets: dict[str, dict[str, int]] = {
        intent: dict.fromkeys(_BUCKETS, 0) for intent in nodes
    }

    rows = session.execute(
        select(Evidence.intent_id, Evidence.evidence_type, func.count())
        .where(Evidence.adversarial.is_(False), Evidence.polarity == "supports")
        .group_by(Evidence.intent_id, Evidence.evidence_type)
    ).all()
    for intent, etype, cnt in rows:
        bucket = _TYPE_BUCKET.get(etype)
        if intent in buckets and bucket:
            buckets[intent][bucket] += int(cnt)

    for (dist,) in session.execute(
        select(Episode.label_distribution).where(training_gold())  # §8-2 벤치마크 제외
    ).all():
        if dist:
            top = max(dist, key=dist.get)
            if top in buckets:
                buckets[top]["gold"] += 1

    for intent, node in nodes.items():
        node.evidence_stats = buckets[intent]
    session.flush()


# --- 오케스트레이션 ---


@dataclass
class BackfillReport:
    nodes_created: int
    exemplars_selected: int


def run_backfill(
    session: Session, config: ExperimentsConfig, *, approved_by: str, embed_fn: EmbedFn
) -> BackfillReport:
    """S13: 노드 부트스트랩 → exemplar 선정 → evidence_stats 집계."""
    before = session.query(BrainNode).count()
    bootstrap_nodes(session, approved_by=approved_by)
    nodes_created = session.query(BrainNode).count() - before
    selected = select_exemplars(session, config, embed_fn)
    aggregate_evidence_stats(session)
    return BackfillReport(nodes_created=nodes_created, exemplars_selected=selected)
