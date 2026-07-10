"""Phase 5 완료 / Live-rollout 준비 게이트 (§10-2) — **읽기 전용 리포트**.

§10-2 부활 트리거: `KTIB First Intent Accuracy ≥ 80% ∧ CWAR 기준 충족 2주 유지`.
2026-07-10 확정된 4지표 게이트:

| 레그 | 지표 | 성격 |
|---|---|---|
| 1 | First Intent Accuracy ≥ `arena.first_intent_accuracy_target` | 능력 |
| 2 | CWAR-fire ≤ `cwar_max` ∧ CWAR-miss ≤ `cwar_miss_max` ∧ CCC ≥ `ccc_min` | **안전** |
| 3 | 1-Turn Recovery ≥ `gate.recovery_min` | 품질 |
| 4 | 활성 prior 클러스터 중 Harm−Lift > `gate.persona_harm_margin`인 것이 없음 | 품질·안전 |

**PARTIAL HOLD 준수:** 이 모듈은 어떤 서빙 경로도 켜지 않는다. §10-2 트리거 도달 여부를
**보고**할 뿐이고, live rollout은 사람 협의 소관이다(CLAUDE.md).

**결정성:** 네 지표는 전부 `run_arena()`가 run 시점에 계산해 `arena_runs.metrics`에 동결한
값이다. 이 게이트는 **저장값만 읽는다** — 게이트 시점에 live config/DB로 재계산하면 config를
고치는 것만으로 과거 판정이 바뀌어 replay가 무너진다. (임계값 비교만 오늘의 config로 한다.)

**null 정직성 비대칭:**
- 안전 레그: critical 표면이 존재(`o_count > 0`)하는데 지표가 null이면 **FAIL**.
  측정하지 못한 안전은 안전이 아니다. 표면 자체가 없으면(`o_count == 0`) N/A + 큰 경고.
- 품질 레그: clarify가 하나도 없으면 Recovery는 N/A(WAIVE) — 측정 대상이 없는 것과 나쁜 것은 다르다.
- 어느 경우에도 null을 0%나 100%로 렌더하지 않는다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import ExperimentsConfig
from app.models.arena import RUN_TYPE_BRAIN, ArenaRun

PASS, FAIL, NA = "PASS", "FAIL", "N/A"


@dataclass
class LegResult:
    name: str
    status: str            # PASS | FAIL | N/A
    reasons: list[str] = field(default_factory=list)
    values: dict = field(default_factory=dict)


@dataclass
class RunVerdict:
    run_id: str
    passed: bool
    legs: list[LegResult]
    warnings: list[str] = field(default_factory=list)


@dataclass
class LiveReadiness:
    """§10-2 준비도. `ready`는 '연속 sustained_runs개 run이 모두 통과'일 때만 True."""

    ready: bool
    sustained_runs_required: int
    runs_evaluated: int
    ktib_version: str | None
    verdicts: list[RunVerdict] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)


def _leg_accuracy(metrics: dict, config: ExperimentsConfig) -> LegResult:
    acc = metrics.get("first_intent_accuracy")
    target = config.arena.first_intent_accuracy_target
    if acc is None:
        return LegResult("first_intent_accuracy", FAIL, ["미측정(null) — 능력을 주장할 수 없다"])
    ok = acc >= target
    return LegResult(
        "first_intent_accuracy", PASS if ok else FAIL,
        [] if ok else [f"{acc:.4f} < 목표 {target}"], {"accuracy": acc, "target": target},
    )


def _leg_safety(metrics: dict, config: ExperimentsConfig) -> LegResult:
    """CWAR 양방향 + Critical Commit Coverage. 미측정 안전은 안전이 아니다."""
    crit = metrics.get("critical") or {}
    g = config.gate
    o_count = int(crit.get("o_count", 0) or 0)
    values = {k: crit.get(k) for k in
              ("cwar_fire", "cwar_fire_n", "cwar_miss", "ccc", "o_count", "critical_set_size")}

    if not crit.get("critical_set_size"):
        return LegResult("critical_safety", FAIL,
                         ["critical 집합이 비어 있다 — 안전 지표가 무의미하다"], values)
    if o_count == 0:
        # 벤치마크에 critical 정답이 하나도 없다. 조용히 통과시키지 않는다.
        return LegResult("critical_safety", NA,
                         ["KTIB에 critical intent 정답 아이템이 없다 — 안전 미측정"], values)

    reasons: list[str] = []
    if o_count < g.critical_surface_min_items:
        reasons.append(
            f"critical 표면 {o_count} < 표본 하한 {g.critical_surface_min_items} — 미측정"
        )

    fire, fire_n = crit.get("cwar_fire"), int(crit.get("cwar_fire_n", 0) or 0)
    if fire is None or fire_n < g.cwar_min_items:
        reasons.append(
            f"CWAR-fire 미측정(커밋한 critical {fire_n} < 하한 {g.cwar_min_items})"
        )
    elif fire > g.cwar_max:
        reasons.append(f"CWAR-fire {fire:.4f} > 상한 {g.cwar_max}")

    miss = crit.get("cwar_miss")
    if miss is None:
        reasons.append("CWAR-miss 미측정")
    elif miss > g.cwar_miss_max:
        reasons.append(f"CWAR-miss {miss:.4f} > 상한 {g.cwar_miss_max}")

    ccc = crit.get("ccc")
    if ccc is None:
        reasons.append("Critical Commit Coverage 미측정")
    elif ccc < g.critical_commit_coverage_min:
        reasons.append(
            f"CCC {ccc:.4f} < 하한 {g.critical_commit_coverage_min} — "
            f"critical을 clarify/abstain으로 흘리고 있다"
        )
    return LegResult("critical_safety", FAIL if reasons else PASS, reasons, values)


def _leg_recovery(metrics: dict, config: ExperimentsConfig) -> LegResult:
    rec = metrics.get("recovery")
    floor = config.gate.recovery_min_clarify
    if rec is None:
        return LegResult("recovery", NA, ["clarify가 없다 — 복구 품질 측정 대상 없음"])
    denom = int(rec.get("denominator", 0) or 0)
    if denom < floor:
        return LegResult("recovery", NA, [f"clarify {denom} < 표본 하한 {floor}"], dict(rec))
    rate = rec["rate"]
    ok = rate >= config.gate.recovery_min
    return LegResult("recovery", PASS if ok else FAIL,
                     [] if ok else [f"{rate:.4f} < 하한 {config.gate.recovery_min}"], dict(rec))


def _leg_persona(metrics: dict, config: ExperimentsConfig) -> LegResult:
    """§4-2: Harm > Lift인 클러스터가 있으면 안 된다. 표본 미달 클러스터는 FAIL(미측정≠안전)."""
    personas = metrics.get("persona")
    if not personas:
        return LegResult("persona_safety", NA, ["persona 클러스터 없음 — 측정 대상 없음"])
    reasons: list[str] = []
    for cluster, m in sorted(personas.items()):
        if m.get("sample_below_floor"):
            reasons.append(
                f"{cluster}: 표본 {m['n']} < 하한 {config.gate.persona_eval_min_items} — "
                f"활성 prior인데 Harm/Lift를 신뢰할 수 없다"
            )
        elif (m["harm"] - m["lift"]) > config.gate.persona_harm_margin:
            reasons.append(
                f"{cluster}: Harm {m['harm']:.4f} − Lift {m['lift']:.4f} > "
                f"margin {config.gate.persona_harm_margin} (비활성화 권고)"
            )
    return LegResult("persona_safety", FAIL if reasons else PASS, reasons, dict(personas))


def evaluate_run(run: ArenaRun, config: ExperimentsConfig) -> RunVerdict:
    """run 하나의 4레그 판정. `metrics`에 동결된 값만 읽는다."""
    metrics = run.metrics or {}
    legs = [
        _leg_accuracy(metrics, config),
        _leg_safety(metrics, config),
        _leg_recovery(metrics, config),
        _leg_persona(metrics, config),
    ]
    warnings = [
        f"{leg.name}: {'; '.join(leg.reasons)}" for leg in legs if leg.status == NA
    ]
    # 능력·안전 레그가 PASS가 아니면 통과 불가. 품질 레그는 N/A면 WAIVE.
    capability = next(leg for leg in legs if leg.name == "first_intent_accuracy")
    safety = next(leg for leg in legs if leg.name == "critical_safety")
    passed = (
        capability.status == PASS
        and safety.status == PASS
        and all(leg.status != FAIL for leg in legs)
    )
    return RunVerdict(run_id=run.run_id, passed=passed, legs=legs, warnings=warnings)


def evaluate_live_readiness(session: Session, config: ExperimentsConfig) -> LiveReadiness:
    """최근 `gate.sustained_runs`개 연속 brain run(동일 ktib_version)이 모두 통과해야 ready.

    §10-2 "2주 유지" = `arena.schedule=weekly`일 때 sustained_runs=2. 어떤 서빙 경로도 켜지 않는다.
    """
    required = config.gate.sustained_runs
    latest = session.scalar(
        select(ArenaRun)
        .where(ArenaRun.run_type == RUN_TYPE_BRAIN)
        .order_by(ArenaRun.created_at.desc())
        .limit(1)
    )
    if latest is None:
        return LiveReadiness(
            ready=False, sustained_runs_required=required, runs_evaluated=0, ktib_version=None,
            blockers=["brain arena run이 하나도 없다"],
        )

    runs = list(session.scalars(
        select(ArenaRun)
        .where(
            ArenaRun.run_type == RUN_TYPE_BRAIN,
            ArenaRun.ktib_version == latest.ktib_version,  # 신·구 벤치마크를 섞지 않는다(§8-2)
        )
        .order_by(ArenaRun.created_at.desc())
        .limit(required)
    ))
    verdicts = [evaluate_run(r, config) for r in runs]
    blockers: list[str] = []
    if len(runs) < required:
        blockers.append(
            f"동일 ktib_version({latest.ktib_version}) brain run {len(runs)} < 유지 요건 {required}"
        )
    blockers += [
        f"{v.run_id}: {leg.name} — {'; '.join(leg.reasons)}"
        for v in verdicts for leg in v.legs if leg.status == FAIL
    ]
    warnings = [f"{v.run_id}: {w}" for v in verdicts for w in v.warnings]

    return LiveReadiness(
        ready=len(runs) >= required and all(v.passed for v in verdicts),
        sustained_runs_required=required,
        runs_evaluated=len(runs),
        ktib_version=latest.ktib_version,
        verdicts=verdicts,
        blockers=blockers,
        warnings=warnings,
    )
