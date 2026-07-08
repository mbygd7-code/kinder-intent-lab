"""Persona prior 테이블 CRUD + state_version 발급 + cap 적용 (§5-3·§5-5, replay).

- population: (persona_cluster × intent) → prior, teacher: (trainer_ref × intent) → prior.
- prior는 state_version으로 스냅샷된다 — 조회는 항상 state_version과 함께 반환(replay 무결성).
- 추론 시 노드 점수에 밖에서 곱하되(§5-5), 영향은 config.brain.persona_prior_cap로 제한한다
  (§4-2 필터버블 방지). 여기서는 prior 저장·조회·cap 함수만 — 실제 scoring은 Phase 3.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.persona import PersonaStateVersion, PopulationPrior, TeacherPrior


@dataclass
class PriorSet:
    """조회 결과 — prior와 그 스냅샷 버전을 항상 함께 반환한다."""

    state_version: str | None
    priors: dict[str, float] = field(default_factory=dict)


# --- state_version 발급 ---


def _validate_priors(priors: dict[str, float]) -> None:
    for intent_id, prior in priors.items():
        if not 0.0 <= prior <= 1.0:
            raise ValueError(f"prior {prior} for {intent_id!r}가 [0,1] 밖")


def issue_state_version(session: Session, *, reason: str, parent: str | None = None) -> str:
    """새 prior 스냅샷 버전 발급 (단조 seq). prior가 바뀔 때마다 새 버전을 발급한다.

    seq는 max(seq)+1이라 단일 작성자를 전제한다(배치 러너는 단일 프로세스). 동시 발급 시
    seq UNIQUE / version PK가 loud-fail로 막으므로 무음 오염은 없다.
    """
    seq = (session.scalar(select(func.max(PersonaStateVersion.seq))) or 0) + 1
    version = f"ps-{seq:06d}"
    session.add(
        PersonaStateVersion(version=version, seq=seq, reason=reason, parent_version=parent)
    )
    session.flush()
    return version


def current_state_version(session: Session) -> str | None:
    """가장 최근 발급된 버전 (없으면 None)."""
    return session.scalar(
        select(PersonaStateVersion.version).order_by(PersonaStateVersion.seq.desc()).limit(1)
    )


# --- population prior CRUD ---


def set_population_priors(
    session: Session, cluster_id: str, priors: dict[str, float], state_version: str
) -> None:
    """cluster의 prior를 한 state_version 스냅샷으로 적재. 스냅샷은 불변 —
    prior를 바꾸려면 새 state_version을 발급하라(같은 버전 재-set은 PK 충돌로 거부됨)."""
    _validate_priors(priors)
    for intent_id, prior in priors.items():
        session.add(
            PopulationPrior(
                cluster_id=cluster_id, intent_id=intent_id, prior=prior,
                state_version=state_version,
            )
        )


def get_population_priors(
    session: Session, cluster_id: str, state_version: str | None = None
) -> PriorSet:
    """cluster의 prior를 조회. state_version 미지정 시 current 버전 사용. 항상 버전 동반."""
    version = state_version or current_state_version(session)
    if version is None:
        return PriorSet(state_version=None, priors={})
    rows = session.execute(
        select(PopulationPrior.intent_id, PopulationPrior.prior).where(
            PopulationPrior.cluster_id == cluster_id,
            PopulationPrior.state_version == version,
        )
    ).all()
    return PriorSet(state_version=version, priors={r.intent_id: r.prior for r in rows})


# --- teacher prior CRUD ---


def set_teacher_priors(
    session: Session, trainer_ref: str, priors: dict[str, float], state_version: str
) -> None:
    """trainer의 prior를 한 state_version 스냅샷으로 적재 (불변 — 변경 시 새 버전)."""
    _validate_priors(priors)
    for intent_id, prior in priors.items():
        session.add(
            TeacherPrior(
                trainer_ref=trainer_ref, intent_id=intent_id, prior=prior,
                state_version=state_version,
            )
        )


def get_teacher_priors(
    session: Session, trainer_ref: str, state_version: str | None = None
) -> PriorSet:
    version = state_version or current_state_version(session)
    if version is None:
        return PriorSet(state_version=None, priors={})
    rows = session.execute(
        select(TeacherPrior.intent_id, TeacherPrior.prior).where(
            TeacherPrior.trainer_ref == trainer_ref,
            TeacherPrior.state_version == version,
        )
    ).all()
    return PriorSet(state_version=version, priors={r.intent_id: r.prior for r in rows})


# --- cap 적용 (§4-2, §5-5) ---


def capped_prior_factor(prior: float, cap: float) -> float:
    """prior(0..1)를 점수 배수로 변환하되 |배수 − 1| ≤ cap로 제한한다.

    prior=0.5 → 1.0(중립), prior→1 → 최대 1+cap, prior→0 → 최소 1−cap.
    범위 밖 prior도 [1−cap, 1+cap]로 클램프되어 필터버블(prior가 점수를 지배)을 막는다.
    """
    raw = 1.0 + (prior - 0.5) * 2.0 * cap
    return min(1.0 + cap, max(1.0 - cap, raw))


def apply_persona_prior(activation: float, prior: float, cap: float) -> float:
    """활성 점수에 cap 적용된 persona prior 배수를 곱한다 — 점수 변화율 ≤ cap."""
    return activation * capped_prior_factor(prior, cap)
