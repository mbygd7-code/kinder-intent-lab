"""화면 씨드 웹 관리 AC — /v1/situation-seeds (2026-07-17 사용자 요청).

"씨드를 프론트 화면에서 작성해 넣을 수 있게":
- 조회는 어휘(한글 라벨)·vs-1.0 어휘·씨드별 최소기준 판정을 함께 준다 (프론트 하드코딩 방지)
- 작성·수정·삭제는 PIN+작성자 필수(오클릭 방지), 전체 파일 재검증 후에만 원자 저장,
  governance_events에 감사 기록 — 우회 저장 경로 없음
- 삭제가 도메인 커버리지를 깨면 거부(증산 즉사 방지 — 로더와 같은 잣대)
- 확장 미리보기는 저장 없이 LLM 1회 — 최소기준 미달 씨드는 확장 불가 안내
"""
import shutil
import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select

from app.api.situation_seeds import get_expand_client, get_seed_path
from app.core.config import get_config
from app.core.db import get_session
from app.foundry.pilot import SyntheticFoundryProvider
from app.foundry.situation_seeds import DEFAULT_SITUATION_SEED_PATH, load_situation_seeds
from app.llm.client import LLMClient, LLMConfig
from app.main import app
from app.models.governance import GovernanceEvent

CFG = get_config()
PIN = "2341"


@pytest.fixture()
def seed_path(tmp_path):
    p = tmp_path / "situation_seeds_v1.yaml"
    shutil.copy(DEFAULT_SITUATION_SEED_PATH, p)
    return p


@pytest.fixture()
def api(db_session, seed_path):
    db_session.execute(delete(GovernanceEvent).where(
        GovernanceEvent.event_type == "SITUATION_SEED_EDIT"
    ))
    db_session.flush()
    app.dependency_overrides[get_session] = lambda: db_session
    app.dependency_overrides[get_seed_path] = lambda: seed_path
    app.dependency_overrides[get_expand_client] = lambda: LLMClient(
        SyntheticFoundryProvider(), LLMConfig(max_retries=0, timeout_s=5.0, retry_backoff_s=0.0)
    )
    with TestClient(app) as client:
        yield client, db_session, seed_path
    app.dependency_overrides.clear()


def _new_seed(seed_id=None):
    return {
        "seed_id": seed_id or ("web_seed_" + uuid.uuid4().hex[:6]),
        "domains": ["PLAY"],
        "workspace_state": {
            "surface_type": "photo_album",
            "objects_summary": {"photo": 3},
            "selection": {"type": "photo", "count": 1},
            "recent_actions": ["select_photo"],
            "visual_semantics": [{
                "object_ref": "photo_1",
                "schema_version": "vs-1.0",
                "extractor_version": "SYNTH_BUILDER_v1",
                "scene_type": ["INDOOR_CLASSROOM"],
                "activity_types": ["FREE_PLAY"],
                "observed_actions": ["OBSERVE"],
                "group_size_band": "SMALL_GROUP",
                "identity_removed": True,
            }],
        },
    }


def test_catalog_returns_vocab_labels_and_readiness(api) -> None:
    """★ 조회 하나로 폼을 그릴 수 있다 — 어휘(한글)·vs-1.0 어휘·씨드별 최소기준 판정."""
    client, _, _ = api
    body = client.get("/v1/situation-seeds").json()
    assert body["version"] and body["seeds"]
    assert body["vocabulary"]["surface_types"]["play_board"] == "놀이 보드 화면"
    assert "INDOOR_CLASSROOM" in body["vs_vocabulary"]["scene_type"]
    assert body["scenario_variants"] == CFG.foundry.scenario_variants  # config 에코
    for item in body["seeds"]:
        assert isinstance(item["ready"], bool) and isinstance(item["unmet"], list)
    assert all(item["ready"] for item in body["seeds"])  # 실파일 씨드는 전부 기준 충족


def test_create_requires_pin_and_editor(api) -> None:
    """PIN 불일치 401 · 작성자 공백 422 — 어느 쪽도 파일을 건드리지 않는다."""
    client, _, seed_path = api
    before = seed_path.read_text(encoding="utf-8")
    r1 = client.post("/v1/situation-seeds/seeds",
                     json={"pin": "0000", "editor": "명배영", "seed": _new_seed()})
    assert r1.status_code == 401
    r2 = client.post("/v1/situation-seeds/seeds",
                     json={"pin": PIN, "editor": "  ", "seed": _new_seed()})
    assert r2.status_code == 422
    assert seed_path.read_text(encoding="utf-8") == before


def test_create_persists_file_and_audit_event(api) -> None:
    """★ 작성 성공 = YAML 원천에 저장 + governance 감사 기록. 조회에 즉시 나타난다."""
    client, db, seed_path = api
    seed = _new_seed("web_seed_created")
    r = client.post("/v1/situation-seeds/seeds",
                    json={"pin": PIN, "editor": "명배영", "seed": seed})
    assert r.status_code == 200, r.text

    reloaded = load_situation_seeds(seed_path)  # 파일이 로더 계약 그대로 다시 열린다
    assert any(s.seed_id == "web_seed_created" for s in reloaded.seeds)
    ids = [i["seed_id"] for i in client.get("/v1/situation-seeds").json()["seeds"]]
    assert "web_seed_created" in ids

    ev = db.scalars(select(GovernanceEvent).where(
        GovernanceEvent.event_type == "SITUATION_SEED_EDIT"
    )).all()
    assert len(ev) == 1 and ev[0].approved_by == "명배영"
    assert ev[0].payload["action"] == "create" and ev[0].payload["seed_id"] == "web_seed_created"


def test_create_rejects_out_of_vocabulary_and_keeps_file(api) -> None:
    """어휘 밖 값은 422(한글 사유) — 파일은 1바이트도 안 바뀐다."""
    client, _, seed_path = api
    before = seed_path.read_text(encoding="utf-8")
    bad = _new_seed()
    bad["workspace_state"]["recent_actions"] = ["teleport"]
    r = client.post("/v1/situation-seeds/seeds",
                    json={"pin": PIN, "editor": "명배영", "seed": bad})
    assert r.status_code == 422 and "teleport" in r.json()["detail"]
    assert seed_path.read_text(encoding="utf-8") == before


def test_create_duplicate_id_conflict(api) -> None:
    client, _, _ = api
    existing = load_situation_seeds().seeds[0].seed_id
    r = client.post("/v1/situation-seeds/seeds",
                    json={"pin": PIN, "editor": "명배영", "seed": _new_seed(existing)})
    assert r.status_code == 409


def test_update_replaces_seed(api) -> None:
    client, _, seed_path = api
    target = load_situation_seeds().seeds[0]
    body = _new_seed(target.seed_id)
    r = client.put(f"/v1/situation-seeds/seeds/{target.seed_id}",
                   json={"pin": PIN, "editor": "조선생", "seed": body})
    assert r.status_code == 200, r.text
    reloaded = load_situation_seeds(seed_path)
    got = next(s for s in reloaded.seeds if s.seed_id == target.seed_id)
    assert got.workspace_state.surface_type == "photo_album"

    r404 = client.put("/v1/situation-seeds/seeds/no_such_seed",
                      json={"pin": PIN, "editor": "조선생", "seed": _new_seed("no_such_seed")})
    assert r404.status_code == 404


def test_delete_blocked_when_domain_coverage_breaks(api, seed_path) -> None:
    """★ 삭제로 어느 도메인이 비면 422 거부 — 증산이 배분에서 죽는 사고를 문에서 막는다."""
    client, _, _ = api
    # STUDIO 후보는 4개 — 3개를 지우면 마지막 하나는 삭제 거부돼야 한다
    studio = [s.seed_id for s in load_situation_seeds(seed_path).seeds if "STUDIO" in s.domains]
    for sid in studio[:-1]:
        ok = client.post(f"/v1/situation-seeds/seeds/{sid}/delete",
                         json={"pin": PIN, "editor": "명배영"})
        assert ok.status_code == 200, ok.text
    last = client.post(f"/v1/situation-seeds/seeds/{studio[-1]}/delete",
                       json={"pin": PIN, "editor": "명배영"})
    assert last.status_code == 422 and "STUDIO" in last.json()["detail"]
    assert any(s.seed_id == studio[-1] for s in load_situation_seeds(seed_path).seeds)


def test_expand_preview_returns_contract_variants(api) -> None:
    """★ 미리보기: 저장 없이 변형 k개 — 씨드 파일은 그대로, 변형은 어휘·계약 통과분만."""
    client, _, seed_path = api
    before = seed_path.read_text(encoding="utf-8")
    anchor = load_situation_seeds(seed_path).seeds[0].seed_id
    r = client.post("/v1/situation-seeds/expand-preview",
                    json={"pin": PIN, "seed_id": anchor})
    assert r.status_code == 200, r.text
    body = r.json()
    assert len(body["variants"]) == CFG.foundry.scenario_variants
    assert all(v["surface_type"] for v in body["variants"])
    assert seed_path.read_text(encoding="utf-8") == before  # 저장 없음

    r404 = client.post("/v1/situation-seeds/expand-preview",
                       json={"pin": PIN, "seed_id": "no_such"})
    assert r404.status_code == 404


# --- CSV 일괄 업로드 (bulk upsert — 전체 검증 통과 시에만 원자 반영) ---


def test_bulk_upsert_atomic_create_and_update(api) -> None:
    """★ 기존 id는 교체·새 id는 추가가 한 번에 — 파일 저장 1회, 감사 기록 1건(개수 포함)."""
    client, db, seed_path = api
    before_total = len(load_situation_seeds(seed_path).seeds)
    target = load_situation_seeds(seed_path).seeds[0].seed_id
    r = client.post("/v1/situation-seeds/seeds/bulk", json={
        "pin": PIN, "editor": "명배영",
        "seeds": [_new_seed(target), _new_seed("bulk_new_seed")],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["created"] == 1 and body["updated"] == 1
    assert body["total"] == before_total + 1

    reloaded = load_situation_seeds(seed_path)
    got = next(s for s in reloaded.seeds if s.seed_id == target)
    assert got.workspace_state.surface_type == "photo_album"  # 교체 반영
    assert any(s.seed_id == "bulk_new_seed" for s in reloaded.seeds)

    ev = db.scalars(select(GovernanceEvent).where(
        GovernanceEvent.event_type == "SITUATION_SEED_EDIT"
    )).all()
    assert len(ev) == 1 and ev[0].payload["action"] == "bulk_upsert"
    assert ev[0].payload["created"] == 1 and ev[0].payload["updated"] == 1


def test_bulk_bad_row_rejects_everything(api) -> None:
    """한 행이라도 계약 위반이면 전부 거부(부분 반영 금지) — 파일 무변경, 행 식별 포함."""
    client, _, seed_path = api
    before = seed_path.read_text(encoding="utf-8")
    bad = _new_seed("bulk_bad_row")
    bad["workspace_state"]["recent_actions"] = ["teleport"]
    r = client.post("/v1/situation-seeds/seeds/bulk", json={
        "pin": PIN, "editor": "명배영",
        "seeds": [_new_seed("bulk_ok_row"), bad],
    })
    assert r.status_code == 422
    detail = r.json()["detail"]
    assert "teleport" in detail and "bulk_bad_row" in detail
    assert seed_path.read_text(encoding="utf-8") == before


def test_bulk_duplicate_ids_in_payload_rejected(api) -> None:
    client, _, seed_path = api
    before = seed_path.read_text(encoding="utf-8")
    r = client.post("/v1/situation-seeds/seeds/bulk", json={
        "pin": PIN, "editor": "명배영",
        "seeds": [_new_seed("bulk_dup"), _new_seed("bulk_dup")],
    })
    assert r.status_code == 422 and "중복" in r.json()["detail"]
    assert seed_path.read_text(encoding="utf-8") == before


# --- 어휘 관리 (보고 있던 화면·행동·카드 목록을 킨더버스에 맞게 추가·수정) ---


def test_vocab_add_and_rename_updates_catalog_and_csv_source(api) -> None:
    """★ 새 화면 종류 추가·라벨 수정이 어휘 원천에 저장된다 — 폼·CSV·검수 라벨의 단일 원천."""
    client, db, seed_path = api
    r = client.post("/v1/situation-seeds/vocabulary", json={
        "pin": PIN, "editor": "명배영",
        "table": "surface_types", "vocab_id": "photo_editor", "label_ko": "사진 편집 화면",
    })
    assert r.status_code == 200 and r.json()["updated"] is False

    cat = client.get("/v1/situation-seeds").json()
    assert cat["vocabulary"]["surface_types"]["photo_editor"] == "사진 편집 화면"
    saved = load_situation_seeds(seed_path).vocabulary.surface_types
    assert saved["photo_editor"] == "사진 편집 화면"

    r2 = client.post("/v1/situation-seeds/vocabulary", json={
        "pin": PIN, "editor": "명배영",
        "table": "surface_types", "vocab_id": "photo_editor", "label_ko": "사진 꾸미기 화면",
    })
    assert r2.status_code == 200 and r2.json()["updated"] is True
    renamed = load_situation_seeds(seed_path).vocabulary.surface_types
    assert renamed["photo_editor"] == "사진 꾸미기 화면"

    ev = db.scalars(select(GovernanceEvent).where(
        GovernanceEvent.event_type == "SITUATION_SEED_EDIT"
    )).all()
    assert len(ev) == 2 and all(e.payload["action"] == "vocab_upsert" for e in ev)


def test_vocab_rejects_bad_table_id_or_blank_label(api) -> None:
    client, _, seed_path = api
    before = seed_path.read_text(encoding="utf-8")
    base = {"pin": PIN, "editor": "명배영", "label_ko": "라벨"}
    assert client.post("/v1/situation-seeds/vocabulary",
                       json={**base, "table": "nope", "vocab_id": "x"}).status_code == 422
    assert client.post("/v1/situation-seeds/vocabulary",
                       json={**base, "table": "actions", "vocab_id": "Bad Id!"}).status_code == 422
    assert client.post("/v1/situation-seeds/vocabulary",
                       json={"pin": PIN, "editor": "명배영", "table": "actions",
                             "vocab_id": "swipe", "label_ko": "  "}).status_code == 422
    assert seed_path.read_text(encoding="utf-8") == before


def test_vocab_delete_guarded_when_in_use(api) -> None:
    """★ 씨드가 쓰는 어휘는 삭제 거부(사유에 씨드 표시) — 안 쓰는 항목만 지워진다."""
    client, _, seed_path = api
    r = client.post("/v1/situation-seeds/vocabulary/delete", json={
        "pin": PIN, "editor": "명배영", "table": "surface_types", "vocab_id": "play_board",
    })
    assert r.status_code == 422 and "play_board" in r.json()["detail"]
    assert "play_board" in load_situation_seeds(seed_path).vocabulary.surface_types

    client.post("/v1/situation-seeds/vocabulary", json={
        "pin": PIN, "editor": "명배영",
        "table": "surface_types", "vocab_id": "unused_screen", "label_ko": "안 쓰는 화면",
    })
    r2 = client.post("/v1/situation-seeds/vocabulary/delete", json={
        "pin": PIN, "editor": "명배영", "table": "surface_types", "vocab_id": "unused_screen",
    })
    assert r2.status_code == 200
    assert "unused_screen" not in load_situation_seeds(seed_path).vocabulary.surface_types

    r404 = client.post("/v1/situation-seeds/vocabulary/delete", json={
        "pin": PIN, "editor": "명배영", "table": "surface_types", "vocab_id": "ghost",
    })
    assert r404.status_code == 404
