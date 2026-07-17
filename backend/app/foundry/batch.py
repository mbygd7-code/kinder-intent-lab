"""배치 러너 — 체크포인트·재시작 가능한 대규모 에피소드 생성 (T2.1, §10-2 Phase 2).

- 슬롯별 결정론적 dedup_hash로 재시작 멱등: 이미 생성된 슬롯은 건너뛴다(중복 생성 0).
- 배치(chunk)마다 commit해 체크포인트. 중단 후 재실행하면 완료 슬롯을 스킵하고 이어간다.
- 실패 에피소드는 격리 큐(failed_episodes)로 보내고 배치를 계속 진행한다.
- 배치별 토큰·비용 단가 리포트.
"""
from __future__ import annotations

import hashlib
import logging
import uuid
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass, field

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.config import ExperimentsConfig
from app.core.ontology import CANONICAL_DOMAINS, load_ontology
from app.foundry.atlas import compute_coverage, enqueue_unmapped, simulator_stats
from app.foundry.episode_builder import generate_episode
from app.foundry.pilot import _Deduper, _default_source_specs
from app.foundry.situation_seeds import load_situation_seeds, pick_variants
from app.foundry.stages.s1_discovery import SourceCandidate, register_source
from app.foundry.stages.s2_governance import govern_source, store_raw_document
from app.foundry.stages.s3_extractor import FrameInput, build_situation_frame
from app.foundry.stages.s5_situation_builder import build_scenarios
from app.foundry.stages.s8_skeptic import record_confusion_edges
from app.llm.client import LLMClient
from app.models.episodes import Episode
from app.models.foundry import AtlasEntry, FailedEpisode

logger = logging.getLogger(__name__)

_DOMAINS = list(CANONICAL_DOMAINS)  # 정본 도메인 순환 (onto-2.0: STUDIO 포함 8)
_DEFAULT_PERSONAS = ["P_hypo_1", "P_active_2", "P_struct_3"]

Scenario = tuple[str, str, str]  # (scenario_id, frame_id, source_id)


def slot_dedup_hash(run_id: str, slot_index: int) -> str:
    """슬롯(run_id, index)의 결정론적 dedup_hash — 재시작 시 완료 슬롯 식별."""
    return "DH_" + hashlib.sha256(f"{run_id}|{slot_index}".encode()).hexdigest()[:38]


def existing_slot_hashes(session: Session, run_id: str, n: int) -> set[str]:
    """run_id의 0..n-1 슬롯 중 이미 생성된 슬롯의 dedup_hash 집합 (재시작 멱등의 근거)."""
    hashes = [slot_dedup_hash(run_id, i) for i in range(n)]
    return set(session.scalars(select(Episode.dedup_hash).where(Episode.dedup_hash.in_(hashes))))


def prepare_scenarios(
    session: Session, *, run_id: str, config: ExperimentsConfig,
    specs: list[SourceCandidate] | None = None,
) -> list[Scenario]:
    """S1~S5로 소스·프레임·시나리오를 준비한다 (배치 러너 입력). run_batch와 분리 — 1회 실행."""
    specs = specs or _default_source_specs()
    seed_file = load_situation_seeds()  # 화면 씨드(수동 작성) — 계약 위반이면 증산 시작 전 실패
    scenarios: list[Scenario] = []
    for si, spec in enumerate(specs):
        source = register_source(session, spec)
        govern_source(session, source.source_id, "ALLOW", reviewed_by="batch")
        store_raw_document(session, source.source_id, f"[batch raw excerpt {run_id} {si}]")
        domain = _DOMAINS[si % len(_DOMAINS)]
        frame = build_situation_frame(
            session,
            FrameInput(
                domain=domain, summary=f"배치 소스 {si} 상황 프레임",
                teacher_concern="개입 시점과 방식", extraction_confidence=0.8,
            ),
        )
        session.flush()
        variants = pick_variants(
            seed_file, domain=domain, k=config.foundry.scenario_variants,
            salt=f"{run_id}|{domain}|{si}",
        )
        for sc in build_scenarios(session, frame, variants, config):
            scenarios.append((sc.scenario_id, frame.frame_id, source.source_id))
    session.flush()
    return scenarios


@dataclass
class BatchCost:
    batch_index: int
    attempted: int   # 시도한 슬롯 수 (created + failed) — 단가 분모
    created: int     # 실제 적재된 에피소드 (accept + reject 모두; 실패·스킵 제외)
    failed: int
    tokens: int      # 배치 윈도의 모든 LLM 토큰 (실패분 포함 = 낭비 포함)
    cost_usd: float
    rejected: int    # created 중 Judge가 reject한 수 (품질 지표; T2.5)
    consensus_sum: float  # accept된 에피소드의 합의도 합 (평균 분자; T2.5)

    def unit_tokens(self) -> float:
        """시도당 토큰 — 실패로 낭비된 호출까지 반영(전량 실패 배치가 0으로 오보고되지 않게)."""
        return self.tokens / self.attempted if self.attempted else 0.0

    def unit_cost(self) -> float:
        return self.cost_usd / self.attempted if self.attempted else 0.0

    def accepted(self) -> int:
        return self.created - self.rejected

    def reject_rate(self) -> float:
        """created 대비 reject 비율 (Pilot judge_reject_rate와 같은 모집단)."""
        return self.rejected / self.created if self.created else 0.0

    def mean_consensus(self) -> float:
        """accept분 평균 합의도 (Pilot mean_consensus와 같은 모집단)."""
        acc = self.accepted()
        return self.consensus_sum / acc if acc else 0.0


@dataclass
class BatchReport:
    run_id: str
    requested: int
    created: int
    skipped_existing: int
    failed: int
    batches: list[BatchCost] = field(default_factory=list)

    def total_tokens(self) -> int:
        return sum(b.tokens for b in self.batches)

    def total_cost(self) -> float:
        return sum(b.cost_usd for b in self.batches)

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "requested": self.requested,
            "created": self.created,
            "skipped_existing": self.skipped_existing,
            "failed": self.failed,
            "total_tokens": self.total_tokens(),
            "total_cost_usd": round(self.total_cost(), 6),
            "batches": [
                {
                    "batch_index": b.batch_index, "attempted": b.attempted, "created": b.created,
                    "failed": b.failed, "rejected": b.rejected, "tokens": b.tokens,
                    "unit_tokens": round(b.unit_tokens(), 2),
                    "unit_cost_usd": round(b.unit_cost(), 6),
                    "reject_rate": round(b.reject_rate(), 4),
                    "mean_consensus": round(b.mean_consensus(), 4),
                }
                for b in self.batches
            ],
        }


def _chunks(items: list[int], size: int) -> Iterator[list[int]]:
    for i in range(0, len(items), size):
        yield items[i : i + size]


def run_batch(
    session: Session,
    *,
    run_id: str,
    n: int,
    llm_client: LLMClient,
    embed_fn,
    config: ExperimentsConfig,
    scenarios: list[Scenario],
    personas: list[str] | None = None,
    batch_size: int | None = None,
    model: str = "batch",
    on_checkpoint: Callable[[BatchCost, BatchReport], bool] | None = None,
) -> BatchReport:
    """n개 슬롯을 batch_size씩 생성·커밋한다. 완료 슬롯은 스킵(재시작 멱등), 실패는 격리.

    on_checkpoint: 배치 커밋 직후 (방금 배치의 BatchCost, 누적 BatchReport)로 호출된다.
    False를 반환하면 루프를 중단한다 — 캠페인 품질 게이트의 자동 중단 훅 (T2.5). 체크포인트는
    이미 커밋됐으므로 중단해도 다음 실행에서 완료 슬롯을 스킵하고 이어갈 수 있다.
    """
    if not scenarios:
        raise ValueError("scenarios가 비어 있습니다 (prepare_scenarios 먼저)")
    personas = personas or _DEFAULT_PERSONAS
    batch_size = batch_size or config.foundry.batch_size
    ontology_version = load_ontology().version

    # Atlas 재보정 통계(§2-3) — 비면 None(컨텍스트 생략). 발화는 coverage용으로 수집한다(§2-4)
    _stats = simulator_stats(session)
    atlas_stats = (
        {"sample_count": _stats.sample_count,
         "mean_word_length": round(_stats.mean_word_length, 2),
         "deixis_ratio": round(_stats.deixis_ratio, 3)}
        if _stats.sample_count else None
    )
    run_utterances: list[str] = []

    slot_hashes = {i: slot_dedup_hash(run_id, i) for i in range(n)}
    existing = existing_slot_hashes(session, run_id, n)
    todo = [i for i in range(n) if slot_hashes[i] not in existing]

    call_log: list = []
    prev_recorder = llm_client._recorder  # noqa: SLF001
    llm_client._recorder = call_log.append  # noqa: SLF001
    deduper = _Deduper(embed_fn, config.foundry.dedup_similarity)

    report = BatchReport(
        run_id=run_id, requested=n, created=0, skipped_existing=len(existing), failed=0,
    )
    try:
        for batch_index, chunk in enumerate(_chunks(todo, batch_size)):
            batch_log_start = len(call_log)
            batch_pairs: list = []
            created_here = 0
            failed_here = 0
            rejected_here = 0
            consensus_sum_here = 0.0
            for i in chunk:
                scenario_id, _f, _s = scenarios[i % len(scenarios)]
                persona = personas[i % len(personas)]
                try:
                    gen = generate_episode(
                        llm_client, config=config, run_id=run_id, index=i,
                        scenario_id=scenario_id, persona=persona,
                        ontology_version=ontology_version, deduper=deduper, model=model,
                        dedup_hash=slot_hashes[i], atlas_stats=atlas_stats,
                    )
                except Exception as exc:  # noqa: BLE001 — 생성 실패 격리, 배치는 계속
                    session.add(
                        FailedEpisode(
                            fail_id=f"FE_{uuid.uuid4().hex[:12]}", run_id=run_id, slot_index=i,
                            stage="generate_episode", error=f"{type(exc).__name__}: {exc}"[:1000],
                        )
                    )
                    failed_here += 1
                    continue
                # 슬롯별 savepoint — 동시 러너가 이미 만든 슬롯이면 dedup_hash 유니크 위반을
                # 이 슬롯만 롤백하고 스킵(배치 전체를 중단시키지 않는다)
                try:
                    with session.begin_nested():
                        session.add(gen.episode)
                        session.add_all(gen.evidences)
                except IntegrityError:
                    report.skipped_existing += 1
                    continue
                batch_pairs.extend(gen.pairs)
                run_utterances.append(gen.episode.teacher_prompt)
                created_here += 1
                if gen.accepted:
                    consensus_sum_here += gen.consensus_score
                else:
                    rejected_here += 1

            record_confusion_edges(session, batch_pairs)
            session.commit()  # 체크포인트 — 여기까지는 재시작 시 스킵된다

            report.failed += failed_here
            new_calls = call_log[batch_log_start:]
            batch_cost = BatchCost(
                batch_index=batch_index, attempted=created_here + failed_here,
                created=created_here, failed=failed_here,
                tokens=sum(c.total_tokens for c in new_calls),
                cost_usd=sum(c.cost_usd for c in new_calls),
                rejected=rejected_here, consensus_sum=consensus_sum_here,
            )
            report.batches.append(batch_cost)
            report.created += created_here
            if on_checkpoint is not None and on_checkpoint(batch_cost, report) is False:
                break  # 품질 게이트 자동 중단 — 체크포인트는 커밋됨

        # Atlas coverage(§2-4): 신규 발화 중 미매핑을 확장 큐로. Atlas가 비어 있으면 전량
        # 미매핑이 되어 큐가 범람하므로 스킵한다(원료 주입 전까지 큐는 의미가 없다).
        if run_utterances and session.scalar(select(func.count()).select_from(AtlasEntry)):
            try:
                cov = compute_coverage(session, run_utterances, embed_fn, config)
                queued = enqueue_unmapped(session, cov.unmapped, source_run=run_id)
                session.commit()
                logger.info(
                    "Atlas coverage %.2f (%d/%d) — 확장 큐 +%d",
                    cov.coverage(), cov.mapped, cov.total, len(queued),
                )
            except Exception as exc:  # noqa: BLE001 — 부가 지표 실패가 증산을 못 죽인다
                session.rollback()
                logger.warning("Atlas coverage 계산 실패(무시하고 계속): %s", exc)
    finally:
        llm_client._recorder = prev_recorder  # noqa: SLF001

    return report


def build_work_iterator(scenarios: Iterable[Scenario], n: int) -> list[int]:
    """호환용 — 슬롯 인덱스 목록."""
    return list(range(n))
