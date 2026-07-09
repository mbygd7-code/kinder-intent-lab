"""T3.3 AC: POST /v1/intent/infer (mode=gym) — 라우터 + decision 정책.

- 훈련 메타데이터가 Core 경계를 넘으면(=live/shadow에 gym_extension) 400 (절대 규칙 5)
- margin < decision.clarify_margin → decision=clarify (top-2 옵션)
- 약한 top(top_activation < abstain_score) → decision=abstain(LOW_CONFIDENCE)
- 단일 확신 후보 → decision=suggest
- 응답이 infer_response.schema.json 왕복 통과
- live/shadow 서빙은 PARTIAL HOLD → 501 (계약은 통과해도 서빙 안 함)
- gym_extension은 gym 모드에서 합법(훈련 메타 적재)이며 그래도 200
"""
import json
from pathlib import Path

import jsonschema
import pytest
from brain_helpers import CFG, FAST, _embed, _payload, _real_intents, _seed, _SyntheticScorer
from fastapi.testclient import TestClient

from app.api.infer import get_experiments, get_infer_client, get_infer_embed
from app.core.db import get_session
from app.llm.client import LLMClient
from app.main import app

REPO_ROOT = Path(__file__).resolve().parents[2]
INFER_RESPONSE_SCHEMA = json.loads(
    (REPO_ROOT / "schemas" / "infer_response.schema.json").read_text(encoding="utf-8")
)


@pytest.fixture()
def api(db_session):
    """합성 scorer/임베딩 + savepoint 세션을 주입(실 LLM/네트워크 없음). (client, session) 반환."""
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_infer_client] = lambda: LLMClient(_SyntheticScorer(), FAST)
    app.dependency_overrides[get_infer_embed] = lambda: _embed()
    app.dependency_overrides[get_experiments] = lambda: CFG
    with TestClient(app) as client:
        yield client, db_session
    app.dependency_overrides.clear()


def _use_scorer(scorer) -> None:
    app.dependency_overrides[get_infer_client] = lambda: LLMClient(scorer, FAST)


# --- AC 1: 훈련 메타데이터가 Core 경계를 넘으면 400 ---


def test_training_metadata_in_core_rejected_400(api) -> None:
    client, _ = api
    # live 모드에 gym_extension(훈련 메타) → 계약이 거부(절대 규칙 5) → 400
    payload = _payload("발화", mode="live", gym_extension={"scenario_id": "SECRET_SCENARIO"})
    r = client.post("/v1/intent/infer", json=payload)
    assert r.status_code == 400


def test_gym_extension_is_legal_in_gym_mode(api) -> None:
    client, db = api
    ints = _real_intents(1)
    _seed(db, _embed(), [(ints[0], "정상 발화")])
    payload = _payload("정상 발화", mode="gym",
                       gym_extension={"scenario_id": "SC1", "target_confusion": [["a", "b"]]})
    r = client.post("/v1/intent/infer", json=payload)
    assert r.status_code == 200  # gym에선 훈련 메타 적재 합법(Core엔 안 들어감 — T3.2에서 고정)


# --- AC 2: margin < clarify_margin → clarify ---


def test_low_margin_yields_clarify(api) -> None:
    client, db = api
    ints = _real_intents(2)
    _seed(db, _embed(), [(ints[0], "모호 A"), (ints[1], "모호 B")])  # 근접 두 후보
    r = client.post("/v1/intent/infer", json=_payload("모호 A"))
    assert r.status_code == 200
    body = r.json()
    assert body["margin"] < CFG.decision.clarify_margin
    assert body["decision"] == "clarify"
    assert len(body["clarification"]["options"]) == 2


def test_confident_single_candidate_suggests(api) -> None:
    client, db = api
    ints = _real_intents(1)
    _seed(db, _embed(), [(ints[0], "확신 발화")])  # 단독 후보 → 큰 margin
    r = client.post("/v1/intent/infer", json=_payload("확신 발화"))
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "suggest"
    assert body["top_intent"] == ints[0]
    jsonschema.validate(body, INFER_RESPONSE_SCHEMA)  # suggest 분기도 계약 왕복


def test_weak_top_abstains(api) -> None:
    client, db = api
    ints = _real_intents(1)
    _seed(db, _embed(), [(ints[0], "약한 발화")])
    _use_scorer(_SyntheticScorer(fixed=0.05))  # 정규화 confidence는 1.0이나 절대 강도는 약함
    r = client.post("/v1/intent/infer", json=_payload("약한 발화"))
    assert r.status_code == 200
    body = r.json()
    assert body["decision"] == "abstain"
    assert body["abstain_reason"] == "LOW_CONFIDENCE"
    jsonschema.validate(body, INFER_RESPONSE_SCHEMA)  # abstain 분기도 계약 왕복


# --- AC 3: 스키마 왕복 ---


def test_response_roundtrips_infer_response_schema(api) -> None:
    client, db = api
    ints = _real_intents(2)
    _seed(db, _embed(), [(ints[0], "왕복 A"), (ints[1], "왕복 B")])
    r = client.post("/v1/intent/infer", json=_payload("왕복 A"))
    assert r.status_code == 200
    jsonschema.validate(r.json(), INFER_RESPONSE_SCHEMA)  # draft-07 계약 왕복


# --- live rollout PARTIAL HOLD: 계약은 통과해도 서빙 안 함 ---


def test_shadow_mode_not_served_501(api) -> None:
    client, _ = api
    r = client.post("/v1/intent/infer", json=_payload("발화", mode="shadow"))
    assert r.status_code == 501  # live/shadow rollout HOLD (CLAUDE.md)
