"""config/experiments.yaml 단일 접근점 (§0-3 원칙 7, CLAUDE.md 절대 규칙 1).

모든 숫자 임계값은 config/experiments.yaml에만 존재한다.
코드 어디서든 `get_config().<section>.<key>`로만 읽는다.

- 필수 키 누락 / 타입 불일치 / 알 수 없는 키 → 로드 시점에 ValidationError
- 정의되지 않은 키 접근 → AttributeError
- 로드 후 불변(frozen)
"""
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

_REPO_ROOT = Path(__file__).resolve().parents[3]
DEFAULT_CONFIG_PATH = _REPO_ROOT / "config" / "experiments.yaml"


class _Section(BaseModel):
    # strict: yaml 오타(true→1, "0.92"→0.92 등)의 조용한 타입 강제 변환 차단
    model_config = ConfigDict(extra="forbid", frozen=True, strict=True)


class FoundryConfig(_Section):
    dedup_similarity: float
    paraphrase_max: float
    scenario_variants: int
    extract_min: float
    consensus_min: float
    judge_reject_max: float
    pilot_kappa_min: float
    consensus_disagreement_margin: float


class BrainConfig(_Section):
    retrieval_top_k: int
    exemplar_min_dist: float
    persona_prior_cap: float
    persona_warmup: int


class DecisionConfig(_Section):
    clarify_margin: float
    clarify_confidence: float
    abstain_score: float
    execute_confidence: float
    execute_margin: float
    clarify_per_utterance_max: int
    clarify_per_session_max: int


class FastUpdateConfig(_Section):
    fast_min_samples: int
    fast_delta_cap: float
    weekly_decay: float


class GrowthConfig(_Section):
    confusion_trigger: float
    gold_low_threshold: int
    default_pack_items: int


class OntologyConfig(_Section):
    min_intents: int
    min_examples_per_side: int


class LLMConfig(_Section):
    max_retries: int = Field(ge=0)
    timeout_s: float = Field(ge=0)
    retry_backoff_s: float = Field(ge=0)


class LabelAggregatorConfig(_Section):
    min_label_functions: int
    aggregate_confidence_min: float
    conflict_max: float
    evidence_type_weights: str


class VersionGateConfig(_Section):
    min_new_gold: int
    promote_rule: str


class VisualSemanticsConfig(_Section):
    vocabulary_version: str
    ktib_extractor_pinned: bool


class ArenaConfig(_Section):
    schedule: str
    ood_score_threshold: float


class LatencyConfig(_Section):
    live_p50_ms: int
    live_p95_ms: int
    client_deadline_ms: int
    useful_response_rate_min: float


class ExperimentsConfig(_Section):
    foundry: FoundryConfig
    brain: BrainConfig
    decision: DecisionConfig
    fast_update: FastUpdateConfig
    growth: GrowthConfig
    ontology: OntologyConfig
    llm: LLMConfig
    label_aggregator: LabelAggregatorConfig
    version_gate: VersionGateConfig
    visual_semantics: VisualSemanticsConfig
    arena: ArenaConfig
    latency: LatencyConfig


def load_config(path: Path | None = None) -> ExperimentsConfig:
    """지정 경로(기본: config/experiments.yaml)에서 읽어 전체 검증 후 반환."""
    target = path or DEFAULT_CONFIG_PATH
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    return ExperimentsConfig.model_validate(data)


@lru_cache(maxsize=1)
def get_config() -> ExperimentsConfig:
    """전역 단일 접근점 — 프로세스당 1회 로드·검증 후 캐시."""
    return load_config()
