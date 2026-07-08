"""T1.7 AC (§1-S1·S2, 절대 규칙 7).

- governance 미판정(PENDING) 소스는 S3+에서 읽기 불가 (파이프라인 레벨 차단)
- TRANSFORM_ONLY 소스의 원문 저장 시도 차단 (앱 가드 + DB 트리거 백스톱)
- DENY 소스 drop 카운터
"""
import pytest
from pydantic import ValidationError
from sqlalchemy import insert
from sqlalchemy.exc import IntegrityError

from app.foundry.stages.s1_discovery import (
    SourceCandidate,
    get_source,
    list_sources,
    register_source,
)
from app.foundry.stages.s2_governance import (
    RawStorageForbidden,
    SourceNotFound,
    SourceNotReadable,
    assert_readable,
    dropped_source_count,
    govern_source,
    readable_sources,
    store_raw_document,
)
from app.models.foundry import SourceDocument


def _candidate(**kw) -> SourceCandidate:
    base = dict(
        source_class="TEACHER_LANGUAGE",
        title="교사 커뮤니티 놀이지도 질문 게시판",
        access="public_web",
        format="forum_posts",
        est_volume="12000 posts",
        discovery_reason="놀이 개입 시점 고민 표현의 밀도가 높음",
    )
    base.update(kw)
    return SourceCandidate(**base)


def _registered(db_session, **kw):
    src = register_source(db_session, _candidate(**kw))
    db_session.flush()
    return src


# --- S1 discovery / CRUD ---


def test_register_source_starts_pending(db_session) -> None:
    src = _registered(db_session)
    assert src.source_id.startswith("SRC_")
    assert src.governance_status == "PENDING"
    assert src.discovery_reason
    assert get_source(db_session, src.source_id).source_id == src.source_id


def test_discovery_reason_required() -> None:
    with pytest.raises(ValidationError):
        _candidate(discovery_reason="")


def test_invalid_source_class_rejected() -> None:
    with pytest.raises(ValidationError):
        _candidate(source_class="RANDOM_BLOG")


def test_list_sources_by_status(db_session) -> None:
    a = _registered(db_session)
    b = _registered(db_session)
    govern_source(db_session, b.source_id, "ALLOW", reviewed_by="rev-1")
    db_session.flush()
    pending = {s.source_id for s in list_sources(db_session, status="PENDING")}
    assert a.source_id in pending and b.source_id not in pending


# --- AC 1: PENDING/DENY 하류 읽기 불가 ---


def test_pending_source_not_readable(db_session) -> None:
    src = _registered(db_session)
    with pytest.raises(SourceNotReadable):
        assert_readable(src)
    assert src.source_id not in {s.source_id for s in readable_sources(db_session)}


def test_allow_and_transform_only_readable(db_session) -> None:
    allow = _registered(db_session)
    transform = _registered(db_session)
    govern_source(db_session, allow.source_id, "ALLOW", reviewed_by="rev-1")
    govern_source(db_session, transform.source_id, "TRANSFORM_ONLY", reviewed_by="rev-1")
    db_session.flush()
    readable = {s.source_id for s in readable_sources(db_session)}
    assert {allow.source_id, transform.source_id} <= readable
    assert_readable(get_source(db_session, allow.source_id))
    assert_readable(get_source(db_session, transform.source_id))


def test_deny_source_not_readable(db_session) -> None:
    src = _registered(db_session)
    govern_source(db_session, src.source_id, "DENY", reviewed_by="rev-1")
    db_session.flush()
    with pytest.raises(SourceNotReadable):
        assert_readable(get_source(db_session, src.source_id))
    assert src.source_id not in {s.source_id for s in readable_sources(db_session)}


# --- AC 3: DENY drop 카운터 ---


def test_dropped_source_count(db_session) -> None:
    before = dropped_source_count(db_session)
    for _ in range(3):
        s = _registered(db_session)
        govern_source(db_session, s.source_id, "DENY", reviewed_by="rev-1")
    db_session.flush()
    assert dropped_source_count(db_session) == before + 3


# --- AC 2: TRANSFORM_ONLY 원문 저장 차단 (절대 규칙 7) ---


def test_store_raw_blocked_for_transform_only(db_session) -> None:
    src = _registered(db_session)
    govern_source(db_session, src.source_id, "TRANSFORM_ONLY", reviewed_by="rev-1")
    db_session.flush()
    with pytest.raises(RawStorageForbidden, match="TRANSFORM_ONLY"):
        store_raw_document(db_session, src.source_id, "원문 전체 텍스트")


def test_store_raw_blocked_for_pending(db_session) -> None:
    src = _registered(db_session)
    with pytest.raises(RawStorageForbidden):
        store_raw_document(db_session, src.source_id, "원문")


def test_store_raw_blocked_for_deny(db_session) -> None:
    src = _registered(db_session)
    govern_source(db_session, src.source_id, "DENY", reviewed_by="rev-1")
    db_session.flush()
    with pytest.raises(RawStorageForbidden):
        store_raw_document(db_session, src.source_id, "원문")


def test_store_raw_allowed_for_allow(db_session) -> None:
    src = _registered(db_session)
    govern_source(db_session, src.source_id, "ALLOW", reviewed_by="rev-1")
    db_session.flush()
    doc = store_raw_document(db_session, src.source_id, "라이선스 확인된 원문")
    db_session.flush()
    assert doc.content == "라이선스 확인된 원문"
    assert doc.source_id == src.source_id


def test_db_trigger_blocks_raw_bypass(db_session) -> None:
    """앱 가드를 우회한 직접 INSERT도 DB 트리거가 차단 (절대 규칙 7 물리 백스톱)."""
    src = _registered(db_session)
    govern_source(db_session, src.source_id, "TRANSFORM_ONLY", reviewed_by="rev-1")
    db_session.flush()
    with pytest.raises(IntegrityError):
        with db_session.begin_nested():
            db_session.execute(
                insert(SourceDocument).values(
                    doc_id="DOC_BYPASS", source_id=src.source_id, content="원문 우회 시도"
                )
            )


def test_store_raw_unknown_source_raises(db_session) -> None:
    with pytest.raises(SourceNotFound):
        store_raw_document(db_session, "SRC_NOPE", "원문")


# --- 재판정 시 원문 purge (절대 규칙 7: 비ALLOW 소스는 원문을 가질 수 없다) ---


def _raw_doc_count(db_session, source_id: str) -> int:
    return (
        db_session.query(SourceDocument)
        .filter(SourceDocument.source_id == source_id)
        .count()
    )


def test_downgrade_purges_raw_documents(db_session) -> None:
    src = _registered(db_session)
    govern_source(db_session, src.source_id, "ALLOW", reviewed_by="rev-1")
    db_session.flush()
    store_raw_document(db_session, src.source_id, "라이선스 원문 전체")
    db_session.flush()
    assert _raw_doc_count(db_session, src.source_id) == 1

    govern_source(db_session, src.source_id, "TRANSFORM_ONLY", reviewed_by="rev-2")
    db_session.flush()
    assert _raw_doc_count(db_session, src.source_id) == 0
    assert src.source_id in {s.source_id for s in readable_sources(db_session)}


def test_downgrade_records_purge_count_in_event(db_session) -> None:
    from app.models.governance import GovernanceEvent

    src = _registered(db_session)
    govern_source(db_session, src.source_id, "ALLOW", reviewed_by="rev-1")
    db_session.flush()
    store_raw_document(db_session, src.source_id, "원문")
    db_session.flush()
    govern_source(db_session, src.source_id, "DENY", reviewed_by="rev-2")
    db_session.flush()
    events = (
        db_session.query(GovernanceEvent)
        .filter(GovernanceEvent.event_type == "SOURCE_DECISION")
        .all()
    )
    assert any(e.payload.get("purged_raw_documents") == 1 for e in events)


def test_db_trigger_purges_raw_on_direct_downgrade(db_session) -> None:
    """앱 가드를 우회한 직접 SQL 상태 변경도 DB 트리거가 원문을 purge (규칙 7 백스톱)."""
    from sqlalchemy import text

    src = _registered(db_session)
    govern_source(db_session, src.source_id, "ALLOW", reviewed_by="rev-1")
    db_session.flush()
    store_raw_document(db_session, src.source_id, "원문")
    db_session.flush()

    db_session.execute(
        text("UPDATE sources SET governance_status = 'DENY' WHERE source_id = :sid"),
        {"sid": src.source_id},
    )
    db_session.expire_all()  # 트리거가 지운 행을 다시 조회
    assert _raw_doc_count(db_session, src.source_id) == 0


# --- governance 이벤트 ---


def test_govern_unknown_source_raises(db_session) -> None:
    with pytest.raises(SourceNotFound):
        govern_source(db_session, "SRC_NOPE", "ALLOW", reviewed_by="rev-1")


def test_govern_records_governance_event(db_session) -> None:
    from app.models.governance import GovernanceEvent

    src = _registered(db_session)
    govern_source(db_session, src.source_id, "ALLOW", reviewed_by="rev-7", rules=["license_ok"])
    db_session.flush()
    events = (
        db_session.query(GovernanceEvent)
        .filter(GovernanceEvent.event_type == "SOURCE_DECISION")
        .all()
    )
    assert any(
        e.payload.get("source_id") == src.source_id and e.payload.get("decision") == "ALLOW"
        for e in events
    )
    assert any(e.approved_by == "rev-7" for e in events)
