"""Gym 세션 라이프사이클 (§8-1). 세션 생성 + 응답 제출 → GYM_HUMAN 에피소드 + evidence.

세션 아이템은 gym_sessions.results.items에 서버가 저장(제출은 item_id로 참조 — 클라이언트가
발화·정답을 위조하지 못하게). 제출 시 응답마다 트레이너가 고른 intent로 HUMAN evidence를 만든다.
같은 발화의 GYM_HUMAN 에피소드가 아직 축적 중이면 **그 에피소드에 evidence를 덧붙인다** —
다른 트레이너의 신호가 쌓여야 §3-6 '최소 신호 수'와 §6-7 [5] '2인 일치 → SILVER' 경로가 열린다.
없으면 새 에피소드(origin_channel=GYM_HUMAN, creator=GYM_SESSION)를 만든다.
recovery_turns(교정드릴)는 세션 결과에 기록한다.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import ExperimentsConfig
from app.core.ontology import load_ontology
from app.gym.evidence import GYM_ACTOR_TYPE, evidence_type_for
from app.models.episodes import Episode, Evidence
from app.models.gym import ChallengePack, GymSession


@dataclass
class GymReport:
    episodes_created: int
    evidence_created: int
    by_type: dict[str, int]
    session_id: str


def start_session(
    session: Session,
    *,
    trainer_ref: str,
    mode: str,
    pack: ChallengePack,
    items: list[dict],
) -> GymSession:
    """세션 생성 — 아이템을 서버 측 results에 저장(제출이 item_id로 참조)."""
    evidence_type_for(mode)  # 미지원 모드면 여기서 즉시 실패
    gs = GymSession(
        session_id="GS_" + uuid.uuid4().hex[:12],
        pack_id=pack.pack_id,
        trainer_ref=trainer_ref,
        mode=mode,
        results={"items": items, "responses": []},
    )
    session.add(gs)
    session.flush()
    return gs


def _open_episode_for(session: Session, utterance: str) -> Episode | None:
    """같은 발화의 축적 중(EVIDENCE_ACCUMULATING) GYM_HUMAN 에피소드 — 두 번째 신호의 귀속처.

    episode_id 정렬로 결정론(같은 발화의 열린 에피소드가 여럿이어도 항상 같은 것에 붙는다).
    """
    return session.scalars(
        select(Episode)
        .where(
            Episode.origin_channel == "GYM_HUMAN",
            Episode.label_state == "EVIDENCE_ACCUMULATING",
            Episode.teacher_prompt == utterance,
        )
        .order_by(Episode.episode_id)
        .limit(1)
    ).first()


def submit_results(
    session: Session,
    gym_session: GymSession,
    responses: list[dict],
    config: ExperimentsConfig,
) -> GymReport:
    """트레이너 응답 → HUMAN evidence (같은 발화의 축적 중 에피소드에 덧붙이거나 새로 생성).

    세션에 없는 item_id·후보 밖 chosen_intent는 무시한다(지어내지 않음 + intent 위조 차단 —
    임의 문자열이 label_distribution·evidence.intent_id로 새는 것을 막는다. T4.3 리뷰).
    """
    items_by_id = {it["item_id"]: it for it in gym_session.results.get("items", [])}
    onto_version = load_ontology().version
    etype = evidence_type_for(gym_session.mode)

    by_type: dict[str, int] = {}
    recorded: list[dict] = []
    episodes_created = evidence_created = 0

    for resp in responses:
        item = items_by_id.get(resp.get("item_id"))
        chosen = resp.get("chosen_intent")
        if item is None or not chosen:
            continue  # 세션에 없는 아이템·빈 응답은 지어내지 않고 건너뛴다
        if chosen not in item.get("candidate_intents", []):
            continue  # 후보 밖 intent — 서버 보관 아이템만 신뢰(발화·정답 위조 방지와 동일 규율)
        recovery_turns = int(resp.get("recovery_turns", 0) or 0)

        # §6-7 [5] 2인 일치 경로: 같은 발화의 열린 에피소드가 있으면 신호를 덧붙인다
        episode = _open_episode_for(session, item["utterance"])
        if episode is None:
            episode = Episode(
                episode_id="EP_GYM_" + uuid.uuid4().hex[:12],
                ontology_version=onto_version,
                lang="ko",
                dataset_split="TRAIN",           # 벤치마크 아님 → 절대 규칙 2 무관
                reliability_tier="UNVERIFIED",   # 사람 1명 라벨 — 아직 미검증
                label_state="EVIDENCE_ACCUMULATING",
                origin_channel="GYM_HUMAN",      # 비합성 — 트레이너 산출
                episode_creator_type="GYM_SESSION",
                primary_subject_type="TEACHER",
                teacher_prompt=item["utterance"],
                label_distribution={chosen: 1.0},
            )
            session.add(episode)
            episodes_created += 1
        session.add(Evidence(
            evidence_id="EV_GYM_" + uuid.uuid4().hex[:12],
            episode_id=episode.episode_id,
            intent_id=chosen,
            polarity="supports",             # 트레이너가 고른 intent를 지지
            strength=config.gym.evidence_strength,
            evidence_type=etype,
            actor_type=GYM_ACTOR_TYPE,
            trainer_ref=gym_session.trainer_ref,
            adversarial=False,               # 절대 규칙 6: gym 기본 false
            context={
                "gym_mode": gym_session.mode,
                "challenge_pack": gym_session.pack_id,
                "recovery_turns": recovery_turns,
            },
        ))
        evidence_created += 1
        by_type[etype] = by_type.get(etype, 0) + 1
        recorded.append({
            "item_id": item["item_id"],
            "episode_id": episode.episode_id,  # finalize_session([5])이 aggregator로 흘릴 대상
            "chosen_intent": chosen,
            "brain_guess": resp.get("brain_guess"),
            "recovery_turns": recovery_turns,
        })

    # JSONB 변경 감지를 위해 재할당
    gym_session.results = {**gym_session.results, "responses": recorded}
    session.flush()
    return GymReport(episodes_created, evidence_created, by_type, gym_session.session_id)
