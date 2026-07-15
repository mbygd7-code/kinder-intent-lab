"""즉석 문답(Live Quiz) AC — POST /v1/gym/live/feedback (§3-1·§3-2·§6-7 [5][6]).

- 훈련용: 사람이 타이핑한 발화 + 판정 → GYM_HUMAN 에피소드 + HUMAN evidence
  (뇌 추측과 일치=CONFIRMATION, 다르면=CORRECTION). 같은 발화의 축적 중 에피소드에
  2인째 신호가 덧붙고, 최소 신호 수 도달 시 집계 전이(§6-7 [5]).
- 출제용: DB에 아무것도 만들지 않는다 — expert_ingest 호환 YAML 큐에만 적재
  (KTIB 유일 입구 §8-2 유지, 뇌 추측 미기록 = blind 2차 검수). TRAIN 오염은 409.
- 온톨로지 밖 의도 제안 → atlas_expansion_queue(PENDING)만. 노드 자동 생성 없음(규칙 4).
- brightness는 절대 불변(규칙 3). 훈련 반영은 size/density/pending 링만(§6-5).
"""
import uuid

import pytest
import yaml
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.brain.backfill import bootstrap_nodes, select_exemplars
from app.core.config import get_config
from app.core.db import get_session
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.main import app
from app.models.arena import ArenaRun, KtibItem, KtibVersion
from app.models.brain import BrainNode, Exemplar
from app.models.episodes import Episode, Evidence
from app.models.foundry import AtlasExpansionEntry

CFG = get_config()


@pytest.fixture(autouse=True)
def _clean_bank(db_session):
    """전역 카운트 단언용 빈 뱅크 + 노드 부트스트랩(거버넌스 경로, 멱등) — 세이브포인트 안.
    FK 순서: arena_runs→ktib_versions, ktib_items→episodes — ArenaRun→KTIB→episode 순
    (test_promote와 동일 규율)."""
    db_session.execute(delete(ArenaRun))
    db_session.execute(delete(KtibItem))
    db_session.execute(delete(KtibVersion))
    db_session.execute(delete(Evidence))
    db_session.execute(delete(Exemplar))
    db_session.execute(delete(Episode))
    db_session.execute(delete(AtlasExpansionEntry))
    bootstrap_nodes(db_session, approved_by="test_gym_live")
    db_session.flush()


@pytest.fixture()
def api(db_session, tmp_path, monkeypatch):
    import app.gym.live as live_mod

    monkeypatch.setattr(
        live_mod, "BENCHMARK_QUEUE_PATH", tmp_path / "benchmark_candidates.yaml"
    )
    app.dependency_overrides[get_session] = lambda: db_session
    with TestClient(app) as client:
        yield client, db_session, tmp_path / "benchmark_candidates.yaml"
    app.dependency_overrides.clear()


def _intent(idx=0):
    return [i.intent_id for i in load_ontology().intents if i.domain][idx]


def _post(client, **over):
    body = {
        "feedback_id": uuid.uuid4().hex[:12],
        "trainer_ref": "TR_LIVE",
        "utterance": "블록으로 만든 성 사진 좀 정리해줘",
        "brain_top_intent": _intent(0),
        "chosen_intent": _intent(0),
        "purpose": "training",
    }
    body.update(over)
    return client.post("/v1/gym/live/feedback", json=body)


# --- 훈련용: evidence 생성 + provenance ---


def test_confirmation_creates_gym_human_episode_with_provenance(api) -> None:
    client, db, _ = api
    r = _post(client)  # chosen == brain_top → 확인
    assert r.status_code == 200, r.text
    rep = r.json()
    assert rep["kind"] == "confirmation" and rep["evidence_created"] == 1

    ep = db.get(Episode, rep["episode_id"])
    # provenance 4필드(규칙 9) + 훈련 칸 명시
    assert ep.origin_channel == "GYM_HUMAN"
    assert ep.episode_creator_type == "GYM_SESSION"
    assert ep.primary_subject_type == "TEACHER"
    assert ep.dataset_split == "TRAIN"
    assert ep.teacher_prompt == "블록으로 만든 성 사진 좀 정리해줘"

    ev = db.scalars(select(Evidence).where(Evidence.episode_id == ep.episode_id)).one()
    assert ev.evidence_type == "HUMAN_CONFIRMATION"
    assert ev.actor_type == "TEACHER_TRAINER"
    assert ev.strength == CFG.gym.evidence_strength  # 임계값은 config에서만(규칙 1)
    assert ev.adversarial is False  # 규칙 6
    assert ev.context.get("gym_mode") == "live_quiz"


def test_correction_when_choice_differs_from_brain_guess(api) -> None:
    client, db, _ = api
    r = _post(client, brain_top_intent=_intent(1))  # 뇌 추측과 다른 정답 → 교정
    assert r.status_code == 200
    assert r.json()["kind"] == "correction"
    ev = db.scalars(select(Evidence)).one()
    assert ev.evidence_type == "HUMAN_CORRECTION"


def test_correction_when_brain_abstained(api) -> None:
    client, db, _ = api
    r = _post(client, brain_top_intent=None)  # 뇌가 abstain → 사람이 기록 = 교정(미스 문서화)
    assert r.status_code == 200
    assert r.json()["kind"] == "correction"


# --- §6-7 [5]: 2인째 신호는 같은 에피소드에 덧붙고, 최소 신호 수 도달 시 전이 ---


def test_second_signal_reuses_open_episode_and_aggregates(api) -> None:
    client, db, _ = api
    first = _post(client, trainer_ref="TR_A").json()
    second = _post(client, trainer_ref="TR_B").json()

    assert second["episode_id"] == first["episode_id"]  # 새 에피소드가 아니라 덧붙음
    eps = db.scalars(select(Episode)).all()
    assert len(eps) == 1
    evs = db.scalars(select(Evidence)).all()
    assert len(evs) == 2

    # min_label_functions(=2) 도달 → 집계 전이(LABEL_CANDIDATE = 검수 가능 상태)
    assert second["episodes_aggregated"] == 1
    assert eps[0].label_state == "LABEL_CANDIDATE"
    assert eps[0].reliability_tier in ("BRONZE", "SILVER")  # 자동 경로 상한 ≤ SILVER(§3-6)


# --- §6-5·규칙 3: pending 링만 켜지고 brightness는 불변 ---


def test_pending_ring_set_and_brightness_untouched(api) -> None:
    client, db, _ = api
    node_intent = _intent(0)
    node = db.scalar(select(BrainNode).where(BrainNode.intent_id == node_intent))
    node.pending_evaluation = False
    db.flush()
    before_heldout = node.heldout_accuracy

    rep = _post(client, chosen_intent=node_intent, brain_top_intent=node_intent).json()
    assert rep["pending_set"] is True and rep["node_intent"] == node_intent

    db.refresh(node)
    assert node.pending_evaluation is True          # 훈련됨·검증 대기 링(§6-5)
    assert node.heldout_accuracy == before_heldout  # 밝기는 Arena만(규칙 3)


# --- 온톨로지 밖: atlas 큐 등록(규칙 4 — 노드 자동 생성 없음) ---


def test_unknown_intent_goes_to_atlas_queue(api) -> None:
    client, db, _ = api
    r = _post(client, chosen_intent=None, suggest_new_intent=True,
              utterance="교실 벽에 붙일 계절 장식 도안 뽑아줘")
    assert r.status_code == 200
    assert r.json()["kind"] == "atlas_queued"

    rows = db.scalars(select(AtlasExpansionEntry)).all()
    assert len(rows) == 1 and rows[0].status == "PENDING"
    assert rows[0].utterance == "교실 벽에 붙일 계절 장식 도안 뽑아줘"
    # 에피소드·evidence·노드는 만들지 않는다
    assert db.scalars(select(Episode)).all() == []
    assert db.scalars(select(Evidence)).all() == []


def test_fabricated_intent_rejected(api) -> None:
    client, db, _ = api
    for bad in ("NOT_A_REAL_INTENT", UNKNOWN_INTENT_ID):
        r = _post(client, chosen_intent=bad)
        assert r.status_code == 422, bad  # 임의 문자열이 라벨·evidence로 새는 것 차단
    assert db.scalars(select(Evidence)).all() == []


def test_suggest_new_with_chosen_intent_rejected(api) -> None:
    client, _, _ = api
    r = _post(client, suggest_new_intent=True)  # chosen_intent와 동시 지정 → 모순
    assert r.status_code == 422


# --- 출제용: DB 무기록, expert_ingest 호환 큐 파일, blind ---


def test_benchmark_purpose_writes_queue_not_db(api) -> None:
    client, db, qpath = api
    r = _post(client, purpose="benchmark",
              utterance="우리 반 알림장 초안 좀 잡아줘", chosen_intent=_intent(2))
    assert r.status_code == 200
    rep = r.json()
    assert rep["kind"] == "benchmark_queued" and rep["benchmark_queue_size"] == 1
    # KTIB 유일 입구(§8-2) 유지 — DB에는 아무것도 만들지 않는다
    assert db.scalars(select(Episode)).all() == []
    assert db.scalars(select(Evidence)).all() == []

    doc = yaml.safe_load(qpath.read_text(encoding="utf-8"))
    assert doc["origin_channel"] == "EXPERT_AUTHORED"
    assert doc["dataset_split"] == "BENCHMARK_HOLDOUT"
    (item,) = doc["episodes"]
    assert item["teacher_prompt"] == "우리 반 알림장 초안 좀 잡아줘"
    assert item["intent"] == _intent(2)
    assert item["reviewers"] == ["TR_LIVE"]        # 1인째 — 2인째는 blind로 추가
    assert item["agreement_kappa"] is None         # 2인째 확인 전
    assert "brain" not in yaml.dump(item, allow_unicode=True).lower()  # blind: 뇌 추측 미기록


def test_benchmark_train_contamination_rejected(api) -> None:
    client, db, _ = api
    utter = "산책 나가기 전에 준비물 목록 만들어줘"
    assert _post(client, utterance=utter).status_code == 200  # 훈련에 먼저 사용
    r = _post(client, purpose="benchmark", utterance=utter)
    assert r.status_code == 409  # 같은 발화가 학습·시험 양쪽에 가면 오염(§8-2)


def test_duplicate_feedback_id_conflict(api) -> None:
    client, db, _ = api
    fid = "dupdupdupdup"
    assert _post(client, feedback_id=fid).status_code == 200
    r = _post(client, feedback_id=fid)  # 더블클릭·재시도 → 이중 계상 차단
    assert r.status_code == 409
    assert len(db.scalars(select(Evidence)).all()) == 1


# --- Q-2: infer↔feedback 감사 연결 — 판정이 어느 추론 run에 대한 것인지 남는다 ---


def test_feedback_links_inference_request_id(api) -> None:
    client, db, _ = api
    r = _post(client, inference_request_id="REQ_LIVEQ_audit001")
    assert r.status_code == 200
    ev = db.scalars(select(Evidence)).one()
    # 스냅샷 본체는 inference_logs(request_id 인덱스) — evidence는 연결고리만 보관
    assert ev.context.get("inference_request_id") == "REQ_LIVEQ_audit001"


# --- Q-2: §8-2 격리 — HOLDOUT 에피소드는 exemplar/retrieval에 절대 노출되지 않는다 ---


def _gold_episode(db, *, split: str, intent: str, prompt: str) -> Episode:
    ep = Episode(
        episode_id="EP_T_" + uuid.uuid4().hex[:12],
        ontology_version=load_ontology().version,
        lang="ko",
        dataset_split=split,
        reliability_tier="GOLD",
        label_state="LABELED",
        origin_channel="EXPERT_AUTHORED",
        episode_creator_type="HUMAN_ANNOTATOR",
        primary_subject_type="TEACHER",
        teacher_prompt=prompt,
        label_distribution={intent: 1.0},
    )
    db.add(ep)
    db.flush()
    return ep


def test_benchmark_episode_never_selected_as_exemplar(db_session) -> None:
    intent = _intent(0)
    train = _gold_episode(db_session, split="TRAIN", intent=intent, prompt="훈련용 발화 하나")
    holdout = _gold_episode(
        db_session, split="BENCHMARK_HOLDOUT", intent=intent, prompt="시험용 발화 하나"
    )

    # 결정론 mock 임베딩 — 프롬프트마다 다른 기저 벡터(서로 멀리 떨어짐)
    def embed(texts: list[str]) -> list[list[float]]:
        out = []
        for t in texts:
            v = [0.0] * 1536
            v[hash(t) % 1536] = 1.0
            out.append(v)
        return out

    select_exemplars(db_session, CFG, embed)
    picked = set(db_session.scalars(select(Exemplar.episode_id)).all())
    assert train.episode_id in picked      # 훈련 GOLD는 검색 기반이 된다
    assert holdout.episode_id not in picked  # 시험지는 학습 파이프라인에 절대 노출 금지(§8-2)


# --- Q-2: 원자성 — 처리 중 예외 시 Episode-only 부분 저장이 없다 ---


def test_feedback_failure_leaves_no_partial_rows(db_session, monkeypatch) -> None:
    import app.gym.live as live_mod
    from app.gym.live import record_training_feedback

    # evidence 생성 이후 단계(집계 반영)에서 실패를 강제 — 프로덕션 get_session은 예외 시
    # 요청 트랜잭션 전체를 rollback 한다. 여기선 savepoint로 그 의미를 그대로 재현한다.
    def boom(session):
        raise RuntimeError("집계 단계 강제 실패")

    monkeypatch.setattr(live_mod, "aggregate_evidence_stats", boom)

    sp = db_session.begin_nested()
    with pytest.raises(RuntimeError):
        record_training_feedback(
            db_session,
            feedback_id="atomicatomic1",
            trainer_ref="TR_ATOM",
            utterance="원자성 검증용 발화",
            chosen_intent=_intent(0),
            brain_top_intent=None,
            config=CFG,
        )
    sp.rollback()

    assert db_session.scalars(
        select(Episode).where(Episode.teacher_prompt == "원자성 검증용 발화")
    ).all() == []
    assert db_session.get(Evidence, "EV_LIVE_atomicatomic1") is None


# --- Q-2: 온톨로지에 존재하는 intent 선택은 atlas 큐에 아무것도 남기지 않는다 ---


def test_existing_intent_choice_never_touches_atlas_queue(api) -> None:
    client, db, _ = api
    assert _post(client, chosen_intent=_intent(3)).status_code == 200
    assert db.scalars(select(AtlasExpansionEntry)).all() == []


# --- Q-2: blind 2차 검수 (§3-3) — 1차 라벨을 보지 않은 독립 검증만 확정된다 ---


def _seed_queue(client, *pairs: tuple[str, str]) -> None:
    """즉석 문답 '출제' 경로로 대기열을 채운다 (utterance, intent) 쌍들."""
    for utter, intent in pairs:
        r = _post(client, purpose="benchmark", utterance=utter, chosen_intent=intent)
        assert r.status_code == 200, r.text


def test_blind_file_contains_utterances_only(api) -> None:
    from app.gym.live import build_blind_review_file

    client, _, qpath = api
    _seed_queue(client, ("발화 하나", _intent(0)), ("발화 둘", _intent(1)))

    blind = build_blind_review_file(qpath)
    assert [row["teacher_prompt"] for row in blind["labels"]] == ["발화 하나", "발화 둘"]
    # blind 보장: 항목 키는 정확히 셋(발화 + 빈 라벨 칸) — 1차 라벨이 실릴 자리 자체가 없다
    for row in blind["labels"]:
        assert set(row) == {"episode_id", "teacher_prompt", "chosen_intent"}
        assert row["chosen_intent"] is None
    dumped = yaml.safe_dump(blind, allow_unicode=True).lower()
    # 1차 라벨 값·뇌 추측·후보·confidence가 어디에도 새지 않는다
    for banned in (_intent(0), _intent(1), "brain", "candidate", "confidence"):
        assert banned not in dumped, banned


def test_blind_agreement_completes_reviewers_and_kappa(api) -> None:
    from app.gym.live import apply_blind_review, build_blind_review_file

    client, _, qpath = api
    _seed_queue(client, ("발화 하나", _intent(0)), ("발화 둘", _intent(1)))
    blind = build_blind_review_file(qpath)
    blind["reviewer_ref"] = "TR_second"
    for row in blind["labels"]:  # 독립 라벨이 1차와 일치하는 시나리오
        row["chosen_intent"] = _intent(0) if row["teacher_prompt"] == "발화 하나" else _intent(1)

    report = apply_blind_review(blind, CFG, queue_path=qpath, write=True)
    assert report.kappa == 1.0 and len(report.kept) == 2 and report.rejected == []

    doc = yaml.safe_load(qpath.read_text(encoding="utf-8"))
    for e in doc["episodes"]:
        assert sorted(e["reviewers"]) == ["TR_LIVE", "TR_second"]  # 서로 다른 2인(§3-3)
        assert e["agreement_kappa"] == 1.0                          # 측정된 일치도 기록


def test_blind_low_kappa_rejects_whole_batch(api) -> None:
    from app.gym.live import BlindBatchRejected, apply_blind_review, build_blind_review_file

    client, _, qpath = api
    _seed_queue(client, ("발화 하나", _intent(0)), ("발화 둘", _intent(1)), ("발화 셋", _intent(0)))
    before = qpath.read_text(encoding="utf-8")

    blind = build_blind_review_file(qpath)
    blind["reviewer_ref"] = "TR_second"
    labels = {row["teacher_prompt"]: row for row in blind["labels"]}
    labels["발화 하나"]["chosen_intent"] = _intent(0)   # 일치
    labels["발화 둘"]["chosen_intent"] = _intent(1)     # 일치
    labels["발화 셋"]["chosen_intent"] = _intent(2)     # 불일치 → kappa 하락

    with pytest.raises(BlindBatchRejected):  # 배치 kappa < 0.65 → 아무것도 확정 안 함
        apply_blind_review(blind, CFG, queue_path=qpath, write=True)
    assert qpath.read_text(encoding="utf-8") == before  # 파일 불변


def test_blind_same_reviewer_alias_rejected(api) -> None:
    from app.gym.live import BlindReviewerInvalid, apply_blind_review, build_blind_review_file

    client, _, qpath = api
    _seed_queue(client, ("발화 하나", _intent(0)), ("발화 둘", _intent(1)))
    blind = build_blind_review_file(qpath)
    blind["reviewer_ref"] = " tr_live "  # 1차(TR_LIVE)의 별칭 — 자기 확인 위장
    for row in blind["labels"]:
        row["chosen_intent"] = _intent(0)

    with pytest.raises(BlindReviewerInvalid):
        apply_blind_review(blind, CFG, queue_path=qpath)
