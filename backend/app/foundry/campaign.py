"""10k~30k 생성 캠페인 — 도메인 배분 + 주간 품질 리포트 + Pilot 대비 악화 시 자동 중단.

T2.5 (§10-2 Phase 2, §1-14 기준선). T2.1 배치 러너(run_batch) 위의 오케스트레이터다.

- **도메인 배분**: config.campaign.domain_weights(DOCUMENT+VISUAL 우선)를 길이 N 스케줄로
  강제한다. 슬롯 i → schedule[i]라 run_batch의 라운드로빈이 그대로 배분을 따르고,
  재시작해도 슬롯의 도메인이 고정된다(스케줄이 target_n에만 의존).
- **주간 품질 리포트**: window_batches개 배치마다 품질 윈도를 만든다. 합성 생성엔 벽시계
  시간이 없으므로 'window_batches개 배치 = 한 주(週) 리포트'로 해석한다.
- **자동 중단(§1-14)**: 윈도의 합의도 하락·reject율 상승·단가 상승 중 하나라도 기준선 대비
  악화하면 다음 배치를 시작하지 않는다. 체크포인트가 커밋돼 있어 재개는 안전하다.

단가는 합성 provider의 cost_usd=0이라 unit_tokens(비용 동인, 항상 >0)로 게이트하고,
unit_cost(실 vendor에서 >0)는 리포트에 병기한다.

이 모듈은 데이터 생성만 한다 — 노드 brightness에 접근하지 않는다(절대 규칙 3).
"""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import ExperimentsConfig
from app.core.ontology import CANONICAL_DOMAINS
from app.foundry.batch import (
    BatchCost,
    BatchReport,
    Scenario,
    existing_slot_hashes,
    run_batch,
)
from app.foundry.pilot import PilotResult
from app.foundry.seed_expansion import variants_for_domain
from app.foundry.situation_seeds import load_situation_seeds
from app.foundry.stages.s1_discovery import SourceCandidate, register_source
from app.foundry.stages.s2_governance import govern_source, store_raw_document
from app.foundry.stages.s3_extractor import FrameInput, build_situation_frame
from app.foundry.stages.s5_situation_builder import build_scenarios
from app.llm.client import LLMClient
from app.models.episodes import Episode

EmbedFn = Callable[[list[str]], list[list[float]]]

_DEFAULT_PERSONAS = ["P_hypo_1", "P_active_2", "P_struct_3"]

# 도메인별 소스 클래스 (다양성; S1 후보의 source_class는 3종 고정 서열이 아니다)
_SOURCE_CLASS_BY_DOMAIN = {
    "DOCUMENT": "AUTHORITY",
    "VISUAL": "PRACTICE",
    "PLAY": "PRACTICE",
    "OBSERVATION": "PRACTICE",
    "COMMUNICATION": "TEACHER_LANGUAGE",
    "OPERATION": "AUTHORITY",
    "REFLECTION": "TEACHER_LANGUAGE",
    "STUDIO": "PRACTICE",  # onto-2.0 — 자료 만들기 요청은 현장 실무 발화 계열
}


# --- Pilot 기준선 (§1-14) ---


@dataclass
class PilotBaseline:
    """캠페인 품질을 견주는 Pilot 기준선. '악화'는 이 값 대비 나빠짐을 뜻한다."""

    mean_consensus: float
    reject_rate: float
    unit_tokens: float
    unit_cost: float

    @classmethod
    def from_pilot(cls, result: PilotResult) -> PilotBaseline:
        n = result.report.episodes or 0
        return cls(
            mean_consensus=result.report.mean_consensus,
            reject_rate=result.report.judge_reject_rate,
            unit_tokens=(result.manifest.total_tokens() / n) if n else 0.0,
            unit_cost=(result.manifest.total_cost() / n) if n else 0.0,
        )

    def as_dict(self) -> dict:
        return {
            "mean_consensus": round(self.mean_consensus, 4),
            "reject_rate": round(self.reject_rate, 4),
            "unit_tokens": round(self.unit_tokens, 2),
            "unit_cost": round(self.unit_cost, 6),
        }


def baseline_from_run(session: Session, run_id: str) -> PilotBaseline:
    """중단된 캠페인 재개용 기준선 — 이 run이 이미 만든 에피소드의 실측(DB)에서 복원한다.

    2026-07-17 감사: CLI가 매번 새 run_id를 만들어 '재시작 멱등'이 실제로는 불가능했다
    (camp_06f8128c가 미완으로 남은 원인). 토큰 단가는 DB에 없어 0으로 둔다 —
    _evaluate_window의 0-기준선 가드가 비용 악화 검사를 건너뛴다(합의도·reject 게이트는 유지).
    """
    rows = session.execute(
        select(Episode.label_state, Episode.consensus).where(
            Episode.episode_id.like(f"EP_{run_id}\\_%"),
            # 기준선 파일럿(run_id + '_base')은 캠페인 실측이 아니다 — 오포함 방지(적대 검증)
            Episode.episode_id.not_like(f"EP_{run_id}\\_base%"),
        )
    ).all()
    if not rows:
        raise ValueError(f"재개할 run 이력이 없음: {run_id} (에피소드 0건)")
    total = len(rows)
    rejected = sum(1 for state, _ in rows if state == "REJECTED")
    consensus_vals = [c for state, c in rows if state != "REJECTED" and c is not None]
    mean_consensus = sum(consensus_vals) / len(consensus_vals) if consensus_vals else 0.0
    return PilotBaseline(
        mean_consensus=mean_consensus, reject_rate=rejected / total,
        unit_tokens=0.0, unit_cost=0.0,
    )


# --- 도메인 배분 스케줄 ---


@dataclass
class CampaignSchedule:
    scenarios: list[Scenario]     # 길이 == target_n; 슬롯 i → scenarios[i]
    slot_domains: list[str]       # 슬롯별 도메인 (scenarios와 병렬)
    allocation: dict[str, float]  # 실제 배분 비율 (도메인 → 분율)


def _apportion(target_n: int, weights: dict[str, float]) -> dict[str, int]:
    """target_n을 가중치대로 도메인에 배정(최대잔여법). N ≥ 도메인 수면 각 도메인 최소 1."""
    domains = sorted(weights)  # 결정론적 순서
    k = len(domains)
    if target_n <= k:
        ordered = sorted(domains, key=lambda d: weights[d], reverse=True)
        return {d: (1 if idx < target_n else 0) for idx, d in enumerate(ordered)}
    rest = target_n - k
    raw = {d: weights[d] * rest for d in domains}
    floor = {d: int(raw[d]) for d in domains}
    assigned = sum(floor.values())
    remainder = sorted(domains, key=lambda d: raw[d] - floor[d], reverse=True)
    for d in remainder[: rest - assigned]:
        floor[d] += 1
    return {d: 1 + floor[d] for d in domains}


def _planned_counts_and_allocation(
    config: ExperimentsConfig, target_n: int
) -> tuple[dict[str, int], dict[str, float]]:
    """도메인명 검증 + 슬롯 배정(counts) + 실제 배분 비율(allocation)을 순수 계산한다 (DB 무관).

    interleave가 도메인 d를 정확히 counts[d]회 방출하므로 allocation은 counts로부터 곧바로
    나온다 — 전량 완료 재시작의 no-op 리포트가 DB 없이도 배분을 보고할 수 있게 한다.
    """
    weights = config.campaign.domain_weights
    if set(weights) != set(CANONICAL_DOMAINS):
        raise ValueError(f"campaign.domain_weights 도메인이 정본과 다름: {sorted(weights)}")
    counts = _apportion(target_n, weights)
    total = sum(counts.values()) or 1
    allocation = {d: counts.get(d, 0) / total for d in CANONICAL_DOMAINS}
    return counts, allocation


def _interleave(
    counts: dict[str, int], scen_by_domain: dict[str, list[Scenario]]
) -> tuple[list[Scenario], list[str]]:
    """counts를 도메인별로 고르게 분산(가중 라운드로빈). 슬롯 시나리오·도메인을 병렬 반환."""
    remaining = dict(counts)
    order = sorted(counts, key=lambda d: counts[d], reverse=True)  # 큰 것부터 매 패스 1개
    cursor = {d: 0 for d in counts}
    total = sum(counts.values())
    scenarios: list[Scenario] = []
    slot_domains: list[str] = []
    while len(scenarios) < total:
        for d in order:
            if remaining[d] > 0:
                pool = scen_by_domain[d]
                scenarios.append(pool[cursor[d] % len(pool)])
                slot_domains.append(d)
                cursor[d] += 1
                remaining[d] -= 1
                if len(scenarios) >= total:
                    break
    return scenarios, slot_domains


def prepare_campaign_scenarios(
    session: Session, *, run_id: str, config: ExperimentsConfig, target_n: int,
    llm_client: LLMClient | None = None, model: str = "campaign",
) -> CampaignSchedule:
    """7개 도메인 소스·프레임·시나리오를 준비하고, 배분 가중치대로 길이 target_n 스케줄을 만든다.

    llm_client가 있고 config.foundry.seed_expansion_enabled면 씨드를 LLM으로 확장한다
    (앵커 = 최소기준 충족 씨드, 실패 시 씨드 원본 폴백) — 없으면 씨드 원본 그대로.
    """
    counts, allocation = _planned_counts_and_allocation(config, target_n)

    seed_file = load_situation_seeds()  # 화면 씨드(수동 작성) — 계약 위반이면 증산 시작 전 실패
    scen_by_domain: dict[str, list[Scenario]] = {}
    for domain in CANONICAL_DOMAINS:
        source = register_source(
            session,
            SourceCandidate(
                source_class=_SOURCE_CLASS_BY_DOMAIN[domain],
                title=f"캠페인 소스 {domain} ({run_id})",
                discovery_reason=f"{domain} 도메인 커버리지",
                access="official_corpus",
            ),
        )
        govern_source(session, source.source_id, "ALLOW", reviewed_by="campaign")
        store_raw_document(session, source.source_id, f"[campaign raw {run_id} {domain}]")
        frame = build_situation_frame(
            session,
            FrameInput(
                domain=domain, summary=f"{domain} 상황 프레임 ({run_id})",
                teacher_concern="개입 시점과 방식", extraction_confidence=0.8,
            ),
        )
        session.flush()
        variants = variants_for_domain(
            seed_file, domain=domain, k=config.foundry.scenario_variants,
            salt=f"{run_id}|{domain}", llm_client=llm_client, model=model,
            enabled=config.foundry.seed_expansion_enabled,
        )
        scen_by_domain[domain] = [
            (sc.scenario_id, frame.frame_id, source.source_id)
            for sc in build_scenarios(session, frame, variants, config)
        ]
    session.flush()

    # 빈 풀 가드: count>0인 도메인에 시나리오가 없으면 조용한 ZeroDivision 대신 명확히 실패
    for domain, count in counts.items():
        if count > 0 and not scen_by_domain.get(domain):
            raise ValueError(f"도메인 {domain}의 시나리오 풀이 비어 count={count}를 배치할 수 없음")

    scenarios, slot_domains = _interleave(counts, scen_by_domain)
    return CampaignSchedule(scenarios=scenarios, slot_domains=slot_domains, allocation=allocation)


# --- 주간 품질 리포트 + 게이트 ---


@dataclass
class WeeklyReport:
    week_index: int
    created: int
    attempted: int
    rejected: int
    mean_consensus: float
    reject_rate: float
    unit_tokens: float
    unit_cost: float
    consensus_delta: float    # 윈도 − 기준선 (음수 = 악화)
    reject_delta: float       # 윈도 − 기준선 (양수 = 악화)
    unit_tokens_ratio: float  # 윈도 / 기준선
    degraded: bool
    reasons: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "week_index": self.week_index,
            "created": self.created,
            "attempted": self.attempted,
            "rejected": self.rejected,
            "mean_consensus": round(self.mean_consensus, 4),
            "reject_rate": round(self.reject_rate, 4),
            "unit_tokens": round(self.unit_tokens, 2),
            "unit_cost": round(self.unit_cost, 6),
            "consensus_delta": round(self.consensus_delta, 4),
            "reject_delta": round(self.reject_delta, 4),
            "unit_tokens_ratio": round(self.unit_tokens_ratio, 3),
            "degraded": self.degraded,
            "reasons": list(self.reasons),
        }


def _evaluate_window(
    week_index: int,
    batches: list[BatchCost],
    baseline: PilotBaseline,
    config: ExperimentsConfig,
) -> WeeklyReport:
    """한 윈도(배치들)의 품질을 기준선과 비교해 악화 여부를 판정한다 (§1-14)."""
    created = sum(b.created for b in batches)
    attempted = sum(b.attempted for b in batches)
    rejected = sum(b.rejected for b in batches)
    accepted = created - rejected
    consensus_sum = sum(b.consensus_sum for b in batches)
    tokens = sum(b.tokens for b in batches)
    cost = sum(b.cost_usd for b in batches)

    mean_consensus = (consensus_sum / accepted) if accepted else 0.0
    reject_rate = (rejected / created) if created else 0.0
    # 단가는 시도당(created+failed) — 실패로 낭비된 호출 비용까지 반영한다. 기준선(Pilot)은
    # 실패가 없어 분모가 created지만, 실패가 있는 윈도는 그만큼 단가가 오르는 게 정직하다
    # (실패율 상승 = 실제 비용 상승이므로 보수적으로 잡히는 것이 맞다).
    unit_tokens = (tokens / attempted) if attempted else 0.0
    unit_cost = (cost / attempted) if attempted else 0.0

    cfg = config.campaign
    reasons: list[str] = []
    if created == 0:
        reasons.append("no_output")  # 윈도 전량 실패 — 산출 없음
    # accept분이 있어야 합의도 하락을 논한다 (전량 reject면 reject_rise가 잡는다)
    if accepted > 0 and mean_consensus < baseline.mean_consensus - cfg.consensus_drop_max:
        reasons.append("consensus_drop")
    if reject_rate > baseline.reject_rate + cfg.reject_rise_max:
        reasons.append("reject_rise")
    if baseline.unit_tokens > 0 and unit_tokens > baseline.unit_tokens * (
        1.0 + cfg.unit_cost_rise_ratio
    ):
        reasons.append("unit_cost_rise")

    ratio = (unit_tokens / baseline.unit_tokens) if baseline.unit_tokens else 0.0
    return WeeklyReport(
        week_index=week_index, created=created, attempted=attempted, rejected=rejected,
        mean_consensus=mean_consensus, reject_rate=reject_rate,
        unit_tokens=unit_tokens, unit_cost=unit_cost,
        consensus_delta=mean_consensus - baseline.mean_consensus,
        reject_delta=reject_rate - baseline.reject_rate,
        unit_tokens_ratio=ratio,
        degraded=bool(reasons), reasons=reasons,
    )


# --- 캠페인 리포트 + 러너 ---


@dataclass
class CampaignReport:
    run_id: str
    target: int
    baseline: PilotBaseline
    batch_report: BatchReport
    windows: list[WeeklyReport]
    allocation: dict[str, float]
    stopped: bool  # 게이트가 자동 중단을 발동했는가 (남은 슬롯 생성을 멈춤)

    @property
    def degraded(self) -> bool:
        """어느 윈도든 Pilot 대비 악화했는가 — 조기 중단 여부와 무관한 품질 신호.

        서브윈도(배치 < window_batches) 실행이나 마지막 부분 윈도의 악화는 stopped를 켜지
        못한다(그 시점엔 이미 생성이 끝나 멈출 게 없다). 그런 악화도 이 플래그로는 드러나므로,
        운영/CI 기계 신호는 stopped가 아니라 이 값을 써야 한다 (CLI exit code의 근거).
        """
        return any(w.degraded for w in self.windows)

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "target": self.target,
            "stopped": self.stopped,
            "degraded": self.degraded,
            "created": self.batch_report.created,
            "skipped_existing": self.batch_report.skipped_existing,
            "failed": self.batch_report.failed,
            "baseline": self.baseline.as_dict(),
            "allocation": {d: round(v, 4) for d, v in self.allocation.items()},
            "windows": [w.as_dict() for w in self.windows],
            "batch_report": self.batch_report.as_dict(),
        }


def run_campaign(
    session: Session,
    *,
    run_id: str,
    target_n: int,
    llm_client: LLMClient,
    embed_fn: EmbedFn,
    config: ExperimentsConfig,
    baseline: PilotBaseline,
    personas: list[str] | None = None,
    batch_size: int | None = None,
    model: str = "campaign",
) -> CampaignReport:
    """도메인 배분대로 target_n 에피소드를 생성하되, 윈도 품질이 Pilot 대비 악화하면 자동 중단."""
    # 전량 완료 재시작이면 prepare(소스·프레임·시나리오·governance_events·raw 문서)를 건너뛴다 —
    # 없으면 재실행마다 참조되지 않는 provenance 행과 감사 로그가 누적된다(원칙 9 오염). 배분은
    # DB 없이 counts로부터 보고한다.
    _counts, allocation = _planned_counts_and_allocation(config, target_n)
    if target_n > 0 and len(existing_slot_hashes(session, run_id, target_n)) >= target_n:
        empty = BatchReport(
            run_id=run_id, requested=target_n, created=0, skipped_existing=target_n, failed=0
        )
        return CampaignReport(
            run_id=run_id, target=target_n, baseline=baseline, batch_report=empty,
            windows=[], allocation=allocation, stopped=False,
        )

    schedule = prepare_campaign_scenarios(
        session, run_id=run_id, config=config, target_n=target_n,
        llm_client=llm_client, model=model,
    )
    windows: list[WeeklyReport] = []
    window_batches: list[BatchCost] = []
    state = {"week": 0, "halted": False}

    def on_checkpoint(batch_cost: BatchCost, _report: BatchReport) -> bool:
        window_batches.append(batch_cost)
        if len(window_batches) >= config.campaign.window_batches:
            report = _evaluate_window(state["week"], window_batches, baseline, config)
            windows.append(report)
            state["week"] += 1
            window_batches.clear()
            if report.degraded:
                state["halted"] = True
                return False  # 자동 중단
        return True

    batch_report = run_batch(
        session, run_id=run_id, n=target_n, llm_client=llm_client, embed_fn=embed_fn,
        config=config, scenarios=schedule.scenarios, personas=personas or _DEFAULT_PERSONAS,
        batch_size=batch_size, model=model, on_checkpoint=on_checkpoint,
    )
    if window_batches:  # 중단 없이 끝난 경우의 잔여(부분) 윈도
        windows.append(_evaluate_window(state["week"], window_batches, baseline, config))

    return CampaignReport(
        run_id=run_id, target=target_n, baseline=baseline, batch_report=batch_report,
        windows=windows, allocation=schedule.allocation, stopped=state["halted"],
    )
