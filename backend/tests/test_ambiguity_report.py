"""애매 발화 인사이트 리포트 AC — GET /v1/observatory/ambiguity-report (투트랙 채택 B′).

의견서 목표② "의도 분류 자체가 현장 인사이트": 어떤 의도가 자주 애매한가(clarify권 분포),
사람이 무엇을 고쳤나(교정 사례), 무엇이 분류 불능인가(atlas 큐)를 사람이 보는 리포트로 집계한다.
읽기 전용 — 어떤 테이블에도 쓰지 않는다. 출처를 분리한다: 추론은 mode(gym=오픈 전 실험실,
live/shadow=오픈 후 실사용), 교정은 origin_channel — 11월 이후 같은 리포트가 그대로 이어진다.
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete

from app.core.config import get_config
from app.core.db import get_session
from app.main import app
from app.models.brain import InferenceLog
from app.models.episodes import Episode, Evidence
from app.models.foundry import AtlasExpansionEntry

CFG = get_config()
M = CFG.decision.clarify_margin
C = CFG.decision.clarify_confidence


@pytest.fixture(autouse=True)
def _clean(db_session):
    """리포트가 세는 표만 비운다(세이브포인트 안 — 롤백 원복)."""
    db_session.execute(delete(InferenceLog))
    db_session.execute(delete(AtlasExpansionEntry))
    db_session.execute(delete(Evidence))
    db_session.execute(delete(Episode))
    db_session.flush()


@pytest.fixture()
def api(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        yield client, db_session
    app.dependency_overrides.clear()


def _log(db, *, mode="gym", intent="doc_summarize", margin=0.5, confidence=0.9) -> None:
    db.add(InferenceLog(
        inference_id="INF_" + uuid.uuid4().hex[:10],
        request_id="REQ_" + uuid.uuid4().hex[:8],
        mode=mode, top_intent=intent, confidence=confidence, margin=margin, stages={},
    ))
    db.flush()


def _correction(db, *, utterance, chosen, guessed, channel="GYM_HUMAN") -> None:
    ep_id = "EP_amb_" + uuid.uuid4().hex[:8]
    db.add(Episode(
        episode_id=ep_id, ontology_version="onto-test", lang="ko",
        dataset_split="TRAIN", origin_channel=channel,
        episode_creator_type="GYM_SESSION", primary_subject_type="TEACHER",
        teacher_prompt=utterance, label_distribution={chosen: 1.0},
    ))
    db.add(Evidence(
        evidence_id="EV_amb_" + uuid.uuid4().hex[:8], episode_id=ep_id, intent_id=chosen,
        polarity="supports", strength=0.5, evidence_type="HUMAN_CORRECTION",
        actor_type="TEACHER_TRAINER", trainer_ref="T1", adversarial=False,
        context={"brain_guess": guessed, "inference_request_id": "REQ_x"},
    ))
    db.flush()


def test_thresholds_echo_config_not_literals(api) -> None:
    """리포트가 쓰는 임계값은 config 단일 원천(규칙 1) — 응답에 그대로 에코된다."""
    client, _ = api
    body = client.get("/v1/observatory/ambiguity-report").json()
    assert body["thresholds"]["clarify_margin"] == M
    assert body["thresholds"]["clarify_confidence"] == C


def test_ambiguous_counted_per_source_and_intent(api) -> None:
    """clarify권(margin<하한 ∨ confidence<하한) 추론이 출처(mode)별·의도별로 집계된다."""
    client, db = api
    _log(db, mode="gym", intent="doc_summarize", margin=M - 0.01, confidence=0.9)   # 애매(margin)
    _log(db, mode="gym", intent="doc_summarize", margin=0.5, confidence=C - 0.01)   # 애매(confidence)
    _log(db, mode="gym", intent="play_expand", margin=0.5, confidence=0.9)          # 확신 — 미집계
    _log(db, mode="shadow", intent="op_notice_send", margin=M - 0.01, confidence=0.9)

    body = client.get("/v1/observatory/ambiguity-report").json()
    by = {s["source"]: s for s in body["sources"]}
    assert by["gym"]["total"] == 3 and by["gym"]["ambiguous"] == 2
    assert by["shadow"]["total"] == 1 and by["shadow"]["ambiguous"] == 1
    top = by["gym"]["top_ambiguous_intents"]
    assert top[0] == {"intent_id": "doc_summarize", "count": 2}
    assert all(t["intent_id"] != "play_expand" for t in top)  # 확신 추론은 애매 목록에 없다


def test_corrections_list_utterance_guess_and_channel(api) -> None:
    """교정 사례: 발화·사람 정답·뇌 추측·출처 채널이 그대로 보인다(brain_guess는 context 원천)."""
    client, db = api
    _correction(db, utterance="관찰 포인트 잡아줘", chosen="obs_set_watchpoint",
                guessed="refl_goal_alignment_check")
    body = client.get("/v1/observatory/ambiguity-report").json()
    assert len(body["corrections"]) == 1
    row = body["corrections"][0]
    assert row["utterance"] == "관찰 포인트 잡아줘"
    assert row["chosen"] == "obs_set_watchpoint"
    assert row["guessed"] == "refl_goal_alignment_check"
    assert row["origin_channel"] == "GYM_HUMAN"


def test_unclassified_comes_from_atlas_queue(api) -> None:
    client, db = api
    db.add(AtlasExpansionEntry(queue_id="AQ_" + uuid.uuid4().hex[:8],
                               utterance="이건 어떤 기능에도 없는 말", status="PENDING"))
    db.flush()
    body = client.get("/v1/observatory/ambiguity-report").json()
    assert len(body["unclassified"]) == 1
    assert body["unclassified"][0]["utterance"] == "이건 어떤 기능에도 없는 말"
    assert body["unclassified"][0]["status"] == "PENDING"


def test_empty_state_is_honest(api) -> None:
    """데이터가 없으면 0·빈 목록 — 지어내지 않는다."""
    client, _ = api
    body = client.get("/v1/observatory/ambiguity-report").json()
    assert body["sources"] == [] and body["corrections"] == [] and body["unclassified"] == []
