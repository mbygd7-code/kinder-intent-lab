"""Gym 세션 라이프사이클 (§8-1). 세션 생성 + 응답 제출 → GYM_HUMAN 에피소드 + evidence.

세션 아이템은 gym_sessions.results.items에 서버가 저장(제출은 item_id로 참조 — 클라이언트가
발화·정답을 위조하지 못하게). 제출 시 각 응답마다 GYM_HUMAN 에피소드(origin_channel=GYM_HUMAN,
creator=GYM_SESSION)를 만들고 트레이너가 고른 intent로 HUMAN evidence를 붙인다.
recovery_turns(교정드릴)는 세션 결과에 기록한다.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

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


def submit_results(
    session: Session,
    gym_session: GymSession,
    responses: list[dict],
    config: ExperimentsConfig,
) -> GymReport:
    """트레이너 응답 → GYM_HUMAN 에피소드 + HUMAN evidence. 세션에 없는 item_id는 무시."""
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
        recovery_turns = int(resp.get("recovery_turns", 0) or 0)

        ep_id = "EP_GYM_" + uuid.uuid4().hex[:12]
        session.add(Episode(
            episode_id=ep_id,
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
        ))
        session.add(Evidence(
            evidence_id="EV_GYM_" + uuid.uuid4().hex[:12],
            episode_id=ep_id,
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
        episodes_created += 1
        evidence_created += 1
        by_type[etype] = by_type.get(etype, 0) + 1
        recorded.append({
            "item_id": item["item_id"],
            "chosen_intent": chosen,
            "brain_guess": resp.get("brain_guess"),
            "recovery_turns": recovery_turns,
        })

    # JSONB 변경 감지를 위해 재할당
    gym_session.results = {**gym_session.results, "responses": recorded}
    session.flush()
    return GymReport(episodes_created, evidence_created, by_type, gym_session.session_id)
