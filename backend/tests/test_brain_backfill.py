"""T3.1 AC (§5-7): Seed Brain Backfill (S13).

- 노드 부트스트랩은 governance_event를 남긴다 (절대 규칙 4, 자동 INSERT 금지)
- exemplar는 GOLD+LABELED 에피소드만; 기존 exemplar와 임베딩 거리 ≥ exemplar_min_dist
- **분포 라벨(BRONZE/SILVER)은 exemplar 채택 안 됨 — evidence_stats에만 반영** (핵심 AC)
- adversarial=true evidence는 집계에서 분리 (절대 규칙 6)
- backfill은 brightness(heldout_accuracy 등)를 건드리지 않는다 (절대 규칙 3 — Arena 전용)
"""
import pytest
from sqlalchemy import delete, select

from app.brain.backfill import (
    aggregate_evidence_stats,
    bootstrap_nodes,
    run_backfill,
    select_exemplars,
)
from app.core.config import get_config
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.llm.base import EmbeddingRequest
from app.llm.mock import MockProvider
from app.models.arena import ArenaRun, KtibItem, KtibVersion
from app.models.brain import BrainNode, Exemplar
from app.models.episodes import Episode, Evidence
from app.models.governance import GovernanceEvent


@pytest.fixture(autouse=True)
def _empty_brain_bank(db_session):
    """이 모듈은 '빈 뱅크에서의 부트스트랩·집계'를 검증한다 — 실 DB에 노드·에피소드·evidence가
    영구 적재된 뒤에도 정확 카운트 전제를 유지하도록 세이브포인트 안에서 비운다(종료 시 롤백,
    실 데이터 무손상). aggregate_evidence_stats가 전체 Evidence를 훑으므로 Evidence·Episode도
    비워야 한다(FK 순서: evidence·exemplar → episode → node)."""
    # 실 KTIB(ktib_items)가 episodes를 FK로 잡는다 — 자식 먼저
    db_session.execute(delete(ArenaRun))
    db_session.execute(delete(KtibItem))
    db_session.execute(delete(KtibVersion))
    db_session.execute(delete(Evidence))
    db_session.execute(delete(Exemplar))
    db_session.execute(delete(Episode))
    db_session.execute(delete(BrainNode))
    db_session.flush()

CFG = get_config()


def _embed():
    p = MockProvider(embed_dim=1536)  # exemplars.embedding = vector(1536)

    def embed(texts):
        return p.embed(EmbeddingRequest(inputs=texts, model="e")).vectors

    return embed


def _episode(db, ep_id, intent, prompt, *, tier="GOLD", state="LABELED") -> None:
    db.add(Episode(
        episode_id=ep_id, ontology_version="onto-1.0", lang="ko", dataset_split="TRAIN",
        reliability_tier=tier, label_state=state, origin_channel="FOUNDRY_SYNTHETIC",
        episode_creator_type="FOUNDRY_PIPELINE", primary_subject_type="SIMULATED_TEACHER",
        teacher_prompt=prompt, label_distribution={intent: 1.0},
    ))


def _evidence(db, ev_id, ep_id, intent, etype, *, adversarial=False, polarity="supports") -> None:
    db.add(Evidence(
        evidence_id=ev_id, episode_id=ep_id, intent_id=intent, polarity=polarity,
        strength=0.8, evidence_type=etype, actor_type="LLM_ANALYST", adversarial=adversarial,
    ))


def _episode_dist(db, ep_id, dist, prompt, *, tier="GOLD", state="LABELED") -> None:
    """명시적 label_distribution(다중 intent) 에피소드."""
    db.add(Episode(
        episode_id=ep_id, ontology_version="onto-1.0", lang="ko", dataset_split="TRAIN",
        reliability_tier=tier, label_state=state, origin_channel="FOUNDRY_SYNTHETIC",
        episode_creator_type="FOUNDRY_PIPELINE", primary_subject_type="SIMULATED_TEACHER",
        teacher_prompt=prompt, label_distribution=dist,
    ))


def _real_intent(idx=0) -> str:
    reals = [i.intent_id for i in load_ontology().intents if i.intent_id != UNKNOWN_INTENT_ID]
    return reals[idx]


def _node(db, intent) -> BrainNode:
    return db.scalar(select(BrainNode).where(BrainNode.intent_id == intent))


# --- 노드 부트스트랩 (절대 규칙 4) ---


def test_bootstrap_creates_node_per_real_intent_with_governance(db_session) -> None:
    event_id = bootstrap_nodes(db_session, approved_by="lab")
    db_session.flush()
    reals = {i.intent_id for i in load_ontology().intents if i.intent_id != UNKNOWN_INTENT_ID}
    nodes = {n.intent_id for n in db_session.scalars(select(BrainNode))}
    assert nodes == reals
    assert UNKNOWN_INTENT_ID not in nodes  # UNKNOWN은 노드 아님
    # 절대 규칙 4: 모든 노드가 governance_event를 근거로 생성
    ev = db_session.get(GovernanceEvent, event_id)
    assert ev is not None and ev.event_type == "NODE_BOOTSTRAP"
    for n in db_session.scalars(select(BrainNode)):
        assert n.created_by_event == event_id
        assert n.node_id.startswith("N_")


def test_bootstrap_is_idempotent(db_session) -> None:
    bootstrap_nodes(db_session, approved_by="lab")
    db_session.flush()
    n1 = db_session.query(BrainNode).count()
    second = bootstrap_nodes(db_session, approved_by="lab")  # 재실행
    db_session.flush()
    assert second is None  # 만들 노드 없음
    assert db_session.query(BrainNode).count() == n1  # 중복 생성 0


def test_bootstrap_does_not_set_brightness(db_session) -> None:
    """절대 규칙 3: 노드 생성 시 heldout_accuracy 등은 Arena 전까지 NULL(Dormant)."""
    bootstrap_nodes(db_session, approved_by="lab")
    db_session.flush()
    for n in db_session.scalars(select(BrainNode)):
        assert n.heldout_accuracy is None
        assert n.calibration_ece is None
        assert n.last_arena_run is None


# --- exemplar 선정 (§5-7) + 핵심 AC ---


def test_distribution_labels_not_exemplar_only_evidence_stats(db_session) -> None:
    """핵심 AC: BRONZE/SILVER는 exemplar로 채택 안 되고 evidence_stats에만 반영."""
    intent = _real_intent(0)
    bootstrap_nodes(db_session, approved_by="lab")
    _episode(db_session, "EP_GOLD", intent, "확정 골드 발화", tier="GOLD", state="LABELED")
    _episode(db_session, "EP_BRONZE", intent, "분포 브론즈 발화", tier="BRONZE",
             state="LABEL_CANDIDATE")
    # AC는 BRONZE와 SILVER 둘 다 명시 — SILVER(LABELED여도)도 exemplar 아님
    _episode(db_session, "EP_SILVER", intent, "분포 실버 발화", tier="SILVER", state="LABELED")
    _evidence(db_session, "EV_G", "EP_GOLD", intent, "SYNTHETIC_CONSENSUS")
    _evidence(db_session, "EV_B", "EP_BRONZE", intent, "SYNTHETIC_CONSENSUS")
    _evidence(db_session, "EV_S", "EP_SILVER", intent, "SYNTHETIC_CONSENSUS")
    db_session.flush()

    select_exemplars(db_session, CFG, _embed())
    aggregate_evidence_stats(db_session)
    db_session.flush()

    ex_eps = {e.episode_id for e in db_session.scalars(select(Exemplar))}
    assert "EP_GOLD" in ex_eps         # GOLD만 exemplar
    assert "EP_BRONZE" not in ex_eps   # 분포 라벨(BRONZE)은 exemplar 아님
    assert "EP_SILVER" not in ex_eps   # 분포 라벨(SILVER)도 exemplar 아님
    node = _node(db_session, intent)
    # 셋 다 evidence_stats에는 반영 (synthetic 3건)
    assert node.evidence_stats["synthetic"] >= 3
    assert node.evidence_stats["gold"] == 1  # GOLD 에피소드 1건


def test_exemplar_dedup_by_min_dist(db_session) -> None:
    """같은 발화(임베딩 거리 0 < min_dist)는 중복 exemplar로 채택되지 않는다."""
    intent = _real_intent(1)
    bootstrap_nodes(db_session, approved_by="lab")
    _episode(db_session, "EP_A", intent, "완전히 동일한 발화")
    _episode(db_session, "EP_B", intent, "완전히 동일한 발화")  # 동일 → 임베딩 동일
    _episode(db_session, "EP_C", intent, "전혀 다른 발화입니다")  # 다름 → 채택
    db_session.flush()
    select_exemplars(db_session, CFG, _embed())
    db_session.flush()
    picked = {e.episode_id for e in db_session.scalars(
        select(Exemplar).where(Exemplar.intent_id == intent))}
    assert len(picked) == 2  # 동일 발화 중 하나는 dedup
    assert "EP_C" in picked


def test_exemplar_selection_idempotent(db_session) -> None:
    intent = _real_intent(2)
    bootstrap_nodes(db_session, approved_by="lab")
    _episode(db_session, "EP_X", intent, "골드 발화 하나")
    db_session.flush()
    select_exemplars(db_session, CFG, _embed())
    db_session.flush()
    n1 = db_session.query(Exemplar).count()
    select_exemplars(db_session, CFG, _embed())  # 재실행
    db_session.flush()
    assert db_session.query(Exemplar).count() == n1  # 중복 exemplar 0


def test_exemplar_stats_written(db_session) -> None:
    intent = _real_intent(3)
    bootstrap_nodes(db_session, approved_by="lab")
    _episode(db_session, "EP_S1", intent, "발화 첫째")
    _episode(db_session, "EP_S2", intent, "발화 둘째 다른 것")
    db_session.flush()
    select_exemplars(db_session, CFG, _embed())
    db_session.flush()
    node = _node(db_session, intent)
    assert node.exemplar_stats["count"] == 2
    assert node.exemplar_stats["index"] == "exemplars"
    # diversity = 평균 쌍-코사인거리 ∈ [0,2] (cos_sim ∈ [-1,1]). 실 임베딩은 대개 <1.
    assert 0.0 <= node.exemplar_stats["diversity"] <= 2.0


# --- evidence_stats (절대 규칙 6) ---


def test_adversarial_evidence_excluded(db_session) -> None:
    """절대 규칙 6: adversarial evidence는 집계에서 분리."""
    intent = _real_intent(4)
    bootstrap_nodes(db_session, approved_by="lab")
    _episode(db_session, "EP_ADV", intent, "적대 발화", tier="BRONZE", state="LABEL_CANDIDATE")
    _evidence(db_session, "EV_NAT", "EP_ADV", intent, "SYNTHETIC_CONSENSUS", adversarial=False)
    _evidence(db_session, "EV_ADV", "EP_ADV", intent, "SYNTHETIC_CONSENSUS", adversarial=True)
    db_session.flush()
    aggregate_evidence_stats(db_session)
    db_session.flush()
    node = _node(db_session, intent)
    assert node.evidence_stats["synthetic"] == 1  # 자연 1건만, adversarial 제외


def test_evidence_type_buckets(db_session) -> None:
    intent = _real_intent(5)
    bootstrap_nodes(db_session, approved_by="lab")
    _episode(db_session, "EP_T", intent, "타입 발화", tier="BRONZE", state="LABEL_CANDIDATE")
    _evidence(db_session, "EV1", "EP_T", intent, "SYNTHETIC_CONSENSUS")
    _evidence(db_session, "EV2", "EP_T", intent, "WEAK_BEHAVIORAL")
    _evidence(db_session, "EV3", "EP_T", intent, "EXPERT_REVIEW")
    db_session.flush()
    aggregate_evidence_stats(db_session)
    db_session.flush()
    stats = _node(db_session, intent).evidence_stats
    assert stats["synthetic"] == 1
    assert stats["weak_behavioral"] == 1
    assert stats["expert"] == 1


# --- run_backfill 통합 + 규칙 3 ---


def test_run_backfill_end_to_end_and_no_brightness(db_session) -> None:
    intent = _real_intent(6)
    _episode(db_session, "EP_E2E", intent, "통합 골드 발화")
    _evidence(db_session, "EV_E2E", "EP_E2E", intent, "SYNTHETIC_CONSENSUS")
    db_session.flush()
    report = run_backfill(db_session, CFG, approved_by="lab", embed_fn=_embed())
    db_session.flush()
    assert report.nodes_created > 0
    assert report.exemplars_selected >= 1
    node = _node(db_session, intent)
    assert node.exemplar_stats["count"] >= 1
    assert node.evidence_stats["synthetic"] >= 1
    # 절대 규칙 3: backfill은 어떤 노드의 brightness도 바꾸지 않는다
    assert all(n.heldout_accuracy is None for n in db_session.scalars(select(BrainNode)))


# --- 리뷰 회귀 (adversarial 워크플로 findings) ---


def test_refutes_evidence_not_counted_in_support_stats(db_session) -> None:
    """F1: refutes(해당 intent에 반대) evidence는 노드의 support 버킷에 들어가면 안 된다."""
    intent = _real_intent(7)
    bootstrap_nodes(db_session, approved_by="lab")
    _episode(db_session, "EP_POL", intent, "polarity 발화", tier="BRONZE", state="LABEL_CANDIDATE")
    _evidence(db_session, "EV_SUP", "EP_POL", intent, "SYNTHETIC_CONSENSUS", polarity="supports")
    _evidence(db_session, "EV_REF", "EP_POL", intent, "SYNTHETIC_CONSENSUS", polarity="refutes")
    db_session.flush()
    aggregate_evidence_stats(db_session)
    db_session.flush()
    assert _node(db_session, intent).evidence_stats["synthetic"] == 1  # supports만


def test_multi_intent_exemplar_attributed_to_top(db_session) -> None:
    """F3: 다중 분포 GOLD는 top(최대 가중) intent 노드에만 exemplar 귀속."""
    a, b = _real_intent(8), _real_intent(9)
    bootstrap_nodes(db_session, approved_by="lab")
    _episode_dist(db_session, "EP_MULTI", {a: 0.6, b: 0.4}, "다중 분포 발화")
    db_session.flush()
    select_exemplars(db_session, CFG, _embed())
    db_session.flush()
    exs = list(db_session.scalars(select(Exemplar).where(Exemplar.episode_id == "EP_MULTI")))
    assert len(exs) == 1
    assert exs[0].intent_id == a and exs[0].node_id == "N_" + a  # top(0.6)에만, b에는 없음


def test_exemplar_skipped_when_top_intent_has_no_node(db_session) -> None:
    """F3: top intent에 노드가 없으면(부트스트랩 전) exemplar 채택을 스킵한다(가드)."""
    intent = _real_intent(10)
    _episode(db_session, "EP_NONODE", intent, "노드 없는 발화")  # 노드 부트스트랩 안 함
    db_session.flush()
    selected = select_exemplars(db_session, CFG, _embed())
    db_session.flush()
    assert selected == 0
    assert db_session.query(Exemplar).count() == 0
