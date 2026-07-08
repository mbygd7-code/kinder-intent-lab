"""Teacher Language Atlas v1 — coverage 지표·확장 큐·Simulator 통계 훅 (§2, §2-4).

- Atlas Coverage: 신규 발화 중 기존 pattern_cluster에 (임베딩 유사도 ≥ config) 매핑되는 비율.
- 미매핑 발화 → Atlas 확장 큐 자동 적재 (주간 클러스터링으로 신규 pattern_cluster 후보).
- Simulator(S6) 통계 재보정 훅: 현재 Atlas 상태에서 길이·지시어 분포를 재계산.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import ExperimentsConfig
from app.foundry.stages.s4_language_miner import cosine_similarity
from app.models.foundry import AtlasEntry, AtlasExpansionEntry

EmbedFn = Callable[[list[str]], list[list[float]]]

# 교사 발화의 지시어(대상 불명 신호) — Atlas L2 TARGET_UNSPECIFIED와 연결 (§2-1)
# 관형사(이/그/저)는 어절 동등으로 판정 — "종이·높이·길이·고양이" 같은 명사 오탐 방지.
DEIXIS_DETERMINERS = ("이", "그", "저")
# 대명사·지시부사 결합형은 부분문자열로 판정.
DEIXIS_PRONOUNS = ("이거", "저거", "그거", "이걸", "저걸", "이것", "저것", "여기", "거기")


def _has_deixis(text: str) -> bool:
    if any(marker in text for marker in DEIXIS_PRONOUNS):
        return True
    return any(word in text.split() for word in DEIXIS_DETERMINERS)


@dataclass
class CoverageReport:
    total: int
    mapped: int
    unmapped: list[str] = field(default_factory=list)

    def coverage(self) -> float:
        return self.mapped / self.total if self.total else 0.0


def compute_coverage(
    session: Session,
    utterances: list[str],
    embed_fn: EmbedFn,
    config: ExperimentsConfig,
) -> CoverageReport:
    """각 발화를 가장 가까운 Atlas surface_form에 매핑, 유사도 ≥ 임계면 mapped."""
    entries = list(session.scalars(select(AtlasEntry)))
    if not utterances:
        return CoverageReport(total=0, mapped=0, unmapped=[])

    threshold = config.atlas.map_min_similarity
    atlas_vecs = embed_fn([e.surface_form for e in entries]) if entries else []
    utt_vecs = embed_fn(utterances)

    mapped = 0
    unmapped: list[str] = []
    for utterance, uvec in zip(utterances, utt_vecs, strict=True):
        best = max((cosine_similarity(uvec, av) for av in atlas_vecs), default=-1.0)
        if best >= threshold:
            mapped += 1
        else:
            unmapped.append(utterance)
    return CoverageReport(total=len(utterances), mapped=mapped, unmapped=unmapped)


def enqueue_unmapped(
    session: Session, utterances: list[str], source_run: str | None = None
) -> list[AtlasExpansionEntry]:
    """미매핑 발화를 Atlas 확장 큐에 적재 (이미 큐에 있는 발화는 건너뛴다)."""
    if not utterances:
        return []
    existing = set(
        session.scalars(
            select(AtlasExpansionEntry.utterance).where(
                AtlasExpansionEntry.utterance.in_(utterances)
            )
        )
    )
    created: list[AtlasExpansionEntry] = []
    seen: set[str] = set()
    for utterance in utterances:
        if utterance in existing or utterance in seen:
            continue
        seen.add(utterance)
        entry = AtlasExpansionEntry(
            queue_id=f"AQ_{uuid.uuid4().hex[:12]}", utterance=utterance,
            status="PENDING", source_run=source_run,
        )
        session.add(entry)
        created.append(entry)
    return created


@dataclass
class SimulatorStats:
    """S6 Teacher Simulator 재보정 입력 — Atlas 통계(observed_count 가중)."""

    sample_count: int
    mean_word_length: float
    deixis_ratio: float


def simulator_stats(session: Session) -> SimulatorStats:
    """현재 Atlas 상태에서 발화 길이·지시어 분포를 재계산 (§2-3 소비처 1)."""
    entries = list(session.scalars(select(AtlasEntry)))
    if not entries:
        return SimulatorStats(sample_count=0, mean_word_length=0.0, deixis_ratio=0.0)

    total_weight = 0.0
    weighted_length = 0.0
    deixis_weight = 0.0
    for entry in entries:
        weight = float(max(1, entry.observed_count or 1))
        total_weight += weight
        weighted_length += len(entry.surface_form.split()) * weight
        if _has_deixis(entry.surface_form):
            deixis_weight += weight

    return SimulatorStats(
        sample_count=len(entries),
        mean_word_length=weighted_length / total_weight,
        deixis_ratio=deixis_weight / total_weight,
    )
