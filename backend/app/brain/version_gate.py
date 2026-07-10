"""Version Gate + Candidate Build (§6-6, T4.5).

Slow 경로: 누적된 성장(신규 GOLD 등)이 임계를 넘으면 후보(candidate) 뇌 버전을 빌드해
brain_versions에 기록한다. Arena 시험·promote/reject는 T4.6.

**불변식(AC):** candidate 빌드는 현행(promote된) 버전의 데이터를 절대 건드리지 않는다 —
brain_versions에 새 행 하나를 INSERT하고, exemplar/edge/prior는 읽기만 해 delta로 묶는다.
decision='candidate'라 observatory의 brain_version(promote만 읽음)도 바뀌지 않는다.

new_gold는 '현재 GOLD∧LABELED 수 − base(현행 promote)의 gold_watermark'다(누적 아닌 증분).
seed 상태(promote 없음)면 base='seed-v0', watermark=0. 임계는 config.version_gate(절대 규칙 1).
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.brain.priors import current_state_version
from app.core.config import ExperimentsConfig
from app.core.datasets import training_gold
from app.models.brain import BrainVersion, ConfusionEdge
from app.models.episodes import Episode

SEED_VERSION = "seed-v0"  # 최초 promote가 없을 때의 기준 이름(observatory와 동일 관례)


# --- 상태 조회 ---


def current_base(session: Session) -> BrainVersion | None:
    """현행 base = 가장 최근 promote된 버전 (없으면 None=seed)."""
    return session.scalar(
        select(BrainVersion)
        .where(BrainVersion.decision == "promote")
        .order_by(BrainVersion.created_at.desc())
    )


def _base_name(base: BrainVersion | None) -> str:
    return base.version if base is not None else SEED_VERSION


def _base_watermark(base: BrainVersion | None) -> int:
    return int((base.delta or {}).get("gold_watermark", 0)) if base is not None else 0


def count_gold(session: Session) -> int:
    """학습 GOLD∧LABELED 에피소드 절대량(§3-3).

    BENCHMARK_HOLDOUT은 제외한다 — 벤치마크를 늘렸다고 candidate 빌드가 트리거되면 안 된다
    (§8-2 "학습 파이프라인이 접근할 수 없다").
    """
    return int(session.scalar(
        select(func.count()).select_from(Episode).where(training_gold())
    ) or 0)


def _new_gold(session: Session, base: BrainVersion | None) -> int:
    """신규 GOLD 단일 계산원 — 현재 GOLD − base watermark (증분). 게이트·상태·빌드가 공유한다."""
    return count_gold(session) - _base_watermark(base)


def new_gold_since_base(session: Session) -> int:
    """현재 GOLD − base watermark (증분). base 없으면 현재 GOLD 전부가 신규."""
    return _new_gold(session, current_base(session))


def pending_candidate(session: Session, base_name: str) -> BrainVersion | None:
    """이 base 위에 아직 판정 안 난(decision='candidate') 후보 (있으면 재빌드하지 않는다)."""
    return session.scalar(
        select(BrainVersion)
        .where(BrainVersion.decision == "candidate", BrainVersion.base == base_name)
        .order_by(BrainVersion.created_at.desc())
    )


# --- delta 계산 (읽기 전용) ---


def _gold_nodes(session: Session) -> list[str]:
    """학습 GOLD∧LABELED 에피소드의 최상위 intent 집합 — 후보가 담는 노드 (벤치마크 제외)."""
    rows = session.execute(
        select(Episode.label_distribution).where(training_gold())
    ).all()
    return sorted({max(d, key=d.get) for (d,) in rows if d})


def _signal_edges(session: Session) -> list[str]:
    """신호가 있는(confusion_rate 측정된) edge id — 후보가 담는 edge."""
    return sorted(session.scalars(
        select(ConfusionEdge.edge_id).where(ConfusionEdge.confusion_rate.isnot(None))
    ).all())


def _count_labeled(session: Session) -> int:
    return int(session.scalar(
        select(func.count()).select_from(Episode).where(Episode.label_state == "LABELED")
    ) or 0)


# --- 후보 빌드 ---


def build_candidate(
    session: Session, config: ExperimentsConfig, *, trigger: str | None = None
) -> BrainVersion | None:
    """조건 충족 시 candidate 뇌 버전을 brain_versions에 기록하고 반환. 미충족이면 None(무생성).

    이미 대기 중인 candidate가 있으면 그것을 반환한다(멱등 — 중복 후보를 만들지 않는다).
    현행 promote 버전의 데이터는 읽기만 한다(불변).
    """
    base = current_base(session)
    base_name = _base_name(base)

    existing = pending_candidate(session, base_name)
    if existing is not None:
        return existing  # 대기 후보 있음 → 재빌드 안 함

    new_gold = _new_gold(session, base)  # 상태/게이트와 동일 단일 계산원
    if new_gold < config.version_gate.min_new_gold:
        return None  # 조건 미달 — 후보 미생성(brain_versions 무변화)

    watermark = count_gold(session)
    rc = 1 + int(session.scalar(
        select(func.count()).select_from(BrainVersion).where(BrainVersion.base == base_name)
    ) or 0)
    version = f"{base_name}-rc{rc}"
    new_valid = _count_labeled(session)
    row = BrainVersion(
        version=version,
        base=base_name,
        trigger=trigger or f"D_MODEL: new_gold {new_gold}, new_valid_episodes {new_valid}",
        delta={
            "gold_watermark": watermark,
            "updated_nodes": _gold_nodes(session),
            "updated_edges": _signal_edges(session),
            "persona_state_version": current_state_version(session),
        },
        decision="candidate",
    )
    session.add(row)
    session.flush()
    return row


# --- 상태 리포트 (UI·ops 관측용) ---


@dataclass
class VersionGateStatus:
    base_version: str
    new_gold: int
    min_new_gold: int
    condition_met: bool
    pending_candidate: str | None


def version_gate_status(session: Session, config: ExperimentsConfig) -> VersionGateStatus:
    base = current_base(session)
    base_name = _base_name(base)
    new_gold = _new_gold(session, base)  # build_candidate와 동일 계산원 — 드리프트 방지
    pend = pending_candidate(session, base_name)
    return VersionGateStatus(
        base_version=base_name,
        new_gold=new_gold,
        min_new_gold=config.version_gate.min_new_gold,
        condition_met=new_gold >= config.version_gate.min_new_gold,
        pending_candidate=pend.version if pend is not None else None,
    )
