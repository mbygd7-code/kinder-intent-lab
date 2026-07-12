"""시험지 2차 검수 대기열 AC (§3-3·§8-2) — 웹 1~5 평점 검수 흐름.

- A가 문항+1~5 제출 → AWAITING_SECOND 대기
- pending 목록은 rating_a를 절대 노출하지 않는다(2차 검수자 anti-anchoring)
- 같은 사람은 2차 검수 불가(정규화 신원) · 재검수는 409(멱등)
- 2차 제출 시 가중 kappa 자동 계산 · 전부 동일 판정이면 None(등록 불가)
- 등록은 accepted(둘 다 min_item_rating↑)만 → GOLD∧LABELED∧BENCHMARK_HOLDOUT + KTIB 동결
- dry-run(commit=False)은 DB를 바꾸지 않는다 · kappa 미달이면 등록 거부
- 학습 오염(train split 발화)은 생성 단계에서 거부
"""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.core.config import get_config
from app.core.db import get_session
from app.core.ontology import load_ontology
from app.main import app
from app.models.arena import KtibItem, KtibVersion
from app.models.benchmark_candidates import (
    BenchmarkCandidateBatch,
    BenchmarkCandidateItem,
)
from app.models.episodes import Episode, Evidence

CFG = get_config()
FLOOR = CFG.review.min_item_rating  # 등록 대상 문항 점수 하한 (config)


@pytest.fixture()
def api(db_session):
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        yield client, db_session
    app.dependency_overrides.clear()


@pytest.fixture(autouse=True)
def _empty(db_session):
    for model in (BenchmarkCandidateItem, BenchmarkCandidateBatch,
                  KtibItem, KtibVersion, Evidence, Episode):
        db_session.execute(delete(model))
    db_session.flush()


def _intents(n=6):
    return [i.intent_id for i in load_ontology().intents if i.domain][:n]


def _items(intents, ratings):
    """intents[i] + '질문 i' + ratings[i] → 생성 요청 items."""
    return [
        {"intent": intents[i], "teacher_prompt": f"현장 질문 {i}번 — 실제 교사 말투", "rating": r}
        for i, r in enumerate(ratings)
    ]


def _create(client, reviewer, intents, ratings):
    res = client.post("/v1/observatory/ktib/candidates",
                      json={"reviewer": reviewer, "items": _items(intents, ratings)})
    assert res.status_code == 200, res.text
    return res.json()


def _train_episode(db, prompt):
    """학습 분할(TRAIN)에 이미 있는 발화 — 오염 가드 대상."""
    db.add(Episode(
        episode_id="EP_TRAIN_X", ontology_version="onto-1.0", lang="ko", dataset_split="TRAIN",
        reliability_tier="SILVER", label_state="LABEL_CANDIDATE", origin_channel="FOUNDRY_SYNTHETIC",
        episode_creator_type="FOUNDRY_PIPELINE", primary_subject_type="SIMULATED_TEACHER",
        teacher_prompt=prompt, label_distribution={_intents(1)[0]: 1.0},
    ))
    db.flush()


# --- 생성 ---


def test_create_batch_awaits_second(api) -> None:
    client, _ = api
    b = _create(client, "김유아", _intents(3), [5, 4, 3])
    assert b["status"] == "AWAITING_SECOND"
    assert b["item_count"] == 3
    assert b["registerable"] is False
    assert b["agreement_kappa"] is None


def test_create_rejects_train_contamination(api) -> None:
    client, db = api
    _train_episode(db, "현장 질문 0번 — 실제 교사 말투")  # _items의 0번 프롬프트와 동일
    res = client.post("/v1/observatory/ktib/candidates",
                      json={"reviewer": "김유아", "items": _items(_intents(2), [5, 4])})
    assert res.status_code == 409 and "학습 문항" in res.json()["detail"]


def test_create_rejects_unknown_intent(api) -> None:
    client, _ = api
    res = client.post("/v1/observatory/ktib/candidates", json={
        "reviewer": "김유아",
        "items": [{"intent": "not_a_real_intent", "teacher_prompt": "질문", "rating": 5}],
    })
    assert res.status_code == 422


# --- 대기 목록 (blind) ---


def test_pending_hides_rating_a_and_excludes_own(api) -> None:
    client, _ = api
    _create(client, "김유아", _intents(2), [5, 4])
    # A 자신이 보면: pending 없음(내 것 제외), mine에 있음
    mine_view = client.get("/v1/observatory/ktib/candidates", params={"reviewer": "김유아"}).json()
    assert mine_view["pending"] == []
    assert len(mine_view["mine"]) == 1 and mine_view["mine"][0]["status"] == "AWAITING_SECOND"
    # B가 보면: pending에 뜨고, item에 rating_a/rating이 절대 없다(anti-anchoring)
    b_view = client.get("/v1/observatory/ktib/candidates", params={"reviewer": "이교사"}).json()
    assert len(b_view["pending"]) == 1
    item = b_view["pending"][0]["items"][0]
    assert set(item.keys()) == {"item_id", "intent", "teacher_prompt"}
    assert "rating" not in item and "rating_a" not in item


# --- 2차 검수 ---


def _second_review(client, batch_id, reviewer, batch_items, ratings):
    payload = {"reviewer": reviewer,
               "ratings": [{"item_id": it["item_id"], "rating": r}
                           for it, r in zip(batch_items, ratings, strict=True)]}
    return client.post(f"/v1/observatory/ktib/candidates/{batch_id}/review", json=payload)


def _pending_items(client, reviewer, batch_id):
    view = client.get("/v1/observatory/ktib/candidates", params={"reviewer": reviewer}).json()
    batch = next(b for b in view["pending"] if b["batch_id"] == batch_id)
    return batch["items"]


def test_same_person_cannot_second_review(api) -> None:
    client, _ = api
    b = _create(client, "김유아", _intents(2), [5, 4])
    items = _pending_items(client, "이교사", b["batch_id"])
    res = _second_review(client, b["batch_id"], "  KIM유아 ", items, [5, 4])  # 정규화하면 동일?
    # "김유아" vs "KIM유아"는 다른 사람 — 통과. 진짜 동일인만 막힌다:
    assert res.status_code == 200
    b2 = _create(client, "박교사", _intents(2), [5, 4])
    items2 = _pending_items(client, "이교사", b2["batch_id"])
    same = _second_review(client, b2["batch_id"], " 박교사 ", items2, [5, 4])
    assert same.status_code == 409 and "다른 사람" in same.json()["detail"]


def test_second_review_computes_kappa_and_marks_registerable(api) -> None:
    client, _ = api
    b = _create(client, "김유아", _intents(6), [5, 5, 5, 2, 1, 1])
    items = _pending_items(client, "이교사", b["batch_id"])
    res = _second_review(client, b["batch_id"], "이교사", items, [5, 4, 5, 2, 1, 1])
    assert res.status_code == 200, res.text
    out = res.json()
    assert out["status"] == "SECOND_DONE"
    assert out["agreement_kappa"] is not None and out["agreement_kappa"] >= 0.65
    assert out["accepted_count"] == 3   # (5,5)(5,4)(5,5) 만 둘 다 4↑
    assert out["registerable"] is True


def test_all_same_ratings_kappa_none_not_registerable(api) -> None:
    client, _ = api
    b = _create(client, "김유아", _intents(3), [4, 4, 4])
    items = _pending_items(client, "이교사", b["batch_id"])
    out = _second_review(client, b["batch_id"], "이교사", items, [4, 4, 4]).json()
    assert out["agreement_kappa"] is None   # 변별 0 — 지어내지 않음
    assert out["registerable"] is False


def test_double_second_review_conflicts(api) -> None:
    client, _ = api
    b = _create(client, "김유아", _intents(2), [5, 4])
    items = _pending_items(client, "이교사", b["batch_id"])
    assert _second_review(client, b["batch_id"], "이교사", items, [5, 4]).status_code == 200
    # 이미 SECOND_DONE — 다시 검수 시도는 409
    again = client.post(f"/v1/observatory/ktib/candidates/{b['batch_id']}/review",
                        json={"reviewer": "최교사",
                              "ratings": [{"item_id": items[0]["item_id"], "rating": 5},
                                          {"item_id": items[1]["item_id"], "rating": 5}]})
    assert again.status_code == 409


# --- 등록 ---


def _prepare_ready(client, ratings_a, ratings_b, intents=None):
    intents = intents or _intents(len(ratings_a))
    b = _create(client, "김유아", intents, ratings_a)
    items = _pending_items(client, "이교사", b["batch_id"])
    _second_review(client, b["batch_id"], "이교사", items, ratings_b)
    return b["batch_id"]


def test_register_dry_run_then_commit_creates_gold_and_ktib(api) -> None:
    client, db = api
    batch_id = _prepare_ready(client, [5, 5, 5, 2, 1, 1], [5, 4, 5, 2, 1, 1])

    # dry-run — DB에 아무 episode도 남지 않는다
    dry = client.post(f"/v1/observatory/ktib/candidates/{batch_id}/register",
                      json={"reviewer": "총괄", "commit": False}).json()
    assert dry["ok"] is True and dry["dry_run"] is True and dry["inserted"] == 3
    assert db.scalar(select(Episode).limit(1)) is None
    assert db.get(BenchmarkCandidateBatch, batch_id).status == "SECOND_DONE"

    # commit — accepted 3문항이 GOLD∧LABELED∧BENCHMARK_HOLDOUT로 등록 + KTIB 동결
    real = client.post(f"/v1/observatory/ktib/candidates/{batch_id}/register",
                       json={"reviewer": "총괄", "commit": True}).json()
    assert real["ok"] is True and real["dry_run"] is False and real["ktib_version"]
    eps = db.scalars(select(Episode)).all()
    assert len(eps) == 3
    for ep in eps:
        assert ep.dataset_split == "BENCHMARK_HOLDOUT"
        assert ep.reliability_tier == "GOLD" and ep.label_state == "LABELED"
        assert ep.origin_channel == "EXPERT_AUTHORED"
        assert sorted(ep.human_review["reviewers"]) == ["김유아", "이교사"]
    batch = db.get(BenchmarkCandidateBatch, batch_id)
    assert batch.status == "REGISTERED" and batch.ktib_version == real["ktib_version"]


def test_register_blocked_when_kappa_below_floor(api) -> None:
    client, _ = api
    # 강한 불일치 → 가중 kappa 낮음 → 등록 거부
    batch_id = _prepare_ready(client, [5, 4, 5, 4, 1, 2], [1, 2, 1, 2, 5, 4])
    res = client.post(f"/v1/observatory/ktib/candidates/{batch_id}/register",
                      json={"reviewer": "총괄", "commit": True})
    assert res.status_code == 409 and "일치도" in res.json()["detail"]


def test_register_blocked_when_no_accepted_items(api) -> None:
    client, _ = api
    # 일치도는 높지만 둘 다 낮은 점수(등록 대상 문항 0)
    batch_id = _prepare_ready(client, [1, 2, 3, 1, 2, 3], [1, 2, 3, 1, 2, 3])
    res = client.post(f"/v1/observatory/ktib/candidates/{batch_id}/register",
                      json={"reviewer": "총괄", "commit": True})
    assert res.status_code == 409 and "높게 평가한 문항" in res.json()["detail"]
