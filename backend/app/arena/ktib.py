"""KTIB 구성기 — 격리 벤치마크 스냅샷 (§8-2, T5.1).

자격: `dataset_split=BENCHMARK_HOLDOUT ∧ reliability_tier=GOLD ∧ label_state=LABELED
∧ origin_channel ∉ {FOUNDRY_SYNTHETIC, FOUNDRY_AUGMENTED}` (절대 규칙 2).
이 자격의 **강제**는 episodes.benchmark_integrity CHECK가 물리적으로 담당한다 — 여기서는
같은 술어로 한 번 더 좁혀 읽을 뿐, 우회 경로를 만들지 않는다.

**동결(freeze):** 채택 시점의 발화·gold intent·workspace(visual_semantics 포함)를 ktib_items에
복사한다. 에피소드 원본이 나중에 바뀌어도 벤치마크 점수는 흔들리지 않는다.

**extractor 고정 규칙(§8-2):** ktib_version은 `에피소드 집합 ⊕ extractor 지문`의 해시로 식별된다.
extractor를 올려 재추출하면 지문이 달라져 **새 ktib_version이 강제**된다 — 신·구 벤치마크 점수를
같은 축에 그리지 않기 위해서다. 기존 버전의 스냅샷을 덮어쓰는 경로는
`config.visual_semantics.ktib_extractor_pinned`가 켜져 있는 한 flush 리스너가 차단한다
(app/models/guards.py::KtibFrozen).

빈 KTIB는 0%가 아니라 **에러**다 — 벤치마크가 없다는 사실을 점수처럼 보이게 하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import ExperimentsConfig
from app.core.datasets import BENCHMARK_SPLIT
from app.models.arena import KtibItem, KtibVersion
from app.models.episodes import Episode, Evidence
from app.models.foundry import CanonicalScenario

# 절대 규칙 2 — 벤치마크에서 배제되는 합성 채널
SYNTHETIC_CHANNELS = ("FOUNDRY_SYNTHETIC", "FOUNDRY_AUGMENTED")


class EmptyKtib(Exception):
    """자격을 갖춘 벤치마크 에피소드가 0건 — 점수가 아니라 구성 실패다(§8-2)."""


class AmbiguousGoldLabel(Exception):
    """GOLD 에피소드의 label_distribution에 유일 최댓값이 없다 — 정답을 임의로 고르지 않는다."""


class AdversarialInBenchmark(Exception):
    """벤치마크 후보에 adversarial evidence가 붙어 있다 — 자연 분포와 분리한다 (절대 규칙 6)."""


@dataclass(frozen=True)
class FrozenItem:
    episode_id: str
    gold_intent: str
    teacher_prompt: str
    lang: str
    workspace_snapshot: dict | None


def eligible_episodes(session: Session) -> list[Episode]:
    """KTIB 자격 4조건을 모두 만족하는 에피소드 — episode_id 오름차순(결정론)."""
    return list(session.scalars(
        select(Episode)
        .where(
            Episode.dataset_split == BENCHMARK_SPLIT,
            Episode.reliability_tier == "GOLD",
            Episode.label_state == "LABELED",
            Episode.origin_channel.notin_(SYNTHETIC_CHANNELS),
        )
        .order_by(Episode.episode_id)
    ))


def _gold_intent(episode: Episode) -> str:
    """확정 라벨 = label_distribution의 유일 최댓값. 동률이면 임의 선택 대신 loud-fail."""
    dist = episode.label_distribution or {}
    if not dist:
        raise AmbiguousGoldLabel(f"{episode.episode_id}: label_distribution 비어 있음")
    top = max(dist.values())
    winners = [i for i, v in dist.items() if v == top]
    if len(winners) != 1:
        raise AmbiguousGoldLabel(f"{episode.episode_id}: 최댓값 동률 {sorted(winners)}")
    return winners[0]


def _snapshot(session: Session, episode: Episode) -> dict | None:
    """채택 시점 workspace(visual_semantics 포함). 시나리오가 없으면 None — 지어내지 않는다."""
    if not episode.scenario_id:
        return None
    scenario = session.get(CanonicalScenario, episode.scenario_id)
    return dict(scenario.workspace_state) if scenario else None


def assert_no_adversarial(session: Session, episode_ids: list[str]) -> None:
    """절대 규칙 6: adversarial evidence는 자연 분포 집계에서 분리한다.

    Break the Brain(§8-1) 산출은 구조적으로 `dataset_split=TRAIN`이라 벤치마크에 들어올 수
    없지만, 수동 UPDATE로 끌어올 수는 있다. 그 경로를 여기서 막는다 — 스트레스 테스트용 발화가
    자연 분포 벤치마크 점수에 섞이면 그 점수는 무엇도 뜻하지 않는다.
    """
    if not episode_ids:
        return
    tainted = sorted(set(session.scalars(
        select(Evidence.episode_id).where(
            Evidence.episode_id.in_(episode_ids), Evidence.adversarial.is_(True)
        )
    )))
    if tainted:
        raise AdversarialInBenchmark(
            f"adversarial evidence가 붙은 벤치마크 후보: {tainted} — 절대 규칙 6 (§8-1)"
        )


def freeze_items(session: Session) -> list[FrozenItem]:
    """자격 에피소드를 동결 스냅샷으로 변환 (DB 기록 없음 — 순수 읽기)."""
    episodes = eligible_episodes(session)
    assert_no_adversarial(session, [ep.episode_id for ep in episodes])
    return [
        FrozenItem(
            episode_id=ep.episode_id,
            gold_intent=_gold_intent(ep),
            teacher_prompt=ep.teacher_prompt,
            lang=ep.lang,
            workspace_snapshot=_snapshot(session, ep),
        )
        for ep in episodes
    ]


def _snapshot_extractors(items: list[FrozenItem]) -> list[str]:
    """동결된 스냅샷에 실제로 박혀 있는 visual_semantics extractor_version 집합.

    config의 vocabulary_version이 아니라 **데이터에 기록된 추출기 버전**이 replay 축이다 —
    설정만 바꾸고 재추출하지 않은 경우와, 재추출한 경우를 구분해야 하기 때문.
    """
    found: set[str] = set()
    for item in items:
        for vs in (item.workspace_snapshot or {}).get("visual_semantics", []) or []:
            version = vs.get("extractor_version")
            if version:
                found.add(version)
    return sorted(found)


def extractor_versions(items: list[FrozenItem], config: ExperimentsConfig) -> dict:
    """replay 무결성 4종의 4번째 축 — 이 KTIB에 동결된 extractor 지문."""
    return {
        "visual_semantics_vocabulary": config.visual_semantics.vocabulary_version,
        "visual_semantics_extractors": _snapshot_extractors(items),
    }


def _content_hash(items: list[FrozenItem], extractors: dict) -> str:
    """에피소드 집합 ⊕ extractor 지문 → 벤치마크 동일성. 어느 쪽이 바뀌어도 새 버전이 된다."""
    payload = {
        "extractors": extractors,
        "items": [
            {
                "episode_id": i.episode_id,
                "gold_intent": i.gold_intent,
                "teacher_prompt": i.teacher_prompt,
                "lang": i.lang,
                "workspace_snapshot": i.workspace_snapshot,
            }
            for i in items  # eligible_episodes가 episode_id 순으로 이미 정렬
        ],
    }
    blob = json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()


def find_by_hash(session: Session, content_hash: str) -> KtibVersion | None:
    return session.scalar(
        select(KtibVersion).where(KtibVersion.content_hash == content_hash)
    )


def latest_ktib(session: Session) -> KtibVersion | None:
    return session.scalar(select(KtibVersion).order_by(KtibVersion.seq.desc()))


def load_items(session: Session, ktib_version: str) -> list[KtibItem]:
    """벤치마크 아이템 — episode_id 오름차순(러너 재현성의 전제)."""
    return list(session.scalars(
        select(KtibItem)
        .where(KtibItem.ktib_version == ktib_version)
        .order_by(KtibItem.episode_id)
    ))


def build_ktib(
    session: Session, config: ExperimentsConfig, *, notes: str | None = None
) -> KtibVersion:
    """자격 에피소드를 동결해 ktib_version을 발급한다.

    - 같은 내용(에피소드 집합 ⊕ extractor 지문)이면 기존 버전을 그대로 반환한다(멱등).
    - extractor가 바뀌었거나 에피소드 집합이 바뀌었으면 **새 ktib_version**을 만든다.
      기존 버전의 items는 절대 건드리지 않는다(§8-2 동결).
    - 자격 에피소드가 0건이면 EmptyKtib — 빈 벤치마크를 0%로 보고하지 않는다.
    """
    items = freeze_items(session)
    if not items:
        raise EmptyKtib(
            "BENCHMARK_HOLDOUT ∧ GOLD ∧ LABELED ∧ 비합성 에피소드가 0건 — "
            "KTIB를 구성할 수 없다 (§8-2)"
        )

    extractors = extractor_versions(items, config)
    content_hash = _content_hash(items, extractors)

    existing = find_by_hash(session, content_hash)
    if existing is not None:
        return existing  # 같은 벤치마크 — 재빌드하지 않는다

    seq = int(session.scalar(select(func.coalesce(func.max(KtibVersion.seq), 0))) or 0) + 1
    version = KtibVersion(
        ktib_version=f"ktib-{seq}",
        seq=seq,
        extractor_versions=extractors,
        episode_count=len(items),
        content_hash=content_hash,
        notes=notes,
    )
    session.add(version)
    session.flush()  # FK 대상 선행 삽입
    for item in items:
        session.add(KtibItem(
            ktib_version=version.ktib_version,
            episode_id=item.episode_id,
            gold_intent=item.gold_intent,
            teacher_prompt=item.teacher_prompt,
            lang=item.lang,
            workspace_snapshot=item.workspace_snapshot,
        ))
    session.flush()
    return version
