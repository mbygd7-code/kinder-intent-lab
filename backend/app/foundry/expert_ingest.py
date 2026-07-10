"""전문가 저작 에피소드 유입 (§3-2 provenance, §8-2 KTIB).

**KTIB(§8-2)에 들어갈 수 있는 유일한 경로다.** 절대 규칙 2의 `benchmark_integrity` CHECK가
`BENCHMARK_HOLDOUT ⇒ GOLD ∧ LABELED ∧ origin_channel ∉ {FOUNDRY_SYNTHETIC, FOUNDRY_AUGMENTED}`를
물리적으로 강제하므로, 합성 뱅크에서 승격시켜 벤치마크를 만드는 길은 존재하지 않는다.

## 이 모듈이 절대 하지 않는 것

**발화를 생성하지 않는다.** 입력 파일은 사람이 쓰거나(전문가 저작), 사람이 수집·검수한
비합성 코퍼스여야 한다. LLM이 쓴 발화를 `EXPERT_AUTHORED`로 찍어 넣으면 그 순간 KTIB는
합성 분포가 되고, Arena 점수는 '암기'의 측정치가 되어 아무것도 뜻하지 않는다. 코드는 그것을
탐지할 수 없다 — 그래서 `authored_by`를 필수로 받고 거버넌스 이벤트에 남긴다(원칙 9의 정신).

## 가드

- `origin_channel`은 **비합성만** 허용한다(EXPERT_AUTHORED / OFFICIAL_CORPUS / COMMUNITY_DERIVED).
- `dataset_split=BENCHMARK_HOLDOUT`이면 `LABELED ∧ GOLD`로 적재하므로 §3-3 기준을 그대로 요구한다:
  **정규화된** 서로 다른 검수자 `config.review.min_reviewers`명 이상 ∧ 기록된
  `agreement_kappa ≥ config.review.min_agreement_kappa`. 검수 경로(`aggregator.review`)보다 느슨하면
  사람들이 느슨한 문을 쓴다. DB CHECK가 최종 백스톱이다.
- 검수자 신원은 정규화해서 센다 — `"kim"`과 `"kim "`은 한 사람이다. 문자열 부등호를 사람의
  구별로 착각하면 한 사람이 혼자 벤치마크 정답을 확정할 수 있다(적대적 리뷰가 잡은 결함).
- intent는 온톨로지에 실재해야 한다 (UNKNOWN 불가 — 벤치마크의 정답이 '모름'일 수 없다).
- `dedup_hash`(발화+intent)로 재유입을 막는다. **split을 해시에 넣지 않는다** — 넣으면 같은
  발화가 TRAIN과 BENCHMARK_HOLDOUT에 동시에 존재해 학습/시험 오염이 된다(§8-2).
- 벤치마크 유입 시 같은 발화가 이미 **다른 split에** 있으면 거부한다(해시 형식이 다른 합성분 포함).
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.aggregator.review import canonical_reviewer
from app.core.config import ExperimentsConfig
from app.core.datasets import BENCHMARK_SPLIT
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.models.episodes import Episode
from app.models.governance import GovernanceEvent

INGEST_EVENT = "EXPERT_EPISODE_INGEST"

# §3-2 provenance — 합성 채널은 벤치마크에 못 들어간다(절대 규칙 2). 여기서도 애초에 거부한다.
NON_SYNTHETIC_CHANNELS = ("EXPERT_AUTHORED", "OFFICIAL_CORPUS", "COMMUNITY_DERIVED")
VALID_SPLITS = ("TRAIN", "VALIDATION", "TEST", BENCHMARK_SPLIT)


def reviewer_set(reviewers: tuple[str, ...]) -> set[str]:
    """정규화된 서로 다른 검수자 신원. 공백뿐인 ref는 검수자가 아니다 (review와 동일 규칙)."""
    return {c for c in (canonical_reviewer(r) for r in reviewers) if c}


class SyntheticChannelRejected(Exception):
    """합성 채널로 전문가 유입을 시도했다 — 벤치마크 오염 경로를 여기서 막는다 (절대 규칙 2)."""


class BenchmarkNeedsReview(Exception):
    """BENCHMARK_HOLDOUT은 GOLD여야 하고, GOLD는 인간 검수 2인 이상 일치 ∧ kappa 기록이다 (§3-3)."""


class TrainBenchmarkContamination(Exception):
    """같은 발화가 학습 분할에도 있다 — 벤치마크가 일반화가 아니라 암기를 잰다 (§8-2)."""


class UnknownIngestIntent(Exception):
    """온톨로지에 없는(또는 UNKNOWN) intent — 벤치마크의 정답이 '모름'일 수 없다."""


@dataclass(frozen=True)
class ExpertEpisode:
    episode_id: str
    teacher_prompt: str
    intent: str
    lang: str = "ko"
    reviewers: tuple[str, ...] = ()
    agreement_kappa: float | None = None


@dataclass
class IngestReport:
    inserted: int = 0
    skipped_duplicate: int = 0
    episode_ids: list[str] = field(default_factory=list)


def _dedup_hash(prompt: str, intent: str) -> str:
    """split을 넣지 않는다 — 같은 발화가 TRAIN과 BENCHMARK에 공존하면 학습/시험 오염이다(§8-2)."""
    return hashlib.sha256(f"{intent}\x1f{prompt.strip()}".encode()).hexdigest()


def _assert_benchmark_reviewed(
    episodes: list[ExpertEpisode], config: ExperimentsConfig
) -> None:
    """벤치마크는 GOLD로 적재된다 → §3-3 기준을 그대로 요구한다 (검수 경로보다 느슨하면 안 된다).

    - 정규화된 서로 다른 검수자 `review.min_reviewers`명 이상 (별칭·공백으로 2인 위장 금지)
    - 기록된 `agreement_kappa ≥ review.min_agreement_kappa` (없으면 미측정 — 통과시키지 않는다)
    """
    need = config.review.min_reviewers
    floor = config.review.min_agreement_kappa

    thin = [e.episode_id for e in episodes if len(reviewer_set(e.reviewers)) < need]
    if thin:
        raise BenchmarkNeedsReview(
            f"BENCHMARK_HOLDOUT에는 서로 다른 검수자 {need}명 이상이 필요하다 (§3-3). "
            f"미달(공백·대소문자 별칭은 같은 사람): {thin}"
        )
    unmeasured = [e.episode_id for e in episodes if e.agreement_kappa is None]
    if unmeasured:
        raise BenchmarkNeedsReview(
            f"agreement_kappa 미기록 — 측정하지 않은 일치도는 일치가 아니다 (§3-3): {unmeasured}"
        )
    low = [e.episode_id for e in episodes if e.agreement_kappa < floor]
    if low:
        raise BenchmarkNeedsReview(
            f"agreement_kappa < 하한 {floor} (§3-3): {low}"
        )


def _assert_no_train_contamination(session: Session, episodes: list[ExpertEpisode]) -> None:
    """같은 발화가 이미 학습 분할에 있으면 벤치마크는 일반화가 아니라 암기를 잰다 (§8-2).

    dedup_hash 형식이 다른 합성분까지 잡기 위해 `teacher_prompt` 원문으로 대조한다.
    """
    prompts = [e.teacher_prompt.strip() for e in episodes]
    clashing = sorted(session.scalars(
        select(Episode.teacher_prompt).where(
            Episode.teacher_prompt.in_(prompts),
            Episode.dataset_split != BENCHMARK_SPLIT,
        )
    ))
    if clashing:
        raise TrainBenchmarkContamination(
            f"이미 학습 분할에 존재하는 발화를 벤치마크에 넣으려 한다 (§8-2): {clashing[:5]}"
        )


def ingest_expert_episodes(
    session: Session,
    episodes: list[ExpertEpisode],
    config: ExperimentsConfig,
    *,
    origin_channel: str,
    dataset_split: str,
    authored_by: str,
    approved_by: str,
) -> IngestReport:
    """사람이 저작·검수한 에피소드를 적재한다. 발화를 생성하지 않는다."""
    if origin_channel not in NON_SYNTHETIC_CHANNELS:
        raise SyntheticChannelRejected(
            f"origin_channel={origin_channel} — 전문가 유입은 비합성 채널만 (절대 규칙 2): "
            f"{NON_SYNTHETIC_CHANNELS}"
        )
    if dataset_split not in VALID_SPLITS:
        raise ValueError(f"알 수 없는 dataset_split: {dataset_split}")
    if not episodes:
        raise ValueError("에피소드가 없다")
    if not authored_by.strip():
        raise ValueError("authored_by(저작자)는 필수다 — 누가 썼는지 남지 않는 벤치마크는 없다")

    real = {i.intent_id for i in load_ontology().intents if i.intent_id != UNKNOWN_INTENT_ID}
    bad = sorted({e.intent for e in episodes if e.intent not in real})
    if bad:
        raise UnknownIngestIntent(f"온톨로지에 없는 intent: {bad}")

    is_benchmark = dataset_split == BENCHMARK_SPLIT
    if is_benchmark:
        _assert_benchmark_reviewed(episodes, config)
        _assert_no_train_contamination(session, episodes)

    ontology_version = load_ontology().version
    existing = set(session.scalars(select(Episode.dedup_hash).where(
        Episode.dedup_hash.in_([_dedup_hash(e.teacher_prompt, e.intent) for e in episodes])
    )))

    report = IngestReport()
    for e in episodes:
        digest = _dedup_hash(e.teacher_prompt, e.intent)
        if digest in existing:
            report.skipped_duplicate += 1
            continue
        existing.add(digest)

        episode = Episode(
            episode_id=e.episode_id,
            ontology_version=ontology_version,
            lang=e.lang,
            dataset_split=dataset_split,
            # 벤치마크는 GOLD∧LABELED로만 존재할 수 있다(CHECK). 그 밖 split은 검수 전 상태로 둔다.
            reliability_tier="GOLD" if is_benchmark else "UNVERIFIED",
            label_state="LABELED" if is_benchmark else "UNLABELED",
            origin_channel=origin_channel,
            episode_creator_type="HUMAN_ANNOTATOR",
            primary_subject_type="TEACHER",
            teacher_prompt=e.teacher_prompt,
            label_distribution={e.intent: 1.0},
            human_review=(
                # 정규화된 신원을 기록한다 — 별칭 두 개로 '2인 검수'를 위장할 수 없게.
                {"reviewers": sorted(reviewer_set(e.reviewers)),
                 "agreement_kappa": e.agreement_kappa}
                if reviewer_set(e.reviewers) else None
            ),
            dedup_hash=digest,
        )
        session.add(episode)
        report.inserted += 1
        report.episode_ids.append(e.episode_id)

    session.flush()  # benchmark_integrity CHECK가 여기서 최종 백스톱으로 작동한다
    session.add(GovernanceEvent(
        event_id="GOV_" + uuid.uuid4().hex[:12],
        event_type=INGEST_EVENT,
        payload={
            "origin_channel": origin_channel, "dataset_split": dataset_split,
            "authored_by": authored_by, "inserted": report.inserted,
            "skipped_duplicate": report.skipped_duplicate,
        },
        approved_by=approved_by,
    ))
    session.flush()
    return report
