"""Fast Update — teacher prior 미세 조정의 안전 규칙 (§6-5, T4.4).

"강화"의 Fast 경로: 개인(teacher) prior를 트레이너의 gym 근거로 조금씩 조정한다. 공유 뇌를
바꾸는 Slow 경로(candidate → Arena, §6-6)와 분리된다 — 여기서는 **개인 prior만** 만지며 node
brightness/size/density엔 접근하지 않는다.

**주기·경계 (§6-6, 리뷰 CRITICAL/MAJOR 반영):** state_version은 population·모든 teacher prior가
공유하는 **전역 단일 스냅샷 포인터**다(priors.py). 하나만 바꿔도 새 버전엔 나머지 principal의
prior를 전부 이월해야 current에서 사라지지 않는다(§5-3 완결 스냅샷). 그래서 Fast Update는 요청
경로(gym submit)가 아니라 **배치(run_fast_update_batch·주간 decay)로 한 번에 한 버전만** 발급한다
— per-submit 버전 폭증과 온라인 경로의 seq 경쟁을 피한다.

안전 규칙(전부 config.fast_update — 리터럴 금지, 절대 규칙 1):
- 표본(트레이너 gym evidence) < fast_min_samples인 intent는 조정하지 않는다.
- 한 번의 조정 이동폭 > fast_delta_cap이면 거부한다(무음 클램프가 아니라 명시 거부).
- weekly_decay: prior를 중립(0.5)으로 주간 감쇠 — 오래된 개인화가 영구 고착되지 않게.
- rollback: 이전 state_version의 prior를 복원 — 나쁜 조정을 되돌린다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.brain.priors import (
    current_state_version,
    get_teacher_priors,
    issue_state_version,
    set_teacher_priors,
)
from app.core.config import ExperimentsConfig
from app.gym.evidence import GYM_ACTOR_TYPE
from app.models.episodes import Evidence
from app.models.persona import PopulationPrior, TeacherPrior

# prior 척도 [0,1]의 중립 중앙값 — 실험 임계값이 아니라 구조 상수(capped_prior_factor와 동일 관례)
NEUTRAL_PRIOR = 0.5
_CAP_EPSILON = 1e-9      # cap 경계(정확히 cap만큼 이동)를 float64에서 거부로 오판하지 않게
# prior는 REAL(float32)로 저장된다 — no-change 판정은 float32 정밀도(ULP ~6e-8)보다 커야
# 수렴 후 무한 버전 churn이 안 생긴다(리뷰 MAJOR). cap(0.05)보다 훨씬 작아 의미 있는 조정은 통과.
_NO_CHANGE_STEP = 1e-6


@dataclass
class FastUpdateResult:
    state_version: str | None                          # 새 스냅샷 버전(변경 없으면 None=no-op)
    updated: dict[str, float] = field(default_factory=dict)          # intent → 새 prior
    skipped_insufficient: list[str] = field(default_factory=list)    # 표본 미달로 건너뜀
    rejected_over_cap: list[str] = field(default_factory=list)       # 상한 초과로 거부


@dataclass
class BatchResult:
    state_version: str | None                          # 배치 스냅샷 버전(변경 없으면 None)
    trainers_updated: dict[str, list[str]] = field(default_factory=dict)  # trainer → 조정 intent


def _clamp01(x: float) -> float:
    return min(1.0, max(0.0, x))


# --- 표본 카운트 (min-samples 게이트 입력) ---


def count_teacher_samples(session: Session, trainer_ref: str) -> dict[str, int]:
    """트레이너의 gym evidence를 intent별로 센다 — Fast Update의 '표본'.

    actor=TEACHER_TRAINER · polarity=supports · adversarial=false만(절대 규칙 6: adversarial 분리).
    """
    rows = session.execute(
        select(Evidence.intent_id, func.count())
        .where(
            Evidence.trainer_ref == trainer_ref,
            Evidence.actor_type == GYM_ACTOR_TYPE,
            Evidence.polarity == "supports",
            Evidence.adversarial.is_(False),
        )
        .group_by(Evidence.intent_id)
    ).all()
    return {intent: int(cnt) for intent, cnt in rows}


# --- 완결(all-principal) 스냅샷 적재 (불변 + 전역 포인터 안전) ---


def _issue_snapshot_carrying_forward(
    session: Session, *, trainer_updates: dict[str, dict[str, float]], reason: str,
    parent: str | None,
) -> str:
    """새 global state_version 발급 + 직전 current의 **모든 principal** prior 이월 + 변경 적용.

    이월 대상: population prior 전부 + trainer_updates에 없는 teacher 전부. 그 위에 변경을
    얹어 완결 스냅샷을 만든다 — 전역 포인터가 한 principal만 담아 나머지를 날리는 것을 막는다
    (리뷰 CRITICAL). trainer_updates는 비어 있지 않다고 가정(호출자가 no-op을 먼저 거른다).
    """
    prev = current_state_version(session)
    version = issue_state_version(session, reason=reason, parent=parent or prev)
    if prev is not None:
        for cid, iid, prior in session.execute(
            select(PopulationPrior.cluster_id, PopulationPrior.intent_id, PopulationPrior.prior)
            .where(PopulationPrior.state_version == prev)
        ).all():
            session.add(PopulationPrior(
                cluster_id=cid, intent_id=iid, prior=prior, state_version=version
            ))
        for tref, iid, prior in session.execute(
            select(TeacherPrior.trainer_ref, TeacherPrior.intent_id, TeacherPrior.prior)
            .where(
                TeacherPrior.state_version == prev,
                TeacherPrior.trainer_ref.notin_(list(trainer_updates)),
            )
        ).all():
            session.add(TeacherPrior(
                trainer_ref=tref, intent_id=iid, prior=prior, state_version=version
            ))
    for tref, priors in trainer_updates.items():
        set_teacher_priors(session, tref, priors, version)
    session.flush()
    return version


# --- 안전 규칙 게이트 (fast update·batch 공용) ---


def _gate(
    base: dict[str, float], proposals: dict[str, float], counts: dict[str, int],
    config: ExperimentsConfig,
) -> tuple[dict[str, float], list[str], list[str]]:
    """제안을 §6-5 안전 규칙으로 걸러 (updated, skipped, rejected)를 낸다."""
    fu = config.fast_update
    updated: dict[str, float] = {}
    skipped: list[str] = []
    rejected: list[str] = []
    for intent, target in proposals.items():
        if counts.get(intent, 0) < fu.fast_min_samples:
            skipped.append(intent)          # 표본 미달 → 조정 안 함
            continue
        current = base.get(intent, NEUTRAL_PRIOR)
        if abs(target - current) > fu.fast_delta_cap + _CAP_EPSILON:
            rejected.append(intent)         # 상한 초과 → 거부
            continue
        if abs(target - current) <= _NO_CHANGE_STEP:
            continue                        # 사실상 변화 없음 → 버전 churn 방지
        updated[intent] = _clamp01(target)
    return updated, skipped, rejected


# --- Fast Update: 단일 트레이너 (안전 규칙 적용 후 조정) ---


def fast_update_teacher_prior(
    session: Session,
    trainer_ref: str,
    proposals: dict[str, float],
    config: ExperimentsConfig,
    *,
    reason: str = "fast_update",
) -> FastUpdateResult:
    """proposals(intent→목표 prior)를 안전 규칙으로 걸러 적용하고 완결 스냅샷을 발급한다.

    조정 대상이 하나도 없으면 새 버전을 발급하지 않는다(no-op).
    """
    base = get_teacher_priors(session, trainer_ref).priors
    counts = count_teacher_samples(session, trainer_ref)
    updated, skipped, rejected = _gate(base, proposals, counts, config)

    if not updated:  # no-op — 새 버전을 만들지 않는다
        return FastUpdateResult(None, {}, skipped, rejected)

    version = _issue_snapshot_carrying_forward(
        session, trainer_updates={trainer_ref: {**base, **updated}},  # 이어받은 prior + 조정분
        reason=reason, parent=current_state_version(session),
    )
    return FastUpdateResult(version, updated, skipped, rejected)


# --- 증거 기반 자동 제안 ---


def propose_from_gym(
    session: Session, trainer_ref: str, config: ExperimentsConfig
) -> dict[str, float]:
    """트레이너 gym 근거로 목표 prior를 제안한다 — evidence 분포(share)를 향해 cap 스텝만큼.

    안정 목표 target = 0.5 + 0.5·share (share = 이 intent가 트레이너 evidence에서 차지하는 비율).
    gym 확인은 양(+) 신호라 목표는 항상 ≥ 중립이고, dominant intent일수록 1.0에 가깝다. 매 호출은
    현재값에서 목표로 **cap 이하** 이동하므로 상한 안에서 목표로 수렴한다. 목표는 total로 정규화되어
    한 intent의 evidence가 늘면 다른 intent의 share가 줄어 목표도 함께 재정렬된다 — 즉 prior는
    트레이너의 **현재 분포**를 추적한다(고정 목표가 아니다). 목표 공식은 실험값이다(§6-5 config
    파라미터들처럼 확정 아님). min-samples·상한 게이트는 fast_update_teacher_prior/_gate 소관.
    """
    fu = config.fast_update
    base = get_teacher_priors(session, trainer_ref).priors
    counts = count_teacher_samples(session, trainer_ref)
    total = sum(counts.values())
    if total == 0:
        return {}
    proposals: dict[str, float] = {}
    for intent, cnt in counts.items():
        current = base.get(intent, NEUTRAL_PRIOR)
        target = NEUTRAL_PRIOR + (1.0 - NEUTRAL_PRIOR) * (cnt / total)  # 분포 기반 목표
        step = max(-fu.fast_delta_cap, min(fu.fast_delta_cap, target - current))  # cap 스텝
        proposals[intent] = _clamp01(current + step)
    return proposals


def fast_update_from_gym(
    session: Session, trainer_ref: str, config: ExperimentsConfig, *, reason: str = "fast_update"
) -> FastUpdateResult:
    """propose_from_gym → fast_update_teacher_prior. 단일 트레이너 자동 경로."""
    return fast_update_teacher_prior(
        session, trainer_ref, propose_from_gym(session, trainer_ref, config), config, reason=reason
    )


# --- 배치: 모든 트레이너를 한 버전으로 (요청 경로가 아닌 주기 실행) ---


def _evidenced_trainers(session: Session) -> list[str]:
    """gym evidence가 있는 트레이너 목록 (결정론 순서)."""
    return list(session.scalars(
        select(Evidence.trainer_ref)
        .where(
            Evidence.actor_type == GYM_ACTOR_TYPE,
            Evidence.polarity == "supports",
            Evidence.adversarial.is_(False),
            Evidence.trainer_ref.isnot(None),
        )
        .distinct()
        .order_by(Evidence.trainer_ref)
    ).all())


def run_fast_update_batch(
    session: Session, config: ExperimentsConfig, *, reason: str = "fast_update_batch"
) -> BatchResult:
    """모든 gym-근거 트레이너의 fast update를 **한 번의 새 global 버전**으로 적용한다.

    per-submit 버전 폭증·온라인 seq 경쟁을 피하는 배치 진입점(§6-6). 각 트레이너의 안전 규칙은
    개별 적용하고, 조정이 있는 트레이너들만 모아 완결 스냅샷 한 개를 발급한다.
    """
    trainer_updates: dict[str, dict[str, float]] = {}
    summary: dict[str, list[str]] = {}
    for tref in _evidenced_trainers(session):
        base = get_teacher_priors(session, tref).priors
        counts = count_teacher_samples(session, tref)
        updated, _skipped, _rejected = _gate(
            base, propose_from_gym(session, tref, config), counts, config
        )
        if updated:
            trainer_updates[tref] = {**base, **updated}
            summary[tref] = list(updated)
    if not trainer_updates:
        return BatchResult(None, {})
    version = _issue_snapshot_carrying_forward(
        session, trainer_updates=trainer_updates, reason=reason,
        parent=current_state_version(session),
    )
    return BatchResult(version, summary)


# --- weekly decay ---


def weekly_decay_teacher_prior(
    session: Session, trainer_ref: str, config: ExperimentsConfig, *, reason: str = "weekly_decay"
) -> FastUpdateResult:
    """모든 prior를 중립(0.5)으로 weekly_decay만큼 당긴다 — 완결 스냅샷. prior 없으면 no-op."""
    decay = config.fast_update.weekly_decay
    base = get_teacher_priors(session, trainer_ref).priors
    if not base:
        return FastUpdateResult(None, {}, [], [])
    decayed = {
        intent: _clamp01(NEUTRAL_PRIOR + (prior - NEUTRAL_PRIOR) * decay)
        for intent, prior in base.items()
    }
    version = _issue_snapshot_carrying_forward(
        session, trainer_updates={trainer_ref: decayed}, reason=reason,
        parent=current_state_version(session),
    )
    return FastUpdateResult(version, decayed, [], [])


# --- rollback ---


def rollback_teacher_prior(
    session: Session, trainer_ref: str, *, to_version: str, config: ExperimentsConfig,
    reason: str = "rollback",
) -> str:
    """이전 state_version의 trainer prior를 복원한다 — 완결 스냅샷을 발급해 current를 되돌린다.

    불변성: 대상 버전(to_version)은 보존하고, 나머지 principal은 current에서 이월하며, 이 트레이너
    만 to_version 값으로 되돌린다(단조 seq 유지). config는 서명 일관성용(향후 롤백 정책 자리).
    """
    _ = config
    source = get_teacher_priors(session, trainer_ref, to_version).priors
    return _issue_snapshot_carrying_forward(
        session, trainer_updates={trainer_ref: source}, reason=reason, parent=to_version
    )
