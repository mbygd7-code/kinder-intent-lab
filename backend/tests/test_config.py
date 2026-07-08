"""T1.2 AC: config 로더 (§0-3 원칙 7, CLAUDE.md 절대 규칙 1).

- 필수 키 전부 존재 · 타입 검증
- 없는 키 접근 시 명시적 에러
- 임계값 리터럴을 테스트에도 두지 않는다 — 값 비교 대신 존재·타입만 검증.
"""
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from app.core.config import ExperimentsConfig, get_config, load_config

ROOT = Path(__file__).resolve().parents[2]
CONFIG_PATH = ROOT / "config" / "experiments.yaml"


def _raw() -> dict:
    return yaml.safe_load(CONFIG_PATH.read_text(encoding="utf-8"))


def test_real_config_loads() -> None:
    cfg = load_config(CONFIG_PATH)
    assert isinstance(cfg, ExperimentsConfig)


def test_all_sections_and_keys_covered() -> None:
    """yaml의 모든 섹션·키가 모델에 있고, 모델의 모든 필드가 yaml에 있다 (양방향)."""
    raw = _raw()
    cfg = load_config(CONFIG_PATH)
    assert set(raw.keys()) == set(type(cfg).model_fields.keys())
    for section, keys in raw.items():
        model = getattr(cfg, section)
        assert set(keys.keys()) == set(type(model).model_fields.keys()), section


def test_field_types_are_validated() -> None:
    cfg = load_config(CONFIG_PATH)
    assert isinstance(cfg.foundry.dedup_similarity, float)
    assert isinstance(cfg.foundry.scenario_variants, int)
    assert isinstance(cfg.brain.retrieval_top_k, int)
    assert isinstance(cfg.decision.clarify_margin, float)
    assert isinstance(cfg.fast_update.weekly_decay, float)
    assert isinstance(cfg.growth.gold_low_threshold, int)
    assert isinstance(cfg.label_aggregator.min_label_functions, int)
    assert isinstance(cfg.label_aggregator.evidence_type_weights, str)
    assert isinstance(cfg.version_gate.promote_rule, str)
    assert isinstance(cfg.visual_semantics.ktib_extractor_pinned, bool)
    assert isinstance(cfg.arena.ood_score_threshold, float)
    assert isinstance(cfg.latency.client_deadline_ms, int)


def test_missing_required_key_fails() -> None:
    raw = _raw()
    del raw["foundry"]["dedup_similarity"]
    with pytest.raises(ValidationError, match="dedup_similarity"):
        ExperimentsConfig.model_validate(raw)


def test_missing_section_fails() -> None:
    raw = _raw()
    del raw["label_aggregator"]
    with pytest.raises(ValidationError, match="label_aggregator"):
        ExperimentsConfig.model_validate(raw)


def test_wrong_type_fails() -> None:
    raw = _raw()
    raw["foundry"]["dedup_similarity"] = "very high"
    with pytest.raises(ValidationError):
        ExperimentsConfig.model_validate(raw)


def test_unknown_key_rejected() -> None:
    """오타로 생긴 키가 조용히 무시되지 않는다 (extra=forbid)."""
    raw = _raw()
    raw["foundry"]["dedup_similarty"] = 0.5
    with pytest.raises(ValidationError):
        ExperimentsConfig.model_validate(raw)


def test_all_fields_are_required() -> None:
    """모든 필드 required — 코드 내 기본값(=임계값 리터럴) 유입 봉인 (절대 규칙 1)."""
    for section, field in ExperimentsConfig.model_fields.items():
        assert field.is_required(), section
        for name, sub in field.annotation.model_fields.items():
            assert sub.is_required(), f"{section}.{name}"


def test_type_coercion_rejected() -> None:
    """strict 모드 — 조용한 타입 강제 변환 금지 (bool→int, str→float, int→bool)."""
    for section, key, bad in [
        ("brain", "retrieval_top_k", True),
        ("foundry", "dedup_similarity", "0.92"),
        ("visual_semantics", "ktib_extractor_pinned", 1),
    ]:
        raw = _raw()
        raw[section][key] = bad
        with pytest.raises(ValidationError):
            ExperimentsConfig.model_validate(raw)


def test_undefined_attribute_access_raises() -> None:
    """AC: 없는 키 접근 시 명시적 에러."""
    cfg = load_config(CONFIG_PATH)
    with pytest.raises(AttributeError):
        _ = cfg.foundry.not_a_real_key


def test_config_is_immutable() -> None:
    cfg = load_config(CONFIG_PATH)
    with pytest.raises(ValidationError):
        cfg.foundry.dedup_similarity = 0.5  # type: ignore[misc]


def test_get_config_is_singleton() -> None:
    """전역 단일 접근점 — 프로세스당 1회 로드."""
    assert get_config() is get_config()
