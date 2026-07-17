"""공부 데이터 웹 검수 AC — /v1/review (투트랙 세트 ③, 2026-07-17 사용자 승인).

YAML 검수(run_human_review)의 웹 판이다. 표(votes)는 review_votes에 모으고, 적용은
aggregator.review.apply_review_batch(GOLD 유일문)에 그대로 넣는다 — 우회 승격 경로를
만들지 않는다(§3-3: 2인·만장일치·배치 kappa는 그 문이 강제).

- 큐는 blind: 다른 검수자의 표·집계 제안을 절대 싣지 않는다(앵커링 방지)
- 한 사람 한 표(재제출=갱신), 온톨로지 밖 intent 거부
- 적용 성공 시 backfill(대표 예문) 자동 체인 — run_human_review와 동일
"""
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.api.review import get_review_embed
from app.core.db import get_session
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.main import app
from app.models.brain import BrainNode, Exemplar
from app.models.episodes import Episode, Evidence, ReviewVoteRow

INTENTS = [i.intent_id for i in load_ontology().intents if i.intent_id != UNKNOWN_INTENT_ID]


def _embed(dim: int = 1536):  # exemplars.embedding Vector(1536)와 일치
    """결정론 mock 임베딩 — backfill 체인 주입용(실 네트워크 없음)."""
    def fn(texts: list[str]) -> list[list[float]]:
        return [[(hash(t) % 97) / 97.0] * dim for t in texts]
    return fn


@pytest.fixture(autouse=True)
def _clean(db_session):
    db_session.execute(delete(ReviewVoteRow))
    db_session.execute(delete(Exemplar))
    db_session.execute(delete(Evidence))
    db_session.execute(delete(Episode))
    db_session.execute(delete(BrainNode))
    db_session.flush()


@pytest.fixture()
def api(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_review_embed] = lambda: _embed()
    with TestClient(app) as client:
        yield client, db_session
    app.dependency_overrides.clear()


def _episode(db, prompt: str) -> str:
    eid = "EP_rv_" + uuid.uuid4().hex[:8]
    db.add(Episode(
        episode_id=eid, ontology_version="onto-test", lang="ko",
        dataset_split="TRAIN", origin_channel="FOUNDRY_SYNTHETIC",
        episode_creator_type="FOUNDRY_PIPELINE", primary_subject_type="TEACHER",
        teacher_prompt=prompt, label_distribution={},
        label_state="LABEL_CANDIDATE", reliability_tier="SILVER",
    ))
    db.flush()
    return eid


def _vote(client, reviewer, episode_id, intent):
    return client.post("/v1/review/vote", json={
        "reviewer": reviewer, "episode_id": episode_id, "chosen_intent": intent,
    })


def test_queue_is_blind_and_excludes_my_votes(api) -> None:
    """큐는 발화만 준다(제안·타인 표 없음 — 앵커링 방지). 내가 표를 낸 건 빠진다."""
    client, db = api
    e1, e2 = _episode(db, "검수 발화 하나"), _episode(db, "검수 발화 둘")
    assert _vote(client, "명배영", e1, INTENTS[0]).status_code == 200

    q = client.get("/v1/review/queue", params={"reviewer": "명배영"}).json()
    ids = [i["episode_id"] for i in q["items"]]
    assert e1 not in ids and e2 in ids
    assert q["my_done"] == 1 and q["total_reviewable"] == 2
    # blind — 허용 필드만 (suggests/다른 표/집계 힌트가 실리면 실패해야 한다)
    assert set(q["items"][0].keys()) == {"episode_id", "teacher_prompt", "lang", "origin_channel"}

    q2 = client.get("/v1/review/queue", params={"reviewer": "조선생"}).json()
    assert len(q2["items"]) == 2  # 다른 검수자는 아직 둘 다 대기


def test_vote_upsert_and_unknown_intent_rejected(api) -> None:
    """같은 사람 재제출은 갱신(한 표 유지). 온톨로지 밖 intent는 422 — 지어낸 라벨 금지."""
    client, db = api
    e1 = _episode(db, "업서트 발화")
    assert _vote(client, "명배영", e1, INTENTS[0]).status_code == 200
    r2 = _vote(client, "명배영 ", e1, INTENTS[1])  # 뒤공백 별칭 — 같은 사람(canonical)
    assert r2.status_code == 200 and r2.json()["updated"] is True
    votes = db.scalars(select(ReviewVoteRow)).all()
    assert len(votes) == 1 and votes[0].chosen_intent == INTENTS[1]

    assert _vote(client, "명배영", e1, "NOT_A_REAL_INTENT").status_code == 422
    assert _vote(client, "명배영", "EP_nope", INTENTS[0]).status_code == 404


def test_apply_two_reviewers_promotes_gold_and_chains_backfill(api) -> None:
    """★ 2인 일치분만 GOLD — 적용은 유일문(apply_review_batch) 경유, 성공 시 대표 예문 체인."""
    client, db = api
    eps = [_episode(db, f"승격 발화 {i} — 유일문 검증") for i in range(4)]
    # 4건 중 3건 일치, 1건 불일치 → 배치 kappa ≈ 0.69 (≥0.65 통과)
    for i, e in enumerate(eps):
        _vote(client, "명배영", e, INTENTS[i])
    for i, e in enumerate(eps[:3]):
        _vote(client, "조선생", e, INTENTS[i])
    _vote(client, "조선생", eps[3], INTENTS[10])  # 불일치 1건

    r = client.post("/v1/review/apply", json={"approved_by": "운영자"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["labeled"] == 3 and body["unchanged"] == 1
    assert body["kappa"] is not None and body["kappa"] >= 0.65
    assert body["exemplars_added"] >= 1  # backfill 자동 체인(GOLD+LABELED → 대표 예문)

    gold = db.scalars(select(Episode).where(Episode.reliability_tier == "GOLD")).all()
    assert len(gold) == 3
    assert all(e.label_state == "LABELED" for e in gold)
    # 확정된 에피소드는 큐에서 사라진다 — 남은 건 불일치 1건뿐
    q = client.get("/v1/review/queue", params={"reviewer": "제3자"}).json()
    assert q["total_reviewable"] == 1


def test_apply_low_kappa_rejects_batch_and_changes_nothing(api) -> None:
    """배치 kappa 미달이면 409 — 아무 에피소드도 확정되지 않는다(부분 승격 금지)."""
    client, db = api
    eps = [_episode(db, f"저일치 발화 {i}") for i in range(3)]
    for i, e in enumerate(eps):
        _vote(client, "명배영", e, INTENTS[i])
        _vote(client, "조선생", e, INTENTS[i + 20])  # 전부 불일치

    r = client.post("/v1/review/apply", json={"approved_by": "운영자"})
    assert r.status_code == 409
    assert db.scalars(select(Episode).where(Episode.reliability_tier == "GOLD")).all() == []
    assert all(
        e.label_state == "LABEL_CANDIDATE"
        for e in db.scalars(select(Episode)).all()
    )


def test_apply_requires_two_reviewers(api) -> None:
    """1인 표만으로는 적용 불가 — 명확한 안내와 함께 409 (1인 확정 금지 §3-3)."""
    client, db = api
    e1 = _episode(db, "혼자 검수 발화")
    _vote(client, "명배영", e1, INTENTS[0])
    r = client.post("/v1/review/apply", json={"approved_by": "운영자"})
    assert r.status_code == 409 and "2" in r.json()["detail"]


def test_status_reports_progress(api) -> None:
    client, db = api
    e1, e2 = _episode(db, "상태 발화 1"), _episode(db, "상태 발화 2")
    _vote(client, "명배영", e1, INTENTS[0])
    _vote(client, "조선생", e1, INTENTS[0])
    _vote(client, "명배영", e2, INTENTS[1])

    s = client.get("/v1/review/status").json()
    assert s["reviewable_total"] == 2
    assert s["ready_total"] == 1  # 2인 표가 모인 에피소드 수
    names = {r["name"]: r["votes"] for r in s["reviewers"]}
    assert names["명배영"] == 2 and names["조선생"] == 1
