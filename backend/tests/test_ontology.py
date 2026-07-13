"""T1.5 AC (§5-8·§5-9): 중복 intent_id·미정의 domain·예시 누락 검출 · UNKNOWN 포함."""
import copy
import re

import pytest
from pydantic import ValidationError

from app.core.config import get_config
from app.core.ontology import (
    CANONICAL_DOMAINS,
    Ontology,
    load_ontology,
    register_ontology,
    validate_seed_quality,
)

CANON_INTENTS = {
    "play_expand", "play_transition_next_step", "play_flow_naturalize",
    "text_naturalize", "write_activity_followup",
    "visual_naturalize", "visual_layout_refine",
}


def _mini() -> dict:
    """구조 검증용 최소 유효 온톨로지."""
    return {
        "version": "onto-test",
        "change_type": "major",
        "domains": list(CANONICAL_DOMAINS),
        "intents": [
            {
                "intent_id": "play_expand",
                "domain": "PLAY",
                "definition": "진행 중인 놀이를 확장한다",
                "positive_examples": ["더 해볼까?", "이거 더 크게 해보자"],
                "negative_examples": ["이제 정리하자", "사진 찍어줘"],
                "confusable_with": ["UNKNOWN"],
            },
            {
                "intent_id": "UNKNOWN",
                "domain": None,
                "definition": "정의된 어떤 intent로도 분류할 수 없다",
                "positive_examples": ["음...", "이거"],
                "negative_examples": ["사진 보정해줘", "알림장 써줘"],
            },
        ],
    }


# --- 구조 검증 (AC) ---


def test_mini_ontology_valid() -> None:
    Ontology.model_validate(_mini())


def test_duplicate_intent_id_detected() -> None:
    data = _mini()
    data["intents"].append(copy.deepcopy(data["intents"][0]))
    with pytest.raises(ValidationError, match="중복"):
        Ontology.model_validate(data)


def test_undefined_domain_detected() -> None:
    data = _mini()
    data["intents"][0]["domain"] = "MAGIC"
    with pytest.raises(ValidationError, match="미정의 domain"):
        Ontology.model_validate(data)


def test_missing_examples_detected() -> None:
    data = _mini()
    data["intents"][0]["positive_examples"] = []
    with pytest.raises(ValidationError):
        Ontology.model_validate(data)


def test_unknown_intent_required() -> None:
    data = _mini()
    data["intents"] = [i for i in data["intents"] if i["intent_id"] != "UNKNOWN"]
    with pytest.raises(ValidationError, match="UNKNOWN"):
        Ontology.model_validate(data)


def test_unknown_must_not_have_domain() -> None:
    data = _mini()
    data["intents"][1]["domain"] = "PLAY"
    with pytest.raises(ValidationError, match="UNKNOWN"):
        Ontology.model_validate(data)


def test_confusable_ref_must_exist() -> None:
    data = _mini()
    data["intents"][0]["confusable_with"] = ["ghost_intent"]
    with pytest.raises(ValidationError, match="혼동 참조"):
        Ontology.model_validate(data)


def test_confusable_self_ref_rejected() -> None:
    data = _mini()
    data["intents"][0]["confusable_with"] = ["play_expand"]
    with pytest.raises(ValidationError, match="자기 참조"):
        Ontology.model_validate(data)


def test_domains_must_be_canonical_seven() -> None:
    data = _mini()
    data["domains"] = ["PLAY", "OBSERVATION"]
    with pytest.raises(ValidationError, match="7개"):
        Ontology.model_validate(data)


# --- 시드 품질 (config 임계값) ---


def test_quality_rejects_too_few_intents() -> None:
    onto = Ontology.model_validate(_mini())
    with pytest.raises(ValueError, match="min_intents"):
        validate_seed_quality(onto)


# --- 실제 시드 (seeds/ontology_v1.yaml) ---


def test_seed_loads_and_meets_quality() -> None:
    onto = load_ontology()
    # 예시 시트 반영(apply_ontology_examples)이 minor를 올리므로 리터럴 고정 대신 형식 검사
    assert re.fullmatch(r"onto-\d+\.\d+", onto.version), onto.version
    validate_seed_quality(onto)  # ≥ min_intents, 7 도메인 커버, 예시 수
    ids = {i.intent_id for i in onto.intents}
    assert "UNKNOWN" in ids
    assert CANON_INTENTS <= ids, CANON_INTENTS - ids


def test_seed_covers_all_domains_with_config_minimum() -> None:
    onto = load_ontology()
    cfg = get_config().ontology
    real = [i for i in onto.intents if i.intent_id != "UNKNOWN"]
    assert len(real) >= cfg.min_intents
    assert {i.domain for i in real} == set(CANONICAL_DOMAINS)


def test_seed_contains_canonical_confusion_pair() -> None:
    """정본 혼동쌍 (§5-6): visual_naturalize ↔ text_naturalize."""
    onto = load_ontology()
    by_id = {i.intent_id: i for i in onto.intents}
    assert (
        "text_naturalize" in by_id["visual_naturalize"].confusable_with
        or "visual_naturalize" in by_id["text_naturalize"].confusable_with
    )


# --- ontology_versions 기록 ---


def test_register_ontology_records_version(db_session) -> None:
    onto = Ontology.model_validate(_mini())
    row = register_ontology(db_session, onto)
    assert row.version == "onto-test"
    assert row.change_type == "major"
    again = register_ontology(db_session, onto)  # 멱등
    assert again.version == row.version
