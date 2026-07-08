"""Persona Discovery — 행동 벡터화 → HDBSCAN 클러스터링 → 8축 가설 대조 (§4).

원칙(§4): 8축은 가설이다. 확정은 데이터가 한다. persona는 prior에만 작용한다(§4-2, T2.4).
여기서는 trainer 상호작용 → 행동 벡터 → 밀도 기반 클러스터 → persona_clusters·population_priors.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import ExperimentsConfig
from app.core.ontology import CANONICAL_DOMAINS
from app.models.persona import PersonaCluster, PopulationPrior

# 의미 구조의 유일한 권한은 ontology (§5-9) — 도메인 목록을 재선언하지 않고 참조
DOMAINS = CANONICAL_DOMAINS
_DOMAIN_INDEX = {d: i for i, d in enumerate(DOMAINS)}


@dataclass(frozen=True)
class Interaction:
    """Gym 세션의 trainer 상호작용 1건 (§4-1 [2])."""

    trainer_ref: str
    domain: str
    action: str  # correction | confirmation | selection
    intent_id: str | None = None


@dataclass(frozen=True)
class HypothesisAxis:
    """8축 가설 (§4). 확정이 아니라 클러스터 대조용 프로토타입."""

    name: str
    domain: str | None  # 대표 domain (BALANCED는 None)


# 8축 가설 — 7 domain 중심 + 균형형 (원 설계 8축이 문서에서 잘려 있어 도메인 기반 가설로 시드)
HYPOTHESIS_AXES: tuple[HypothesisAxis, ...] = (
    HypothesisAxis("PLAY_DRIVEN", "PLAY"),
    HypothesisAxis("OBSERVATION_DRIVEN", "OBSERVATION"),
    HypothesisAxis("DOCUMENTATION_DRIVEN", "DOCUMENT"),
    HypothesisAxis("VISUAL_DRIVEN", "VISUAL"),
    HypothesisAxis("COMMUNICATION_DRIVEN", "COMMUNICATION"),
    HypothesisAxis("OPERATION_DRIVEN", "OPERATION"),
    HypothesisAxis("REFLECTION_DRIVEN", "REFLECTION"),
    HypothesisAxis("BALANCED", None),
)


def build_behavior_vectors(interactions: list[Interaction]) -> dict[str, list[float]]:
    """trainer × (domain 편향 7 + correction/confirmation 비율 2) 행동 벡터.

    v1 한계: §4-1 [3]은 (intent 선택 편향, 교정 '방향', 응답 선호)를 규정하나, 이 구현은
    intent→domain로 성기게(coarsen), 교정 '방향'을 correction '빈도'(스칼라)로 근사한 1차
    축소판이다. persona_vector v2에서 intent-레벨·방향으로 확장한다(§4-1 [5]).
    domain 편향은 canon(§5-9) domain 상호작용 기준으로 정규화되어 합=1이다.
    """
    n_domains = len(DOMAINS)
    by_trainer: dict[str, list[Interaction]] = {}
    for it in interactions:
        by_trainer.setdefault(it.trainer_ref, []).append(it)

    vectors: dict[str, list[float]] = {}
    for ref, items in by_trainer.items():
        total = len(items)
        domain_counts = [0.0] * n_domains
        corrections = confirmations = 0
        for it in items:
            if it.domain in _DOMAIN_INDEX:
                domain_counts[_DOMAIN_INDEX[it.domain]] += 1
            if it.action == "correction":
                corrections += 1
            elif it.action == "confirmation":
                confirmations += 1
        # canon domain 상호작용 기준 정규화 (canon 밖 domain이 섞여도 합=1 유지)
        domain_total = sum(domain_counts) or 1.0
        domain_frac = [c / domain_total for c in domain_counts]
        vectors[ref] = [*domain_frac, corrections / total, confirmations / total]
    return vectors


@dataclass
class ClusterResult:
    labels: dict[str, int]  # trainer_ref → 클러스터 라벨 (-1 = 노이즈)
    n_clusters: int
    order: list[str]


def cluster_trainers(vectors: dict[str, list[float]], config: ExperimentsConfig) -> ClusterResult:
    """밀도 기반(HDBSCAN, 파라미터 config) 클러스터링. 결정론적."""
    import numpy as np
    from sklearn.cluster import HDBSCAN

    refs = list(vectors)
    if not refs:
        return ClusterResult(labels={}, n_clusters=0, order=[])

    x = np.asarray([vectors[r] for r in refs], dtype=float)
    pcfg = config.persona
    model = HDBSCAN(
        min_cluster_size=pcfg.cluster_min_size,
        min_samples=pcfg.cluster_min_samples,
        copy=True,
    )
    labels = model.fit(x).labels_
    label_map = {refs[i]: int(labels[i]) for i in range(len(refs))}
    n_clusters = len({lbl for lbl in label_map.values() if lbl >= 0})
    return ClusterResult(labels=label_map, n_clusters=n_clusters, order=refs)


def _cluster_members(result: ClusterResult) -> dict[int, list[str]]:
    members: dict[int, list[str]] = {}
    for ref, label in result.labels.items():
        if label >= 0:
            members.setdefault(label, []).append(ref)
    return members


def persist_clusters(
    session: Session,
    result: ClusterResult,
    interactions: list[Interaction],
    *,
    version: str,
    state_version: str,
    config: ExperimentsConfig,
) -> tuple[list[PersonaCluster], list[PopulationPrior]]:
    """발견된 클러스터를 persona_clusters로, 클러스터별 intent prior를 population_priors로 적재.

    노이즈(-1)는 클러스터로 적재하지 않는다. cluster_id는 멤버 구성 기준으로 정준화되어
    HDBSCAN 정수 라벨의 입력 순서 의존을 제거한다(재현성·replay 안정).
    """
    # version 재사용 방지 — 같은 version에 두 번 적재하면 raw IntegrityError 대신 명확한 오류
    if session.scalar(
        select(func.count()).select_from(PersonaCluster).where(PersonaCluster.version == version)
    ):
        raise ValueError(f"version {version!r}가 이미 적재됨 — 새 version을 발급하라")

    members = _cluster_members(result)
    trainer_intents: dict[str, dict[str, int]] = {}
    for it in interactions:
        if it.intent_id:
            trainer_intents.setdefault(it.trainer_ref, {})
            counts = trainer_intents[it.trainer_ref]
            counts[it.intent_id] = counts.get(it.intent_id, 0) + 1

    # 멤버 최소 ref 기준으로 클러스터를 정준 정렬 → cluster_id가 입력 순서와 무관
    ordered = sorted(members, key=lambda lbl: min(members[lbl]))

    clusters: list[PersonaCluster] = []
    priors: list[PopulationPrior] = []
    for canon_idx, label in enumerate(ordered):
        refs = sorted(members[label])
        cluster_id = f"PC_{version}_{canon_idx}"
        clusters.append(
            PersonaCluster(
                cluster_id=cluster_id, method="HDBSCAN",
                axes={"discovered_label": label, "members": refs},
                member_count=len(refs), version=version,
            )
        )
        # 클러스터 intent prior — 멤버들의 intent 카운트 합산 후 정규화
        agg: dict[str, int] = {}
        for ref in refs:
            for intent_id, count in trainer_intents.get(ref, {}).items():
                agg[intent_id] = agg.get(intent_id, 0) + count
        total = sum(agg.values())
        if total:
            for intent_id, count in agg.items():
                priors.append(
                    PopulationPrior(
                        cluster_id=cluster_id, intent_id=intent_id,
                        prior=count / total, state_version=state_version,
                    )
                )

    session.add_all(clusters)
    session.add_all(priors)
    return clusters, priors


@dataclass
class ClusterReportRow:
    cluster_label: int
    member_count: int
    dominant_domain: str | None
    hypothesis_axis: str


@dataclass
class ClusterReport:
    rows: list[ClusterReportRow] = field(default_factory=list)


def build_cluster_report(result: ClusterResult, vectors: dict[str, list[float]]) -> ClusterReport:
    """발견된 클러스터 ↔ 8축 가설 대조표 (§4-1 [5])."""
    members = _cluster_members(result)
    rows: list[ClusterReportRow] = []
    for label, refs in sorted(members.items()):
        n_domains = len(DOMAINS)
        centroid = [
            sum(vectors[r][d] for r in refs) / len(refs) for d in range(n_domains)
        ]
        peak = max(range(n_domains), key=centroid.__getitem__)
        # 균등분포(1/n) 초과로 우세해야 dominant, 아니면 BALANCED
        dominant = DOMAINS[peak] if centroid[peak] > 1.0 / n_domains else None
        axis = next(
            (a.name for a in HYPOTHESIS_AXES if a.domain == dominant),
            "BALANCED",
        )
        rows.append(
            ClusterReportRow(
                cluster_label=label, member_count=len(refs),
                dominant_domain=dominant, hypothesis_axis=axis,
            )
        )
    return ClusterReport(rows=rows)
