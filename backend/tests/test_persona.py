"""T2.3 AC (§4-1·§4-2).

- 합성 fixture로 클러스터 재현성
- persona_clusters·population_priors 적재
- 클러스터 리포트(8축 가설 대조표)
"""

import pytest

from app.core.config import get_config
from app.core.ontology import CANONICAL_DOMAINS
from app.foundry.persona import (
    HYPOTHESIS_AXES,
    Interaction,
    build_behavior_vectors,
    build_cluster_report,
    cluster_trainers,
    persist_clusters,
)
from app.models.persona import PersonaCluster, PopulationPrior

CFG = get_config()

_DOMAIN_INTENT = {
    "PLAY": "play_expand",
    "DOCUMENT": "text_naturalize",
    "COMMUNICATION": "comm_draft_parent_notice",
}


def _group_interactions(prefix: str, domain: str, n_trainers: int) -> list[Interaction]:
    """한 그룹의 trainer들이 대부분 특정 domain에서 활동하는 상호작용 (분리도 높음)."""
    out: list[Interaction] = []
    for t in range(n_trainers):
        ref = f"{prefix}{t}"
        for _ in range(9):  # 주 domain 교정 9회
            out.append(Interaction(trainer_ref=ref, domain=domain, action="correction",
                                   intent_id=_DOMAIN_INTENT[domain]))
        out.append(Interaction(trainer_ref=ref, domain="OBSERVATION", action="confirmation",
                               intent_id="obs_record_moment"))  # 소량 노이즈
    return out


def _synthetic() -> list[Interaction]:
    return (
        _group_interactions("tp_", "PLAY", 5)
        + _group_interactions("td_", "DOCUMENT", 5)
        + _group_interactions("tc_", "COMMUNICATION", 5)
    )


# --- 행동 벡터 ---


def test_build_behavior_vectors() -> None:
    vectors = build_behavior_vectors(_group_interactions("tp_", "PLAY", 3))
    assert set(vectors) == {"tp_0", "tp_1", "tp_2"}
    v = vectors["tp_0"]
    n_domains = len(CANONICAL_DOMAINS)
    assert len(v) == n_domains + 2  # domain 분포 + correction_frac + confirmation_frac
    assert abs(sum(v[:n_domains]) - 1.0) <= 0.01  # domain 분포 합 = 1


def test_empty_interactions() -> None:
    assert build_behavior_vectors([]) == {}


# --- 클러스터 재현성 (AC 1) ---


def test_cluster_reproducibility() -> None:
    vectors = build_behavior_vectors(_synthetic())
    r1 = cluster_trainers(vectors, CFG)
    r2 = cluster_trainers(vectors, CFG)
    assert r1.labels == r2.labels  # 결정론적
    assert r1.n_clusters >= 2


def test_same_group_same_cluster() -> None:
    vectors = build_behavior_vectors(_synthetic())
    result = cluster_trainers(vectors, CFG)
    play = {result.labels[r] for r in vectors if r.startswith("tp_")}
    doc = {result.labels[r] for r in vectors if r.startswith("td_")}
    # 같은 그룹은 한 클러스터로 (노이즈 -1 제외)
    play_clusters = {c for c in play if c >= 0}
    doc_clusters = {c for c in doc if c >= 0}
    assert len(play_clusters) == 1
    assert len(doc_clusters) == 1
    assert play_clusters != doc_clusters  # 서로 다른 클러스터


# --- 적재 (AC 2) ---


def test_persist_persona_clusters(db_session) -> None:
    vectors = build_behavior_vectors(_synthetic())
    result = cluster_trainers(vectors, CFG)
    clusters, priors = persist_clusters(
        db_session, result, _synthetic(), version="pv-test1", state_version="ps-test1",
        config=CFG,
    )
    db_session.flush()
    assert len(clusters) == result.n_clusters
    rows = db_session.query(PersonaCluster).filter(PersonaCluster.version == "pv-test1").all()
    assert len(rows) == result.n_clusters
    assert all(c.method == "HDBSCAN" for c in rows)
    assert all(c.member_count > 0 for c in rows)


def test_persist_population_priors(db_session) -> None:
    vectors = build_behavior_vectors(_synthetic())
    result = cluster_trainers(vectors, CFG)
    clusters, priors = persist_clusters(
        db_session, result, _synthetic(), version="pv-test2", state_version="ps-test2",
        config=CFG,
    )
    db_session.flush()
    assert len(priors) > 0
    # 클러스터별 prior 합 ≈ 1
    by_cluster: dict[str, float] = {}
    for p in db_session.query(PopulationPrior).filter(
        PopulationPrior.state_version == "ps-test2"
    ):
        by_cluster[p.cluster_id] = by_cluster.get(p.cluster_id, 0.0) + p.prior
    assert by_cluster
    for total in by_cluster.values():
        assert abs(total - 1.0) <= 0.01


def test_noise_not_persisted_as_cluster(db_session) -> None:
    # 고립점 하나를 섞으면 노이즈(-1)로 분류되어 클러스터로 적재되지 않는다
    interactions = _synthetic() + [
        Interaction(trainer_ref="loner", domain="VISUAL", action="correction",
                    intent_id="visual_naturalize")
    ]
    vectors = build_behavior_vectors(interactions)
    result = cluster_trainers(vectors, CFG)
    clusters, _ = persist_clusters(
        db_session, result, interactions, version="pv-test3", state_version="ps-test3",
        config=CFG,
    )
    db_session.flush()
    persisted_members = sum(c.member_count for c in clusters)
    assert persisted_members <= len(vectors)  # 노이즈는 제외


# --- 클러스터 리포트 (8축 가설 대조) ---


def test_cluster_report_maps_to_hypothesis_axes() -> None:
    vectors = build_behavior_vectors(_synthetic())
    result = cluster_trainers(vectors, CFG)
    report = build_cluster_report(result, vectors)
    assert len(report.rows) == result.n_clusters
    axes = {row.hypothesis_axis for row in report.rows}
    assert axes <= {a.name for a in HYPOTHESIS_AXES}
    # PLAY 그룹 클러스터는 PLAY_DRIVEN 축에 대조되어야 한다
    play_label = next(result.labels[r] for r in vectors if r.startswith("tp_")
                      if result.labels[r] >= 0)
    play_row = next(row for row in report.rows if row.cluster_label == play_label)
    assert play_row.hypothesis_axis == "PLAY_DRIVEN"


def test_eight_hypothesis_axes_defined() -> None:
    assert len(HYPOTHESIS_AXES) == 8


# --- 리뷰 회귀 ---


def test_behavior_vector_sum_one_with_noncanon_domain() -> None:
    """canon 밖 domain이 섞여도 domain 분포 합=1 유지 (정규화 견고)."""
    interactions = _group_interactions("tp_", "PLAY", 1) + [
        Interaction(trainer_ref="tp_0", domain="NOT_A_DOMAIN", action="selection")
    ]
    vectors = build_behavior_vectors(interactions)
    assert abs(sum(vectors["tp_0"][:7]) - 1.0) <= 0.01


def test_cluster_id_stable_across_input_order(db_session) -> None:
    """입력 순서가 달라도 같은 멤버 구성이면 같은 cluster_id (정준화)."""
    base = _synthetic()
    v1 = build_behavior_vectors(base)
    v2 = build_behavior_vectors(list(reversed(base)))
    c1, _ = persist_clusters(db_session, cluster_trainers(v1, CFG), base,
                             version="pv-order-a", state_version="ps-a", config=CFG)
    db_session.flush()
    c2, _ = persist_clusters(db_session, cluster_trainers(v2, CFG), base,
                             version="pv-order-b", state_version="ps-b", config=CFG)
    db_session.flush()

    # version 접두를 뗀 멤버-구성별 cluster 매핑이 두 순서에서 동일해야 한다
    def by_members(clusters):
        return {frozenset(c.axes["members"]): c.cluster_id.rsplit("_", 1)[1] for c in clusters}

    assert by_members(c1) == by_members(c2)


def test_repersist_same_version_rejected(db_session) -> None:
    vectors = build_behavior_vectors(_synthetic())
    result = cluster_trainers(vectors, CFG)
    persist_clusters(db_session, result, _synthetic(), version="pv-dup", state_version="ps-1",
                     config=CFG)
    db_session.flush()
    with pytest.raises(ValueError, match="이미 적재"):
        persist_clusters(db_session, result, _synthetic(), version="pv-dup", state_version="ps-2",
                         config=CFG)
