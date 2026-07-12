"""즉석 문답(Live Quiz) — 자유 발화 라이브 추론에 대한 사람 판정 수용 (§3-1·§3-2·§6-7 [5][6]).

훈련용: GYM_HUMAN 에피소드 + HUMAN evidence(뇌 추측 일치=확인, 다름·abstain=교정) →
  같은 발화의 축적 중 에피소드에 신호를 덧붙이고(§6-7 [5] 2인 일치 경로), 최소 신호 수
  도달 시 집계 전이 + 노드 size/density 재집계 + pending 링(§6-5).
출제용: **DB에 아무것도 쓰지 않는다.** KTIB로 가는 문은 scripts/ingest_expert_episodes.py
  하나뿐이다(§8-2) — 이 모듈은 그 문 앞의 대기줄(YAML 큐)만 만든다. 큐에는 뇌 추측을
  기록하지 않는다: 2차 검수자가 뇌의 답에 앵커링되면 독립 검수가 아니다(§3-3의 정신).
  approved_by는 자리 표시자로 남겨 두므로, 2차 검수자가 채우기 전에는 ingest가 거부한다.
새 의도 제안: atlas_expansion_queue(PENDING) 등록만 — brain_nodes 자동 INSERT 금지(규칙 4).

절대 규칙 3·원칙 8: 이 모듈은 brightness 계열(heldout_accuracy·calibration_ece·
last_arena_run)을 읽지도 쓰지도 않는다. 훈련 반영은 size/density/pending 링뿐이다.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

import yaml
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.aggregator.aggregator import aggregate, apply_aggregation, signals_from_rows
from app.aggregator.state_machine import advance_label_state
from app.brain.backfill import aggregate_evidence_stats
from app.core.config import ExperimentsConfig
from app.core.datasets import BENCHMARK_SPLIT
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.foundry.expert_ingest import TrainBenchmarkContamination
from app.gym.evidence import GYM_ACTOR_TYPE
from app.gym.session import _open_episode_for
from app.models.brain import BrainNode
from app.models.episodes import Episode, Evidence
from app.models.foundry import AtlasExpansionEntry

# 2차 검수 대기 큐 — ingest_expert_episodes.py --file 이 그대로 읽는 형식.
# 단일 사용자 실험실 전제(동시 쓰기 미보호). 테스트는 이 경로를 monkeypatch 한다.
BENCHMARK_QUEUE_PATH = Path(__file__).resolve().parents[3] / "seeds" / "benchmark_candidates.yaml"

APPROVED_BY_PLACEHOLDER = "<2차 검수 후 기입>"  # '<' 시작 → 검수 전 ingest가 거부(의도된 잠금)


class DuplicateFeedback(Exception):
    """같은 feedback_id 재제출(더블클릭·타임아웃 재시도) — 이중 계상 차단."""


class DuplicateBenchmarkCandidate(Exception):
    """같은 발화가 이미 출제 대기열에 있다."""


class UnknownLiveIntent(Exception):
    """온톨로지에 없는(또는 UNKNOWN) intent — 라벨·evidence로 새는 것을 차단."""


def real_intent_ids() -> set[str]:
    """온톨로지의 실 intent(도메인 보유, UNKNOWN 제외) — chosen_intent 검증 기준."""
    return {
        i.intent_id
        for i in load_ontology().intents
        if i.domain and i.intent_id != UNKNOWN_INTENT_ID
    }


@dataclass
class LiveReport:
    kind: str                      # confirmation | correction
    episode_id: str
    evidence_created: int
    episodes_aggregated: int
    label_states: dict[str, int] = field(default_factory=dict)
    pending_set: bool = False
    node_intent: str | None = None


def record_training_feedback(
    session: Session,
    *,
    feedback_id: str,
    trainer_ref: str,
    utterance: str,
    chosen_intent: str,
    brain_top_intent: str | None,
    intent_candidates: list[str] | None = None,
    inference_request_id: str | None = None,
    config: ExperimentsConfig,
) -> LiveReport:
    """사람 판정 1건 → HUMAN evidence + §6-7 [5][6] 반영. brightness 불변(규칙 3)."""
    if chosen_intent not in real_intent_ids():
        raise UnknownLiveIntent(chosen_intent)

    evidence_id = "EV_LIVE_" + feedback_id
    if session.get(Evidence, evidence_id) is not None:
        raise DuplicateFeedback(feedback_id)

    utterance = utterance.strip()
    # 뇌 추측과 일치하면 확인, 다르거나 뇌가 답을 못 냈으면(미스 문서화) 교정
    confirmed = brain_top_intent is not None and chosen_intent == brain_top_intent
    etype = "HUMAN_CONFIRMATION" if confirmed else "HUMAN_CORRECTION"

    # §6-7 [5]: 같은 발화의 축적 중 GYM_HUMAN 에피소드가 있으면 신호를 덧붙인다
    episode = _open_episode_for(session, utterance)
    if episode is None:
        episode = Episode(
            episode_id="EP_LIVE_" + uuid.uuid4().hex[:12],
            ontology_version=load_ontology().version,
            lang="ko",
            dataset_split="TRAIN",           # 벤치마크 아님 → 절대 규칙 2 무관
            reliability_tier="UNVERIFIED",   # 사람 1명 라벨 — 아직 미검증
            label_state="EVIDENCE_ACCUMULATING",
            origin_channel="GYM_HUMAN",      # 비합성 — 트레이너가 직접 타이핑한 발화
            episode_creator_type="GYM_SESSION",
            primary_subject_type="TEACHER",
            teacher_prompt=utterance,
            label_distribution={chosen_intent: 1.0},
        )
        session.add(episode)

    session.add(Evidence(
        evidence_id=evidence_id,
        episode_id=episode.episode_id,
        intent_id=chosen_intent,
        polarity="supports",
        strength=config.gym.evidence_strength,
        evidence_type=etype,
        actor_type=GYM_ACTOR_TYPE,
        trainer_ref=trainer_ref,
        adversarial=False,               # 절대 규칙 6: 자연 분포 신호
        context={
            "gym_mode": "live_quiz",
            "brain_guess": brain_top_intent,
            "shown_candidates": intent_candidates or [],
            # 감사 연결: 이 판정이 어느 추론 run에 대한 것인지 — 스냅샷 본체(후보·score·
            # stages)는 inference_logs가 request_id 인덱스로 보관한다. 뇌가 바뀐 뒤에도
            # 당시 추론으로 판정을 설명할 수 있다.
            "inference_request_id": inference_request_id,
        },
    ))
    session.flush()

    # §6-7 [5] 집계: 최소 신호 수 도달분만 전이 — 미달은 다음 트레이너 신호를 기다린다(§3-6)
    aggregated = 0
    if episode.label_state == "EVIDENCE_ACCUMULATING":
        rows = session.scalars(
            select(Evidence).where(Evidence.episode_id == episode.episode_id)
        ).all()
        result = aggregate(signals_from_rows(rows), config)
        if result.signal_count >= config.label_aggregator.min_label_functions:
            advance_label_state(episode, "AGGREGATION_READY")
            apply_aggregation(episode, result, config)  # → LABEL_CANDIDATE|REVIEW_REQUIRED, ≤SILVER
            aggregated = 1

    # §6-7 [6]: 노드 size/density 재집계 + pending 링. brightness는 건드리지 않는다.
    aggregate_evidence_stats(session)
    pending_set = False
    node = session.scalar(select(BrainNode).where(BrainNode.intent_id == chosen_intent))
    if node is not None:
        node.pending_evaluation = True  # §6-5 훈련됨·검증 대기 (규칙 3이 허용하는 필드)
        pending_set = True
    session.flush()

    return LiveReport(
        kind="confirmation" if confirmed else "correction",
        episode_id=episode.episode_id,
        evidence_created=1,
        episodes_aggregated=aggregated,
        label_states={episode.label_state: 1},
        pending_set=pending_set,
        node_intent=chosen_intent if node is not None else None,
    )


def _load_queue(path: Path) -> dict:
    if path.exists():
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    return {}


def queue_benchmark_candidate(
    session: Session,
    *,
    trainer_ref: str,
    utterance: str,
    chosen_intent: str,
    queue_path: Path | None = None,
) -> int:
    """출제 후보를 2차 검수 대기 YAML에 추가한다. DB에는 아무것도 쓰지 않는다(§8-2).

    같은 발화가 학습 분할에 이미 있으면 거부 — 뇌가 이미 본 문제로 시험을 보면 오염이다.
    반환: 큐의 총 문항 수.
    """
    if chosen_intent not in real_intent_ids():
        raise UnknownLiveIntent(chosen_intent)
    utterance = utterance.strip()

    clashing = session.scalars(
        select(Episode.episode_id).where(
            Episode.teacher_prompt == utterance,
            Episode.dataset_split != BENCHMARK_SPLIT,
        ).limit(1)
    ).first()
    if clashing is not None:
        raise TrainBenchmarkContamination(
            f"이미 학습 분할에 존재하는 발화다 (§8-2 학습/시험 오염): {utterance!r}"
        )

    path = queue_path or BENCHMARK_QUEUE_PATH
    doc = _load_queue(path)
    episodes: list[dict] = list(doc.get("episodes") or [])
    if any((e.get("teacher_prompt") or "").strip() == utterance for e in episodes):
        raise DuplicateBenchmarkCandidate(utterance)

    episodes.append({
        "episode_id": "EP_KTIB_LIVE_" + uuid.uuid4().hex[:12],
        "intent": chosen_intent,
        "lang": "ko",
        "reviewers": [trainer_ref],       # 1인째(출제자). 2인째가 blind로 확인 후 추가한다.
        "agreement_kappa": None,          # 2인째 확인 전 — 측정하지 않은 일치도는 기록하지 않는다
        "teacher_prompt": utterance,
    })
    authors = sorted({r for e in episodes for r in (e.get("reviewers") or []) if r})
    out = {
        "authored_by": ", ".join(authors) or trainer_ref,
        "approved_by": doc.get("approved_by") or APPROVED_BY_PLACEHOLDER,
        "origin_channel": "EXPERT_AUTHORED",
        "dataset_split": BENCHMARK_SPLIT,
        "episodes": episodes,
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        yaml.safe_dump(out, allow_unicode=True, sort_keys=False), encoding="utf-8"
    )
    return len(episodes)


def register_atlas_suggestion(session: Session, *, utterance: str) -> str:
    """온톨로지에 없는 의도 후보 발화 → atlas 확장 큐(PENDING). 노드는 만들지 않는다(규칙 4)."""
    entry = AtlasExpansionEntry(
        queue_id="AX_" + uuid.uuid4().hex[:12],
        utterance=utterance.strip(),
        source_run="gym_live",
    )
    session.add(entry)
    session.flush()
    return entry.queue_id


# --- blind 2차 검수 (§3-3) — 출제 대기열의 독립 검증 ---
#
# 대기열 항목에는 1차 검수자(출제자)의 intent가 있다. 2차 검수자가 그 라벨을 보고
# "확인"만 하면 독립 검수가 아니라 앵커링이다. 그래서 2차용 파일에는 **발화만** 준다 —
# intent·뇌 추측·후보 순위·confidence 전부 미포함. 2차가 독립적으로 라벨한 뒤 1차와
# 대조해, 배치 kappa가 하한을 넘고 항목이 일치할 때만 검수 완료로 기록한다.


class BlindBatchRejected(Exception):
    """배치 kappa가 하한 미달(또는 측정 불가) — 아무것도 확정하지 않는다 (§3-3)."""


class BlindReviewerInvalid(Exception):
    """2차 검수자가 비어 있거나 1차와 동일 인물(별칭 포함) — 자기 확인은 검수가 아니다."""


@dataclass
class BlindReviewReport:
    kappa: float
    kept: list[str] = field(default_factory=list)      # 검수 완료(2인 일치) episode_id
    rejected: list[str] = field(default_factory=list)  # 불일치 → 반려 episode_id
    skipped: list[str] = field(default_factory=list)   # blind 파일에 없어 보류


def build_blind_review_file(queue_path: Path | None = None) -> dict:
    """출제 대기열에서 2차 검수용 blind 문서를 만든다 — 발화만, 라벨 정보 일절 없음."""
    path = queue_path or BENCHMARK_QUEUE_PATH
    doc = _load_queue(path)
    pending = [
        e for e in (doc.get("episodes") or [])
        if len({r.strip().lower() for r in (e.get("reviewers") or []) if r.strip()}) < 2
    ]
    return {
        "_안내": (
            "발화만 보고 독립적으로 chosen_intent를 채우세요. "
            "1차 라벨·뇌 추측·후보 순위는 의도적으로 제공되지 않습니다(blind). "
            "판단이 서지 않으면 null(폐기 표)로 두세요."
        ),
        "reviewer_ref": "<2차 검수자 id>",
        "labels": [
            {
                "episode_id": e["episode_id"],
                "teacher_prompt": e["teacher_prompt"],
                "chosen_intent": None,
            }
            for e in pending
        ],
    }


def apply_blind_review(
    blind_doc: dict,
    config: ExperimentsConfig,
    *,
    queue_path: Path | None = None,
    write: bool = False,
) -> BlindReviewReport:
    """2차 독립 라벨을 1차와 대조한다. 배치 kappa 게이트 통과 시에만 확정.

    - 일치 항목: reviewers에 2차 추가 + agreement_kappa=배치 kappa 기록 (ingest 자격 완성)
    - 불일치·폐기 표: rejected 목록으로 이동(정직한 기록 — 조용히 버리지 않는다)
    - write=False면 대기열 파일을 건드리지 않는 dry-run
    """
    from app.aggregator.review import canonical_reviewer, cohens_kappa

    reviewer2_raw = str(blind_doc.get("reviewer_ref") or "").strip()
    reviewer2 = canonical_reviewer(reviewer2_raw)  # 비교는 정규화 신원, 기록은 원문
    if not reviewer2 or reviewer2_raw.startswith("<"):
        raise BlindReviewerInvalid("reviewer_ref(2차 검수자)를 채우세요")

    path = queue_path or BENCHMARK_QUEUE_PATH
    doc = _load_queue(path)
    episodes: list[dict] = list(doc.get("episodes") or [])
    by_id = {e["episode_id"]: e for e in episodes}

    second: dict[str, str | None] = {
        row["episode_id"]: row.get("chosen_intent")
        for row in (blind_doc.get("labels") or [])
        if row.get("episode_id") in by_id
    }
    if not second:
        raise BlindBatchRejected("대조할 라벨이 없다 — blind 파일이 비었거나 대기열과 안 맞는다")

    # 1차와 동일 인물(정규화 신원) 차단 — 별칭 두 개로 2인 검수를 위장할 수 없다 (§3-3)
    clashing = [
        eid for eid in second
        if reviewer2 in {canonical_reviewer(r) for r in (by_id[eid].get("reviewers") or [])}
    ]
    if clashing:
        raise BlindReviewerInvalid(
            f"1차 검수자와 동일 인물이다(별칭 포함) — 자기 확인은 검수가 아니다: {clashing[:5]}"
        )

    reject_mark = "__REJECT__"  # null(폐기 표)도 불일치로 세어 kappa를 정직하게 낮춘다
    ids = sorted(second)
    first_labels = [str(by_id[i]["intent"]) for i in ids]
    second_labels = [str(second[i]) if second[i] else reject_mark for i in ids]
    kappa = cohens_kappa(first_labels, second_labels)
    floor = config.review.min_agreement_kappa
    if kappa is None or kappa < floor:
        raise BlindBatchRejected(
            f"배치 kappa={kappa if kappa is not None else '측정불가'} < 하한 {floor} — "
            f"아무것도 확정하지 않는다 (§3-3)"
        )

    report = BlindReviewReport(kappa=kappa)
    kept_rows, rejected_rows = [], list(doc.get("rejected") or [])
    for e in episodes:
        eid = e["episode_id"]
        if eid not in second:
            report.skipped.append(eid)
            kept_rows.append(e)
            continue
        if second[eid] == e["intent"]:
            e = {**e, "reviewers": [*e.get("reviewers", []), reviewer2_raw],
                 "agreement_kappa": kappa}
            report.kept.append(eid)
            kept_rows.append(e)
        else:
            rejected_rows.append(
                {**e, "second_label": second[eid], "second_reviewer": reviewer2_raw}
            )
            report.rejected.append(eid)

    if write:
        out = {**doc, "episodes": kept_rows}
        if rejected_rows:
            out["rejected"] = rejected_rows
        path.write_text(
            yaml.safe_dump(out, allow_unicode=True, sort_keys=False), encoding="utf-8"
        )
    return report
