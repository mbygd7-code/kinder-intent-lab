"""§4-1 [2] AC: Gym 상호작용 → Persona 행동 벡터 입력 어댑터.

- 사람 트레이너(TEACHER_TRAINER/STAFF_TRAINER) evidence만 상호작용으로 센다
- ★ 절대 규칙 6: adversarial=true(Break the Brain)는 자연 분포 성향 추정에서 제외
- trainer_ref 없는 evidence, domain 없는 intent는 드롭 (추측하지 않는다)
- `persona.min_interactions` 미만 트레이너는 클러스터링 입력에서 제외
- 순서 결정론(evidence_id 오름차순) — HDBSCAN 재현성의 전제
"""
import pytest
from sqlalchemy import delete

from app.core.config import get_config
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.foundry.persona import build_behavior_vectors
from app.foundry.persona_source import eligible_interactions, load_interactions
from app.models.arena import KtibItem, KtibVersion
from app.models.episodes import Episode, Evidence

CFG = get_config()


@pytest.fixture(autouse=True)
def _empty(db_session):
    # FK: ktib_items → episodes 이므로 KtibItem을 먼저 비운다(벤치마크 episode가 있으면 필수)
    db_session.execute(delete(KtibItem))
    db_session.execute(delete(KtibVersion))
    db_session.execute(delete(Evidence))
    db_session.execute(delete(Episode))
    db_session.flush()


def _intents(n=3):
    return [i.intent_id for i in load_ontology().intents if i.domain][:n]


def _episode(db, epid, intent):
    db.add(Episode(
        episode_id=epid, ontology_version="onto-1.0", lang="ko", dataset_split="TRAIN",
        reliability_tier="BRONZE", label_state="LABEL_CANDIDATE", origin_channel="GYM_HUMAN",
        episode_creator_type="GYM_SESSION", primary_subject_type="TEACHER",
        teacher_prompt=f"발화 {epid}", label_distribution={intent: 1.0},
    ))
    db.flush()


def _ev(db, evid, epid, intent, *, trainer="TR_a", actor="TEACHER_TRAINER",
        etype="HUMAN_CONFIRMATION", adversarial=False):
    db.add(Evidence(
        evidence_id=evid, episode_id=epid, intent_id=intent, polarity="supports",
        strength=0.9, evidence_type=etype, actor_type=actor, trainer_ref=trainer,
        adversarial=adversarial,
    ))
    db.flush()


def test_human_evidence_becomes_interaction(db_session) -> None:
    a = _intents()[0]
    _episode(db_session, "EP_0", a)
    _ev(db_session, "EV_0", "EP_0", a, etype="HUMAN_CORRECTION")
    _ev(db_session, "EV_1", "EP_0", a, etype="HUMAN_CONFIRMATION")

    its = load_interactions(db_session)
    assert [i.action for i in its] == ["correction", "confirmation"]
    assert all(i.trainer_ref == "TR_a" and i.intent_id == a for i in its)
    assert its[0].domain == {i.intent_id: i.domain for i in load_ontology().intents}[a]


def test_adversarial_evidence_excluded(db_session) -> None:
    """★ 절대 규칙 6: 스트레스 테스트 표본으로 교사 성향을 추정하지 않는다."""
    a = _intents()[0]
    _episode(db_session, "EP_0", a)
    _ev(db_session, "EV_nat", "EP_0", a, adversarial=False)
    _ev(db_session, "EV_adv", "EP_0", a, adversarial=True)

    its = load_interactions(db_session)
    assert len(its) == 1


@pytest.mark.parametrize("actor", ["LLM_ANALYST", "RULE_ENGINE", "BEHAVIOR_SIGNAL"])
def test_non_human_actors_excluded(db_session, actor) -> None:
    """persona는 *교사의* 성향이다 — 합성·규칙 엔진 evidence는 상호작용이 아니다."""
    a = _intents()[0]
    _episode(db_session, "EP_0", a)
    _ev(db_session, "EV_0", "EP_0", a, actor=actor, trainer=None)
    assert load_interactions(db_session) == []


def test_evidence_without_trainer_ref_excluded(db_session) -> None:
    a = _intents()[0]
    _episode(db_session, "EP_0", a)
    _ev(db_session, "EV_0", "EP_0", a, trainer=None)
    assert load_interactions(db_session) == []


def test_intent_without_domain_dropped(db_session) -> None:
    """UNKNOWN은 domain이 없다 — region을 추측하지 않는다."""
    a = _intents()[0]
    _episode(db_session, "EP_0", a)
    _ev(db_session, "EV_0", "EP_0", UNKNOWN_INTENT_ID)
    assert load_interactions(db_session) == []


def test_order_is_deterministic(db_session) -> None:
    """HDBSCAN은 입력 순서에 민감하다 — evidence_id 오름차순으로 고정."""
    a, b, _ = _intents()
    _episode(db_session, "EP_0", a)
    _ev(db_session, "EV_2", "EP_0", b)
    _ev(db_session, "EV_0", "EP_0", a)
    _ev(db_session, "EV_1", "EP_0", a)
    assert [i.intent_id for i in load_interactions(db_session)] == [a, a, b]


# --- 표본 하한 ---


def _many(db, trainer, n, intent, start=0):
    for k in range(n):
        _ev(db, f"EV_{trainer}_{start + k}", "EP_0", intent, trainer=trainer)


def test_thin_trainers_excluded_from_clustering(db_session) -> None:
    """★ 상호작용 두세 건으로 성향을 주장하면 그 prior가 추론을 오염시킨다."""
    a = _intents()[0]
    _episode(db_session, "EP_0", a)
    floor = CFG.persona.min_interactions
    _many(db_session, "TR_thick", floor, a)
    _many(db_session, "TR_thin", floor - 1, a)

    kept, counts = eligible_interactions(load_interactions(db_session), CFG)
    assert counts == {"TR_thick": floor, "TR_thin": floor - 1}
    assert {i.trainer_ref for i in kept} == {"TR_thick"}
    assert set(build_behavior_vectors(kept)) == {"TR_thick"}


def test_no_interactions_yields_empty_not_error(db_session) -> None:
    """트레이너가 없으면 빈 목록 — 성향을 지어내지 않는다."""
    assert load_interactions(db_session) == []
    kept, counts = eligible_interactions([], CFG)
    assert kept == [] and counts == {}


def test_report_lines_use_real_dataclass_fields() -> None:
    """★ 회귀: 러너가 ClusterReportRow의 없는 필드를 읽어 성공 시 무조건 AttributeError였다.

    러너와 이 테스트가 같은 `report_lines()`를 쓰므로 필드가 바뀌면 여기서 먼저 깨진다.
    """
    from app.foundry.persona import (
        DOMAINS,
        ClusterResult,
        build_cluster_report,
        report_lines,
    )

    refs = ["TR_a", "TR_b", "TR_c"]
    # 전원 첫 domain에 편향된 벡터 (domain 편향 7 + correction/confirmation 2)
    vectors = {r: [1.0] + [0.0] * (len(DOMAINS) - 1) + [0.0, 1.0] for r in refs}
    result = ClusterResult(labels=dict.fromkeys(refs, 0), n_clusters=1, order=refs)

    lines = report_lines(build_cluster_report(result, vectors))
    assert len(lines) == 1
    assert "cluster=0" in lines[0] and "n=3" in lines[0]
    assert f"dominant_domain={DOMAINS[0]}" in lines[0] and "axis=" in lines[0]
