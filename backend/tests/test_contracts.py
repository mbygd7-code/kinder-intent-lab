"""T1.4 AC (§3-1·§3-2, runtime §3-0·§3-1).

- 문서 예시 JSON(episode·evidence·infer req/resp·pack)이 계약(pydantic)과
  JSON Schema를 모두 통과하고, 왕복(model_dump)이 원본과 일치한다
- is_multi_intent=false ∧ intent_plan≠null 거부
- Core/extension 분리(절대 규칙 5): live/shadow 모드에 gym_extension 금지
- visual_semantics 통제 어휘 밖 값 거부 (additionalProperties=false 포함)
"""
import json
import subprocess
import sys
from pathlib import Path

import pytest
from pydantic import ValidationError

from app.contracts import (
    BrainNode,
    ChallengePack,
    ConfusionEdge,
    Evidence,
    InferRequest,
    InferResponse,
    IntentEpisode,
    ObservatoryBrain,
    VisualSemantics,
)

ROOT = Path(__file__).resolve().parents[2]
EXAMPLES = ROOT / "examples"
SCHEMAS = ROOT / "schemas"

MODEL_BY_SCHEMA = {
    "brain_node": BrainNode,
    "challenge_pack": ChallengePack,
    "confusion_edge": ConfusionEdge,
    "episode": IntentEpisode,
    "evidence": Evidence,
    "infer_request": InferRequest,
    "infer_response": InferResponse,
    "observatory_brain": ObservatoryBrain,
    "visual_semantics": VisualSemantics,
}

EXAMPLE_FILES = sorted(EXAMPLES.glob("*.json"))


def _load(filename_stem: str) -> dict:
    return json.loads((EXAMPLES / f"{filename_stem}.json").read_text(encoding="utf-8"))


# --- AC 1: 문서 예시 왕복 (변형 예시 포함 전부) ---


@pytest.mark.parametrize("path", EXAMPLE_FILES, ids=lambda p: p.name)
def test_example_round_trip(path: Path) -> None:
    """예시 → pydantic → dump가 원본과 동일 (계약이 스키마의 충실한 파생임을 고정)."""
    model_cls = MODEL_BY_SCHEMA[path.name.split(".")[0]]
    data = json.loads(path.read_text(encoding="utf-8"))
    dumped = model_cls.model_validate(data).model_dump(mode="json", exclude_unset=True)
    assert dumped == data


def test_every_schema_has_model_and_example() -> None:
    """스키마 8종 전부에 계약 모델과 예시가 존재한다 (커버리지 봉인)."""
    schema_names = {p.stem.removesuffix(".schema") for p in SCHEMAS.glob("*.schema.json")}
    example_names = {p.name.split(".")[0] for p in EXAMPLE_FILES}
    assert schema_names == set(MODEL_BY_SCHEMA)
    assert schema_names <= example_names


def test_validate_schemas_script_passes() -> None:
    """스키마 메타 검증 + examples/ 전체가 jsonschema($ref 포함)를 통과 + risk model 정합."""
    result = subprocess.run(
        [sys.executable, str(ROOT / "scripts" / "validate_schemas.py")],
        capture_output=True,
        # 스크립트는 stdout/stderr을 utf-8로 재설정한다. 여기서 안 맞추면 cp949 콘솔에서
        # 리더 스레드가 UnicodeDecodeError로 죽어 실패 메시지를 못 읽는다.
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    assert result.returncode == 0, result.stdout + result.stderr


# --- AC 2: is_multi_intent=false ∧ intent_plan≠null 거부 ---


def test_multi_intent_false_with_plan_rejected() -> None:
    data = _load("infer_response")
    assert data["is_multi_intent"] is False
    data["intent_plan"] = {"intents": ["play_expand", "doc_record"], "relation": "sequential"}
    with pytest.raises(ValidationError, match="intent_plan"):
        InferResponse.model_validate(data)


def test_multi_intent_true_without_plan_rejected() -> None:
    data = _load("infer_response")
    data["is_multi_intent"] = True
    data["intent_plan"] = None
    with pytest.raises(ValidationError, match="intent_plan"):
        InferResponse.model_validate(data)


def test_multi_intent_true_with_plan_accepted() -> None:
    data = _load("infer_response")
    data["is_multi_intent"] = True
    data["intent_plan"] = {
        "intents": ["play_expand", "doc_record"],
        "relation": "sequential",
        "execution_order": ["play_expand", "doc_record"],
    }
    InferResponse.model_validate(data)


# --- Core/extension 분리 (절대 규칙 5, runtime §3-0) ---


def test_live_mode_with_gym_extension_rejected() -> None:
    data = _load("infer_request")
    data["mode"] = "live"  # gym_extension이 남아 있는 상태
    with pytest.raises(ValidationError, match="gym_extension"):
        InferRequest.model_validate(data)


def test_shadow_mode_with_gym_extension_rejected() -> None:
    data = _load("infer_request")
    data["mode"] = "shadow"
    with pytest.raises(ValidationError, match="gym_extension"):
        InferRequest.model_validate(data)


def test_gym_mode_with_gym_extension_accepted() -> None:
    data = _load("infer_request")
    assert data["mode"] == "gym"
    InferRequest.model_validate(data)


def test_gym_extension_explicit_null_rejected() -> None:
    """스키마상 gym_extension은 null 불가(type: object) — 명시적 null도 거부."""
    data = _load("infer_request")
    data["gym_extension"] = None
    with pytest.raises(ValidationError, match="null 불가"):
        InferRequest.model_validate(data)


# --- strict 타입 규율 (스키마의 type 판정과 일치) ---


def test_strict_rejects_string_coercion() -> None:
    data = _load("episode")
    data["created_at"] = "1783850000"
    with pytest.raises(ValidationError):
        IntentEpisode.model_validate(data)


def test_strict_rejects_numeric_string_confidence() -> None:
    data = _load("infer_response")
    data["confidence"] = "0.57"
    with pytest.raises(ValidationError):
        InferResponse.model_validate(data)


def test_explicit_null_on_non_nullable_optional_rejected() -> None:
    data = _load("episode")
    data["dedup_hash"] = None  # 스키마: type string (nullable 아님)
    with pytest.raises(ValidationError, match="null 불가"):
        IntentEpisode.model_validate(data)


def test_nullable_fields_still_accept_null() -> None:
    """스키마가 nullable로 선언한 필드(scenario_id 등)는 null 허용 유지."""
    data = _load("episode")
    data["scenario_id"] = None
    data["consensus"] = None
    IntentEpisode.model_validate(data)


def test_clarification_requires_exactly_two_options() -> None:
    data = _load("infer_response.clarify")
    data["clarification"]["options"] = data["clarification"]["options"][:1]
    with pytest.raises(ValidationError):
        InferResponse.model_validate(data)


def test_schema_allowed_extra_fields_survive_round_trip() -> None:
    """additionalProperties(기본 true)에 따라 확장 필드는 수용·보존된다."""
    data = _load("evidence")
    data["pipeline_run_id"] = "RUN_001"
    dumped = Evidence.model_validate(data).model_dump(mode="json", exclude_unset=True)
    assert dumped["pipeline_run_id"] == "RUN_001"


# --- 절대 규칙 2 (계약 레벨 미러) ---


def test_benchmark_holdout_synthetic_rejected_at_contract() -> None:
    data = _load("episode")
    data.update(
        dataset_split="BENCHMARK_HOLDOUT",
        reliability_tier="GOLD",
        label_state="LABELED",
    )
    assert data["origin_channel"] == "FOUNDRY_SYNTHETIC"
    with pytest.raises(ValidationError, match="benchmark_integrity"):
        IntentEpisode.model_validate(data)


# --- visual_semantics 통제 어휘 (vs-1.0) ---


def _vs() -> dict:
    return _load("infer_request")["workspace_context"]["objects"][0]["visual_semantics"]


def test_visual_semantics_valid_example() -> None:
    VisualSemantics.model_validate(_vs())


def test_visual_semantics_rejects_unknown_field() -> None:
    data = _vs()
    data["free_text_description"] = "아이들이 나뭇잎을 관찰"
    with pytest.raises(ValidationError):
        VisualSemantics.model_validate(data)


def test_visual_semantics_rejects_out_of_vocabulary() -> None:
    data = _vs()
    data["materials"] = ["MAGIC_WAND"]
    with pytest.raises(ValidationError):
        VisualSemantics.model_validate(data)


def test_visual_semantics_requires_identity_removed_true() -> None:
    data = _vs()
    data["identity_removed"] = False
    with pytest.raises(ValidationError):
        VisualSemantics.model_validate(data)


def test_visual_semantics_rejects_int_one_for_identity_removed() -> None:
    """스키마 const true는 1을 거부한다 — Literal[True]의 1==True 코어션 차단 확인."""
    data = _vs()
    data["identity_removed"] = 1
    with pytest.raises(ValidationError):
        VisualSemantics.model_validate(data)


# --- 나머지 계약 스모크 (brain_node·confusion_edge) ---


def test_brain_node_minimal() -> None:
    BrainNode.model_validate(
        {
            "node_id": "N_visual_naturalize",
            "intent_id": "visual_naturalize",
            "region": "VISUAL",
            "definition_ref": "onto-1.0#visual_naturalize",
        }
    )


def test_confusion_edge_minimal() -> None:
    ConfusionEdge.model_validate(
        {
            "edge_id": "CE_0331",
            "from_true": "visual_naturalize",
            "to_predicted": "text_naturalize",
            "state": "hypothesized",
            "origin": "SKEPTIC",
        }
    )


def test_confusion_edge_rejects_bad_state() -> None:
    with pytest.raises(ValidationError):
        ConfusionEdge.model_validate(
            {
                "edge_id": "CE_0332",
                "from_true": "a",
                "to_predicted": "b",
                "state": "guessed",
            }
        )
