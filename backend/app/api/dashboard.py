"""GET /v1/observatory/dashboard — 브레인 운영실(대시보드) 단일 집계 (읽기 전용).

무엇도 여기서 계산으로 지어내지 않는다 — 전 값이 app.observatory.aggregate의 실측 집계다.
- 실력(ktib_global·stage)은 **여기 없다**: /brain이 단일 원천이고 프론트 store가 이미 갖는다.
- 기준선(게이트 하한·목표)은 config에서 그대로 동봉한다 — 프론트 하드코딩 금지(절대 규칙 1).
- 측정 전·비교 불가 값은 null이다. 유입 시계열의 0만이 실제 0(그날 도착 없음)이다.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.config import ExperimentsConfig, get_config
from app.core.db import get_session
from app.observatory import aggregate

router = APIRouter(prefix="/v1/observatory", tags=["observatory"])


def _get_experiments() -> ExperimentsConfig:
    return get_config()


class DashboardConfigOut(BaseModel):
    """프론트가 표시할 기준선 — 전부 config/experiments.yaml 원천 (절대 규칙 1)."""

    critical_surface_min_items: int
    gold_low_threshold: int
    first_intent_accuracy_target: float
    min_agreement_kappa: float


class CurrentKtibOut(BaseModel):
    version: str
    episode_count: int


class ScoreboardOut(BaseModel):
    ktib_registered_total: int
    ktib_pending_total: int
    critical_met: int
    critical_total: int
    current_ktib: CurrentKtibOut | None
    train_total: int
    gold_total: int
    channels: dict[str, int]
    human_evidence: dict[str, int]
    review_awaiting_batches: int


class DailyCount(BaseModel):
    day: str
    count: int


class StreamOut(BaseModel):
    total: int
    last_days: list[DailyCount]


class InflowOut(BaseModel):
    foundry: StreamOut
    human_teaching: StreamOut
    exam: StreamOut
    shadow: StreamOut


class InflowDeltaOut(BaseModel):
    train_episodes: int
    gold: int
    benchmark_episodes: int


class RunPointOut(BaseModel):
    run_id: str
    created_at: datetime
    accuracy: float | None
    item_count: int | None
    ece: float | None
    delta_pp: float | None            # 첫 run·미측정이면 null — 0.0으로 위장하지 않는다
    inflow_since_prev: InflowDeltaOut | None
    region_regressions: list[str]
    critical_worse: list[str]
    critical: dict | None


class AxisOut(BaseModel):
    ktib_version: str
    model_version: str


class PerformanceOut(BaseModel):
    axis: AxisOut | None
    runs: list[RunPointOut]
    attribution_ready: bool           # run ≥ 2 — 미만이면 귀속은 "측정 전"


class OntologyVersionOut(BaseModel):
    version: str
    change_type: str | None
    created_at: datetime | None


class ExpansionOut(BaseModel):
    intent_count: int
    positive_examples_total: int
    ontology_version: str
    unknown_pool: int
    ambiguous: int
    atlas_queue_pending: int
    ontology_versions: list[OntologyVersionOut]


class ReviewBatchOut(BaseModel):
    batch_id: str
    created_by: str
    status: str
    item_count: int
    agreement_kappa: float | None
    ktib_version: str | None
    created_at: datetime | None


class IntentRowOut(BaseModel):
    intent_id: str
    region: str
    is_critical: bool
    exam_registered: int
    exam_pending: int
    gap_to_floor: int | None          # CRITICAL만 값 — 비critical엔 하한이 없다
    train: int
    gold: int
    positive_examples: int
    heldout_accuracy: float | None    # 측정 전 null
    evidence_total: int


class DashboardOut(BaseModel):
    config: DashboardConfigOut
    scoreboard: ScoreboardOut
    inflow: InflowOut
    performance: PerformanceOut
    expansion: ExpansionOut
    review_inbox: list[ReviewBatchOut]
    intents: list[IntentRowOut]


@router.get("/dashboard", response_model=DashboardOut)
def dashboard(
    session: Session = Depends(get_session),
    config: ExperimentsConfig = Depends(_get_experiments),
) -> DashboardOut:
    ktib_report = aggregate.ktib_coverage_report(session, config)
    train_report = aggregate.train_coverage_report(session, config)

    return DashboardOut(
        config=DashboardConfigOut(
            critical_surface_min_items=config.gate.critical_surface_min_items,
            gold_low_threshold=config.growth.gold_low_threshold,
            first_intent_accuracy_target=config.arena.first_intent_accuracy_target,
            min_agreement_kappa=config.review.min_agreement_kappa,
        ),
        scoreboard=ScoreboardOut(
            ktib_registered_total=ktib_report["registered_total"],
            ktib_pending_total=ktib_report["pending_total"],
            critical_met=ktib_report["critical"]["met"],
            critical_total=ktib_report["critical"]["total"],
            current_ktib=ktib_report["current_ktib"],
            train_total=train_report["train_total"],
            gold_total=train_report["gold_total"],
            channels=train_report["channels"],
            human_evidence=aggregate.human_evidence_totals(session),
            review_awaiting_batches=aggregate.awaiting_batches_count(session),
        ),
        inflow=InflowOut(**aggregate.inflow_report(session, config)),
        performance=PerformanceOut(**aggregate.run_timeline_report(session, config)),
        expansion=ExpansionOut(**aggregate.expansion_report(session, train_report)),
        review_inbox=aggregate.review_inbox_report(session),
        intents=aggregate.intent_rows(session, config, ktib_report, train_report),
    )
