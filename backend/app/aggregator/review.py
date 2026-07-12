"""인간 검수 → GOLD 승격 (§3-3, §3-6).

> `GOLD` | **인간 검수 2인 이상 일치**(kappa 기록). 확정 라벨 보유 (§3-3)

**GOLD를 만드는 유일한 경로다.** Aggregator(§3-6)는 SILVER까지만 올릴 수 있고(`recommend_tier`가
GOLD를 절대 반환하지 않는다), Gym·Foundry·Arena 어디에도 GOLD 승격 경로가 없다. 여기가 그 문이다.

## 왜 이렇게 빡빡한가

GOLD는 세 곳으로 흘러간다: exemplar(추론 retrieval의 재료) · Version Gate의 new_gold(성장 트리거)
· KTIB(§8-2 유일한 심판). 여기서 한 건이라도 잘못 확정되면 그 오염은 되돌릴 수 없다. 그래서:

- **1인 확정 불가.** 서로 다른 검수자 `config.review.min_reviewers`명 이상이 **같은 intent**를
  골라야 한다. 한 명이라도 다르면 그 에피소드는 **상태가 변하지 않는다**(강제 확정 없음).
- **검수자 신원은 정규화해서 센다.** `"alice"`와 `"alice "`, `"Alice"`는 같은 사람이다. 문자열
  부등호를 사람의 구별로 착각하면 **한 사람이 혼자 GOLD를 찍어낼 수 있다**(적대적 리뷰가 잡은
  결함). 공백만 있는 ref는 검수자가 아니다.
- **배치 단위 kappa 게이트.** 검수자 쌍의 Cohen's kappa가 `config.review.min_agreement_kappa`
  미만이면 **배치 전체를 거부**한다. 서로 일치하지 않는 검수자들이 우연히 겹친 몇 건으로 GOLD를
  만들어선 안 된다(§1-14 Pilot 게이트와 같은 정신). 비교는 **반올림 전 원값**으로 한다 —
  0.64995를 0.65로 반올림해 통과시키지 않는다.
- **kappa는 실재하는 에피소드의 표에서만 계산한다.** DB에 없는 에피소드에 대한 표가 섞이면,
  가짜 표로 라벨 다양성을 만들어 `pe ≥ 1` 가드(아래)를 우회할 수 있다. 존재하지 않는 에피소드를
  가리키는 배치는 거부한다.
- **kappa 계산 불가 = 거부.** 모든 검수자가 늘 같은 하나의 라벨만 골랐다면(주변확률 1) kappa는
  정의되지 않는다. 이때 "완전 일치니까 1.0"으로 취급하면 *아무것도 검증하지 않은 배치*가
  통과한다. `None`을 반환하고 배치를 거부한다.
- **재적용은 무해하다.** 이미 확정된(terminal) 에피소드나 검수 대상이 아닌 상태의 에피소드는
  `UNCHANGED`로 남긴다 — 같은 파일을 두 번 적용해도 예외가 터지지 않는다.
- **합성 에피소드도 GOLD가 될 수 있다** — 그건 exemplar·new_gold에 쓰인다. 하지만
  `origin_channel`이 합성이면 `benchmark_integrity` CHECK가 KTIB 진입을 물리적으로 막는다
  (절대 규칙 2). tier와 출생 축은 섞이지 않는다(§3-3 각주).

전이는 `advance_label_state`(§3-6)와 `promote_tier`(§3-3 가드)만 경유한다 — 여기서 직접
`label_state`/`reliability_tier`를 대입하지 않는다.
"""
from __future__ import annotations

import uuid
from collections import Counter
from dataclasses import dataclass, field
from itertools import combinations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.aggregator.state_machine import advance_label_state
from app.core.config import ExperimentsConfig
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.models.episodes import Episode
from app.models.governance import GovernanceEvent
from app.models.guards import promote_tier

REVIEW_EVENT = "HUMAN_REVIEW_BATCH"
# 검수자가 "이 에피소드는 버린다"고 판정한 경우의 라벨 자리표시자. 온톨로지 intent와 충돌하지
# 않도록 실 intent에 쓰일 수 없는 문자를 쓴다(§5-9 intent_id는 소문자·언더스코어).
REJECT = "\x00__REJECT__"

# 검수 대상 상태 (§3-6). 그 밖의 상태(terminal 포함)는 건드리지 않는다 — 재적용이 무해하도록.
REVIEWABLE_STATES = frozenset({"LABEL_CANDIDATE", "REVIEW_REQUIRED"})


class ReviewBatchRejected(Exception):
    """배치가 신뢰 기준(kappa·검수자 수·표의 실재성)을 통과하지 못했다 — 아무것도 확정 안 함."""


class UnknownReviewIntent(Exception):
    """온톨로지에 없는 intent로 검수했다 — 라벨을 지어내지 않는다."""


def canonical_reviewer(reviewer_ref: str) -> str:
    """검수자 신원 정규화 — 문자열 부등호를 사람의 구별로 착각하지 않는다.

    `"alice"`, `"alice "`, `"Alice"`는 한 사람이다. 공백뿐인 ref는 검수자가 아니다(빈 문자열).
    """
    return (reviewer_ref or "").strip().casefold()


@dataclass(frozen=True)
class ReviewVote:
    """검수자 1명이 에피소드 1건에 내린 판정. `chosen_intent=None`이면 폐기(REJECTED) 표."""

    episode_id: str
    reviewer_ref: str
    chosen_intent: str | None

    @property
    def reviewer(self) -> str:
        """구별에 쓰는 정규화된 신원. 기록에도 이 값을 남긴다(별칭으로 2인을 위장 못 하게)."""
        return canonical_reviewer(self.reviewer_ref)


@dataclass
class EpisodeOutcome:
    episode_id: str
    outcome: str          # LABELED | REJECTED | UNCHANGED
    intent: str | None
    reviewers: list[str]
    reason: str = ""


@dataclass
class ReviewReport:
    kappa: float | None
    reviewers: list[str]
    labeled: int = 0
    rejected: int = 0
    unchanged: int = 0
    episodes: list[EpisodeOutcome] = field(default_factory=list)


# --- Cohen's kappa (배치 신뢰도) ---


def cohens_kappa(a: list[str], b: list[str]) -> float | None:
    """두 검수자가 **같은 에피소드들**에 매긴 라벨의 일치도. 정의 불가면 None.

    pe(우연 일치 기대)가 1이면 kappa는 정의되지 않는다 — 두 사람이 늘 같은 하나의 라벨만
    골랐다는 뜻이고, 그 배치는 아무것도 변별하지 못했다. 1.0으로 반올림하지 않는다.

    **반올림하지 않고 반환한다.** 0.64995를 0.65로 반올림하면 임계를 통과한다 — 반올림은
    기록할 때만 한다.
    """
    n = len(a)
    if n == 0 or n != len(b):
        return None
    observed = sum(x == y for x, y in zip(a, b, strict=True)) / n
    ca, cb = Counter(a), Counter(b)
    expected = sum((ca[k] / n) * (cb[k] / n) for k in set(ca) | set(cb))
    if expected >= 1.0:
        return None  # 변별력 없는 배치 — 계산 불가
    return (observed - expected) / (1.0 - expected)


def weighted_cohens_kappa(a: list[int], b: list[int]) -> float | None:
    """순서형 평점(1~5 등)의 **선형 가중** Cohen's kappa — 큰 불일치를 더 크게 벌한다.

    시험지 2차 검수(§3-3)에서 두 검수자의 1~5 평점 일치도를 잰다. 순서형이라 "4 vs 5"보다
    "1 vs 5"를 더 불일치로 본다(선형 가중). nominal cohens_kappa와 같은 정신:
    - **정의 불가(모든 평점이 단일 값이거나 기대 불일치가 0)면 None** — 변별 없는 배치를
      1.0으로 취급하지 않는다.
    - **반올림하지 않는다** — 임계 비교는 원값, 반올림은 기록할 때만.
    """
    n = len(a)
    if n == 0 or n != len(b):
        return None
    cats = sorted(set(a) | set(b))
    if len(cats) < 2:
        return None  # 한 값뿐 — 불일치 가중이 전부 0, 변별 불가
    spread = cats[-1] - cats[0]
    idx = {c: i for i, c in enumerate(cats)}
    k = len(cats)
    obs = [[0.0] * k for _ in range(k)]
    for x, y in zip(a, b, strict=True):
        obs[idx[x]][idx[y]] += 1
    row = [sum(obs[i]) for i in range(k)]                       # a 주변합
    col = [sum(obs[i][j] for i in range(k)) for j in range(k)]  # b 주변합

    def w(i: int, j: int) -> float:  # 선형 불일치 가중: 0(일치)~1(최대 불일치)
        return abs(cats[i] - cats[j]) / spread

    num = sum(w(i, j) * obs[i][j] for i in range(k) for j in range(k))
    den = sum(w(i, j) * (row[i] * col[j] / n) for i in range(k) for j in range(k))
    if den == 0:
        return None  # 기대 불일치 0 — 계산 불가(한쪽이 상수라도 이 경우는 드물다)
    return 1.0 - num / den


def batch_kappa(votes: list[ReviewVote]) -> float | None:
    """검수자 쌍별 Cohen's kappa 중 **최솟값**(가장 보수적). 겹치는 에피소드가 없으면 None.

    검수자는 **정규화된 신원**으로 묶는다 — 별칭 두 개가 한 쌍을 이뤄 kappa 1.0을 만들지 못하게.
    """
    by_reviewer: dict[str, dict[str, str]] = {}
    for v in votes:
        by_reviewer.setdefault(v.reviewer, {})[v.episode_id] = v.chosen_intent or REJECT

    kappas: list[float] = []
    for r1, r2 in combinations(sorted(by_reviewer), 2):
        shared = sorted(set(by_reviewer[r1]) & set(by_reviewer[r2]))
        if not shared:
            continue
        k = cohens_kappa([by_reviewer[r1][e] for e in shared], [by_reviewer[r2][e] for e in shared])
        if k is None:
            return None  # 한 쌍이라도 계산 불가면 배치 전체가 검증 불가다
        kappas.append(k)
    return min(kappas) if kappas else None


# --- 배치 적용 ---


def _validate_intents(votes: list[ReviewVote]) -> None:
    real = {i.intent_id for i in load_ontology().intents if i.intent_id != UNKNOWN_INTENT_ID}
    bad = sorted({v.chosen_intent for v in votes
                  if v.chosen_intent is not None and v.chosen_intent not in real})
    if bad:
        raise UnknownReviewIntent(f"온톨로지에 없는 intent로 검수: {bad}")


def apply_review_batch(
    session: Session,
    votes: list[ReviewVote],
    config: ExperimentsConfig,
    *,
    approved_by: str,
) -> ReviewReport:
    """검수 표 묶음을 적용한다. 배치가 신뢰 기준을 통과할 때만 어떤 에피소드든 확정된다.

    - 배치 kappa < `review.min_agreement_kappa` (또는 계산 불가) → `ReviewBatchRejected`, 무변화
    - 에피소드별: 서로 다른 검수자 ≥ `review.min_reviewers` ∧ **만장일치** → 확정
      - intent 일치 → `LABELED` + `GOLD` + `human_review` 기록
      - 전원 폐기표 → `REJECTED`
    - 그 밖(1인·불일치) → `UNCHANGED`. 강제로 확정하지 않는다.
    """
    if not votes:
        raise ReviewBatchRejected("검수 표가 없다")
    _validate_intents(votes)

    blank = sorted({v.reviewer_ref for v in votes if not v.reviewer})
    if blank:
        raise ReviewBatchRejected(f"빈 검수자 ref: {blank!r} — 공백은 검수자가 아니다")

    reviewers = sorted({v.reviewer for v in votes})  # 정규화된 신원으로 구별한다
    if len(reviewers) < config.review.min_reviewers:
        raise ReviewBatchRejected(
            f"검수자 {len(reviewers)}명 < 최소 {config.review.min_reviewers}명 (§3-3). "
            f"공백·대소문자 별칭은 같은 사람으로 센다"
        )

    by_episode: dict[str, list[ReviewVote]] = {}
    for v in votes:
        by_episode.setdefault(v.episode_id, []).append(v)

    episodes = {
        e.episode_id: e for e in session.scalars(
            select(Episode).where(Episode.episode_id.in_(list(by_episode)))
        )
    }
    # ★ 실재하지 않는 에피소드에 대한 표는 kappa의 라벨 다양성을 위조해 pe≥1 가드를 우회한다.
    phantom = sorted(set(by_episode) - set(episodes))
    if phantom:
        raise ReviewBatchRejected(f"DB에 없는 에피소드에 대한 표: {phantom}")

    # kappa는 **실재 에피소드의 표**로만 계산한다. 반올림 전 원값으로 임계를 비교한다.
    kappa = batch_kappa(votes)
    if kappa is None:
        raise ReviewBatchRejected(
            "배치 kappa 계산 불가 — 검수자 간 겹치는 에피소드가 없거나, 모든 라벨이 동일해 "
            "변별력이 없다. 완전 일치를 1.0으로 취급하지 않는다 (§3-3)"
        )
    if kappa < config.review.min_agreement_kappa:
        raise ReviewBatchRejected(
            f"배치 kappa {kappa:.6f} < 하한 {config.review.min_agreement_kappa} — "
            f"검수자들이 서로 일치하지 않는다. 배치 전량 거부 (§3-3)"
        )
    recorded_kappa = round(kappa, 4)  # 기록용 — 판정은 위에서 원값으로 끝났다

    report = ReviewReport(kappa=recorded_kappa, reviewers=reviewers)
    for episode_id in sorted(by_episode):
        cast = by_episode[episode_id]
        voters = sorted({v.reviewer for v in cast})
        report.episodes.append(
            _apply_one(episodes[episode_id], episode_id, cast, voters, recorded_kappa, config)
        )
    tally = Counter(o.outcome for o in report.episodes)
    report.labeled = tally["LABELED"]
    report.rejected = tally["REJECTED"]
    report.unchanged = tally["UNCHANGED"]

    session.flush()
    session.add(GovernanceEvent(
        event_id="GOV_" + uuid.uuid4().hex[:12],
        event_type=REVIEW_EVENT,
        payload={
            "reviewers": reviewers, "agreement_kappa": recorded_kappa,
            "labeled": report.labeled, "rejected": report.rejected,
            "unchanged": report.unchanged, "episodes": len(by_episode),
        },
        approved_by=approved_by,
    ))
    session.flush()
    return report


def _apply_one(
    episode: Episode,
    episode_id: str,
    cast: list[ReviewVote],
    voters: list[str],
    kappa: float,
    config: ExperimentsConfig,
) -> EpisodeOutcome:
    # ★ 검수 대상이 아닌 상태(이미 확정됨 포함)는 건드리지 않는다 — 같은 배치를 두 번 적용해도
    #   IllegalTransition으로 죽지 않고 조용히 UNCHANGED가 된다(재적용 무해).
    if episode.label_state not in REVIEWABLE_STATES:
        return EpisodeOutcome(episode_id, "UNCHANGED", None, voters,
                              f"검수 대상 상태가 아님(label_state={episode.label_state})")
    if len(voters) < config.review.min_reviewers:
        return EpisodeOutcome(episode_id, "UNCHANGED", None, voters,
                              f"검수자 {len(voters)}명 < {config.review.min_reviewers}명")

    choices = {v.chosen_intent for v in cast}
    if len(choices) > 1:
        return EpisodeOutcome(episode_id, "UNCHANGED", None, voters,
                              "검수자 판정 불일치 — 강제 확정하지 않는다")

    chosen = choices.pop()
    if chosen is None:  # 만장일치 폐기
        advance_label_state(episode, "REJECTED")
        return EpisodeOutcome(episode_id, "REJECTED", None, voters, "만장일치 폐기")

    # 만장일치 확정: 상태 → LABELED, 그 다음에야 tier → GOLD (promote_tier가 순서를 강제)
    advance_label_state(episode, "LABELED")
    episode.label_distribution = {chosen: 1.0}
    episode.human_review = {"reviewers": voters, "agreement_kappa": kappa}
    promote_tier(episode, "GOLD")
    return EpisodeOutcome(episode_id, "LABELED", chosen, voters, "만장일치 확정")
