"""브레인 운영실(대시보드) 집계 — 전부 읽기 전용, 지어내는 값 없음.

원천과 정직성 규칙:
- 시험지 커버리지: app.arena.ktib의 자격 술어(eligible_episodes)를 그대로 재사용 —
  커버리지가 실제 KTIB 구성과 다른 기준으로 세면 안 된다. 정답 동률은 집계에서 제외(모호 목록).
- 훈련 커버리지: TRAIN split만, 임베딩 컬럼(Vector 1536)은 절대 끌어오지 않는다(컬럼 지정 select).
- 성능 타임라인: **현행 뇌를 잰 brain run**만, 같은 ktib_version 축 안에서만(§8-2).
  첫 run의 delta는 0.0이 아니라 None — "변화 없음"과 "비교 대상 없음"은 다르다.
- 유입 시계열의 0은 실제 0(그날 도착 없음)이다. 측정 불가 값만 None을 쓴다.

scripts/ktib_coverage.py·scripts/train_coverage.py는 이 모듈을 import하는 thin CLI다.
"""
from __future__ import annotations

from collections import Counter
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.arena.ktib import (
    AmbiguousGoldLabel,
    _gold_intent,
    eligible_episodes,
    latest_ktib,
)
from app.arena.runner import build_outcome
from app.brain.version_gate import current_brain_version
from app.core.config import ExperimentsConfig
from app.core.datasets import BENCHMARK_SPLIT
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.models.arena import RUN_TYPE_BRAIN, ArenaRun
from app.models.benchmark_candidates import (
    BenchmarkCandidateBatch,
    BenchmarkCandidateItem,
)
from app.models.brain import BrainNode
from app.models.episodes import Episode
from app.models.foundry import AtlasExpansionEntry
from app.models.governance import OntologyVersion

TRAIN_SPLIT = "TRAIN"
REJECTED = "REJECTED"

# evidence_stats 버킷(§5-1 구조 상수 — /brain의 _BUCKETS와 동일 정의)
EVIDENCE_BUCKETS = ("synthetic", "weak_behavioral", "human_confirmed", "gold", "expert")
HUMAN_BUCKETS = ("human_confirmed", "gold", "expert")


# --- ktib_global (api/observatory.py에서 이동 — §7-1 중앙 수치의 단일 원천) ---


def ktib_global(session: Session) -> float | None:
    """최신 **현행 뇌 brain run**의 first_intent_accuracy. 없으면 None(측정 전).

    배제: zero_shot_baseline run(밝기 원천 아님 — §8-2), candidate run(`<base>-rcN` —
    reject된 숫자는 이 뇌의 것이 아니다, §6-6 / 절대 규칙 3).
    """
    metrics = session.scalar(
        select(ArenaRun.metrics)
        .where(
            ArenaRun.run_type == RUN_TYPE_BRAIN,
            ArenaRun.model_version == current_brain_version(session),
        )
        .order_by(ArenaRun.created_at.desc())
        .limit(1)
    )
    if not metrics:
        return None
    value = metrics.get("first_intent_accuracy")
    return float(value) if value is not None else None


# --- 시험지 커버리지 (scripts/ktib_coverage.py에서 승격) ---


def _registered_counts(session: Session) -> tuple[Counter, list[str]]:
    """등록 벤치마크 문항을 gold_intent별로 집계. 동률(모호)은 세지 않고 따로 모은다."""
    counts: Counter = Counter()
    ambiguous: list[str] = []
    for ep in eligible_episodes(session):
        try:
            counts[_gold_intent(ep)] += 1
        except AmbiguousGoldLabel:
            ambiguous.append(ep.episode_id)
    return counts, ambiguous


def _pending_counts(session: Session) -> dict[str, int]:
    """아직 등록(REGISTERED)되지 않은 후보 배치의 문항을 intent별로 — 검수 중 물량."""
    rows = session.execute(
        select(BenchmarkCandidateItem.intent_id, func.count())
        .join(
            BenchmarkCandidateBatch,
            BenchmarkCandidateItem.batch_id == BenchmarkCandidateBatch.batch_id,
        )
        .where(BenchmarkCandidateBatch.status != "REGISTERED")
        .group_by(BenchmarkCandidateItem.intent_id)
    ).all()
    return {intent: int(n) for intent, n in rows}


def ktib_coverage_report(session: Session, config: ExperimentsConfig) -> dict:
    """의도별 등록/검수중 시험 문항을 게이트 하한 대비로 정리 (DB 읽기만)."""
    onto = load_ontology()
    domain_of = {i.intent_id: i.domain for i in onto.intents}
    real_intents = [i.intent_id for i in onto.intents if i.domain]
    critical = list(config.arena.critical_intents)
    critical_set = set(critical)
    floor = config.gate.critical_surface_min_items

    registered, ambiguous = _registered_counts(session)
    pending = _pending_counts(session)

    def row(intent: str) -> dict:
        reg = registered.get(intent, 0)
        return {
            "intent": intent,
            "domain": domain_of.get(intent),
            "registered": reg,
            "pending": pending.get(intent, 0),
            "gap_to_floor": max(0, floor - reg),
            "meets_floor": reg >= floor,
        }

    crit_rows = [row(i) for i in critical]
    crit_met = sum(1 for r in crit_rows if r["meets_floor"])
    noncrit_rows = [row(i) for i in real_intents if i not in critical_set]
    measured = sum(1 for r in noncrit_rows if r["registered"] >= 1)

    latest = latest_ktib(session)
    return {
        "floor_critical": floor,
        "critical": {
            "floor": floor,
            "met": crit_met,
            "total": len(crit_rows),
            "ready": crit_met == len(crit_rows),
            "rows": sorted(crit_rows, key=lambda r: (r["registered"], r["intent"])),
        },
        "noncritical": {
            "measured": measured,
            "total": len(noncrit_rows),
            "unmeasured": [r["intent"] for r in noncrit_rows if r["registered"] == 0],
            "rows": sorted(noncrit_rows, key=lambda r: (r["registered"], r["intent"])),
        },
        "registered_total": int(sum(registered.values())),
        "pending_total": int(sum(pending.values())),
        "ambiguous_gold": ambiguous,
        "current_ktib": (
            None
            if latest is None
            else {"version": latest.ktib_version, "episode_count": latest.episode_count}
        ),
    }


# --- 훈련 커버리지 (scripts/train_coverage.py에서 승격) ---


def _top_intent(dist: dict | None) -> str | None:
    """label_distribution의 유일 최댓값. 비었거나 동률이면 None(귀속하지 않는다)."""
    if not dist:
        return None
    top = max(dist.values())
    winners = [i for i, v in dist.items() if v == top]
    return winners[0] if len(winners) == 1 else None


def train_coverage_report(session: Session, config: ExperimentsConfig) -> dict:
    """TRAIN 에피소드를 의도·도메인별로 집계 (임베딩 컬럼은 읽지 않는다)."""
    onto = load_ontology()
    domain_of = {i.intent_id: i.domain for i in onto.intents}
    real_intents = [i.intent_id for i in onto.intents if i.domain]
    gold_target = config.growth.gold_low_threshold

    rows = session.execute(
        select(
            Episode.label_distribution,
            Episode.reliability_tier,
            Episode.label_state,
            Episode.origin_channel,
        ).where(Episode.dataset_split == TRAIN_SPLIT)
    ).all()

    train: Counter = Counter()
    gold: Counter = Counter()
    channels: Counter = Counter()
    ambiguous = 0
    unknown_pool = 0
    rejected = 0

    for dist, tier, state, channel in rows:
        if state == REJECTED:
            rejected += 1
            continue
        channels[channel] += 1
        top = _top_intent(dist)
        if top is None:
            ambiguous += 1
            continue
        if top == UNKNOWN_INTENT_ID:
            unknown_pool += 1
            continue
        train[top] += 1
        if tier == "GOLD":
            gold[top] += 1

    def row(intent: str) -> dict:
        return {
            "intent": intent,
            "domain": domain_of.get(intent),
            "train": train.get(intent, 0),
            "gold": gold.get(intent, 0),
        }

    intent_rows = [row(i) for i in real_intents]
    uncovered = [r["intent"] for r in intent_rows if r["train"] == 0]
    gold_low = [r["intent"] for r in intent_rows if r["gold"] < gold_target]

    domains: dict[str, dict] = {}
    for d in {r["domain"] for r in intent_rows}:
        drows = [r for r in intent_rows if r["domain"] == d]
        domains[d] = {
            "train": sum(r["train"] for r in drows),
            "gold": sum(r["gold"] for r in drows),
            "intents": len(drows),
            "covered": sum(1 for r in drows if r["train"] > 0),
        }

    return {
        "gold_target": gold_target,
        "intents": sorted(intent_rows, key=lambda r: (r["train"], r["intent"])),
        "uncovered": uncovered,
        "gold_low": gold_low,
        "domains": dict(sorted(domains.items())),
        "train_total": int(sum(train.values())),
        "gold_total": int(sum(gold.values())),
        "channels": dict(channels),
        "ambiguous": ambiguous,
        "unknown_pool": unknown_pool,
        "rejected": rejected,
    }


# --- 데이터 유입 스트림 (B 섹션) ---

# (origin_channel, dataset_split) → 스트림. 벤치마크가 우선한다(시험지는 채널 불문 exam).
def _stream_of(channel: str, split: str) -> str | None:
    if split == BENCHMARK_SPLIT:
        return "exam"
    if channel in ("FOUNDRY_SYNTHETIC", "FOUNDRY_AUGMENTED"):
        return "foundry"
    if channel == "GYM_HUMAN":
        return "human_teaching"
    if channel == "PRODUCTION_SHADOW":
        return "shadow"
    return None  # OFFICIAL_CORPUS 등 — v1 스트림 밖(스코어보드 channels에는 표시됨)


STREAMS = ("foundry", "human_teaching", "exam", "shadow")


def inflow_report(session: Session, config: ExperimentsConfig) -> dict:
    """스트림별 총량 + 최근 N일 일별 도착 수(UTC 기준, 0은 실제 0 — 도착 없음).

    '유입(도착)'은 생성된 행 전부다 — 이후 REJECTED된 것도 도착은 했다.
    (사용 가능 총량은 train_coverage_report가 따로 답한다.)
    """
    window_days = config.dashboard.inflow_window_days
    today = datetime.now(UTC).date()
    days: list[date] = [today - timedelta(days=k) for k in range(window_days - 1, -1, -1)]
    cutoff = datetime.combine(days[0], datetime.min.time(), tzinfo=UTC)

    totals = {s: 0 for s in STREAMS}
    for channel, split, n in session.execute(
        select(Episode.origin_channel, Episode.dataset_split, func.count())
        .group_by(Episode.origin_channel, Episode.dataset_split)
    ).all():
        stream = _stream_of(channel, split)
        if stream:
            totals[stream] += int(n)

    day_col = func.date_trunc("day", Episode.created_at).label("day")
    daily = {s: {d: 0 for d in days} for s in STREAMS}
    for channel, split, day, n in session.execute(
        select(Episode.origin_channel, Episode.dataset_split, day_col, func.count())
        .where(Episode.created_at >= cutoff)
        .group_by(Episode.origin_channel, Episode.dataset_split, day_col)
        .order_by(day_col)
    ).all():
        stream = _stream_of(channel, split)
        key = day.date() if hasattr(day, "date") else day
        if stream and key in daily[stream]:
            daily[stream][key] += int(n)

    return {
        stream: {
            "total": totals[stream],
            "last_days": [
                {"day": d.isoformat(), "count": daily[stream][d]} for d in days
            ],
        }
        for stream in STREAMS
    }


# --- 성능 타임라인 & 귀속 (C 섹션) ---


def _inflow_between(session: Session, start: datetime, end: datetime) -> dict:
    """(start, end] 창에 도착한 에피소드 증분 — 귀속의 근사.

    주의: tier는 **현재 시점** 값이다(생성 후 GOLD 승급분 포함) — created_at 귀속의 근사임을
    소비자(대시보드 문구)가 알린다.
    """
    train_n, gold_n, bench_n = session.execute(
        select(
            func.count().filter(Episode.dataset_split == TRAIN_SPLIT),
            func.count().filter(Episode.reliability_tier == "GOLD"),
            func.count().filter(Episode.dataset_split == BENCHMARK_SPLIT),
        ).where(Episode.created_at > start, Episode.created_at <= end)
    ).one()
    return {
        "train_episodes": int(train_n),
        "gold": int(gold_n),
        "benchmark_episodes": int(bench_n),
    }


def run_timeline_report(session: Session, config: ExperimentsConfig) -> dict:
    """현행 뇌의 같은 축(ktib_version) 최근 run 창 + run 간 델타·유입 귀속.

    stage4_inputs(§7-6)와 같은 축 규칙: brain run ∧ model_version=현행 ∧ 최신 run의
    ktib_version. baseline·candidate run은 구조적으로 걸러진다.
    """
    brain_version = current_brain_version(session)
    latest = session.scalar(
        select(ArenaRun)
        .where(
            ArenaRun.run_type == RUN_TYPE_BRAIN,
            ArenaRun.model_version == brain_version,
        )
        .order_by(ArenaRun.created_at.desc())
        .limit(1)
    )
    if latest is None:
        return {"axis": None, "runs": [], "attribution_ready": False}

    window = config.dashboard.run_timeline_window
    recent = list(session.scalars(
        select(ArenaRun)
        .where(
            ArenaRun.run_type == RUN_TYPE_BRAIN,
            ArenaRun.model_version == brain_version,
            ArenaRun.ktib_version == latest.ktib_version,  # §8-2 같은 축만
        )
        .order_by(ArenaRun.created_at.desc())
        .limit(window)
    ))
    runs = list(reversed(recent))  # 오래된 순

    out: list[dict] = []
    prev: ArenaRun | None = None
    for run in runs:
        metrics = run.metrics or {}
        acc = metrics.get("first_intent_accuracy")
        prev_acc = (prev.metrics or {}).get("first_intent_accuracy") if prev else None
        # 첫 run이거나 어느 쪽이 미측정이면 delta는 None — 0.0(변화 없음)으로 위장하지 않는다.
        # (build_outcome의 0.0은 promote 차단용 의미론이라 여기 쓰지 않는다.)
        delta_pp = (
            None
            if prev is None or acc is None or prev_acc is None
            else round((acc - prev_acc) * 100, 1)
        )
        outcome = build_outcome(run, prev, config) if prev is not None else None
        out.append({
            "run_id": run.run_id,
            "created_at": run.created_at,
            "accuracy": acc,
            "item_count": metrics.get("item_count"),
            "ece": metrics.get("ece"),
            "delta_pp": delta_pp,
            "inflow_since_prev": (
                _inflow_between(session, prev.created_at, run.created_at)
                if prev is not None
                else None
            ),
            "region_regressions": outcome.region_regressions if outcome else [],
            "critical_worse": outcome.critical_worse if outcome else [],
            "critical": metrics.get("critical"),
        })
        prev = run

    return {
        "axis": {"ktib_version": latest.ktib_version, "model_version": brain_version},
        "runs": out,
        "attribution_ready": len(out) >= 2,
    }


# --- 확장 스토리 (D 섹션) ---


def expansion_report(session: Session, train_report: dict) -> dict:
    """의도 수·예시 수는 현재 온톨로지에서, 확장 신호는 실제 큐·버전 이력에서만.

    버전별 과거 예시 수 '이력'은 DB에 없다 — 버전 행 + 현재 값만 보고한다(날조 금지).
    """
    onto = load_ontology()
    real = [i for i in onto.intents if i.domain]
    pending = session.scalar(
        select(func.count())
        .select_from(AtlasExpansionEntry)
        .where(AtlasExpansionEntry.status == "PENDING")
    )
    versions = list(session.scalars(
        select(OntologyVersion).order_by(OntologyVersion.created_at)
    ))
    return {
        "intent_count": len(real),
        "positive_examples_total": sum(len(i.positive_examples) for i in real),
        "ontology_version": onto.version,
        "unknown_pool": train_report["unknown_pool"],
        "ambiguous": train_report["ambiguous"],
        "atlas_queue_pending": int(pending or 0),
        "ontology_versions": [
            {"version": v.version, "change_type": v.change_type, "created_at": v.created_at}
            for v in versions
        ],
    }


# --- 검수함 (E 섹션) ---


def review_inbox_report(session: Session) -> list[dict]:
    """후보 배치 전 상태(최신순) — REGISTERED는 동결 표기용으로만 나온다."""
    counts = dict(session.execute(
        select(BenchmarkCandidateItem.batch_id, func.count())
        .group_by(BenchmarkCandidateItem.batch_id)
    ).all())
    batches = list(session.scalars(
        select(BenchmarkCandidateBatch).order_by(BenchmarkCandidateBatch.created_at.desc())
    ))
    return [
        {
            "batch_id": b.batch_id,
            "created_by": b.created_by,
            "status": b.status,
            "item_count": int(counts.get(b.batch_id, 0)),
            "agreement_kappa": b.agreement_kappa,
            "ktib_version": b.ktib_version,
            "created_at": b.created_at,
        }
        for b in batches
    ]


# --- 의도별 세부 (F 섹션) ---


def intent_rows(
    session: Session,
    config: ExperimentsConfig,
    ktib_report: dict,
    train_report: dict,
) -> list[dict]:
    """의도 63행 — 시험/공부/예시/정확도를 한 줄에. 측정 전 정확도는 None 그대로."""
    onto = load_ontology()
    examples = {i.intent_id: len(i.positive_examples) for i in onto.intents if i.domain}
    critical_set = set(config.arena.critical_intents)

    exam_rows = {
        r["intent"]: r
        for r in ktib_report["critical"]["rows"] + ktib_report["noncritical"]["rows"]
    }
    train_rows = {r["intent"]: r for r in train_report["intents"]}

    nodes = {
        intent: (heldout, stats or {})
        for intent, heldout, stats in session.execute(
            select(BrainNode.intent_id, BrainNode.heldout_accuracy, BrainNode.evidence_stats)
        ).all()
    }

    rows: list[dict] = []
    for i in onto.intents:
        if not i.domain:
            continue
        exam = exam_rows.get(i.intent_id, {})
        train = train_rows.get(i.intent_id, {})
        heldout, stats = nodes.get(i.intent_id, (None, {}))
        is_critical = i.intent_id in critical_set
        rows.append({
            "intent_id": i.intent_id,
            "region": i.domain,
            "is_critical": is_critical,
            "exam_registered": exam.get("registered", 0),
            "exam_pending": exam.get("pending", 0),
            # 하한은 CRITICAL에만 존재한다 — 비critical에 갭을 지어내지 않는다
            "gap_to_floor": exam.get("gap_to_floor") if is_critical else None,
            "train": train.get("train", 0),
            "gold": train.get("gold", 0),
            "positive_examples": examples.get(i.intent_id, 0),
            "heldout_accuracy": heldout,
            "evidence_total": int(sum(int(stats.get(b, 0) or 0) for b in EVIDENCE_BUCKETS)),
        })
    return rows


# --- 스코어보드 보조 (A 섹션) ---


def human_evidence_totals(session: Session) -> dict[str, int]:
    """사람 손을 탄 증거 버킷 합(노드 evidence_stats 롤업) — 사람 가르침 카드 원천."""
    totals = {b: 0 for b in HUMAN_BUCKETS}
    for (stats,) in session.execute(select(BrainNode.evidence_stats)).all():
        for b in HUMAN_BUCKETS:
            totals[b] += int((stats or {}).get(b, 0) or 0)
    return totals


def awaiting_batches_count(session: Session) -> int:
    return int(session.scalar(
        select(func.count())
        .select_from(BenchmarkCandidateBatch)
        .where(BenchmarkCandidateBatch.status == "AWAITING_SECOND")
    ) or 0)
