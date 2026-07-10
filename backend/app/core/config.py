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
from pydantic import BaseModel, ConfigDict, Field, field_validator

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
    max_dedup_retries: int
    batch_size: int


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


class PriorityWeights(_Section):
    """§6-3 훈련 우선순위 순위 신호 가중치 (상대 비교용 — 합이 1일 필요는 없다)."""

    heldout_low: float          # ① heldout 정확도 최저 intent
    confusion_high: float       # ② confusion_rate 최고 edge
    performance_drop: float     # ③ 최근 성능 하락 intent
    evidence_low: float         # ④ evidence 최소 intent
    persona_impact: float       # ⑤ persona 영향 큰 intent
    service_importance: float   # ⑥ 서비스 중요도


class GrowthConfig(_Section):
    confusion_trigger: float
    gold_low_threshold: int
    default_pack_items: int
    coverage_order_items: int   # A형 Foundry 작업주문 1건이 요청하는 시나리오 수 (§6-1)
    priority_weights: PriorityWeights


class GymConfig(_Section):
    evidence_strength: float
    session_items: int


class DiagnosisConfig(_Section):
    ambiguous_competitors_low: float
    ambiguous_competitors_high: float
    screen_coverage_low: float
    screen_coverage_high: float
    persona_entropy_low: float
    persona_entropy_high: float
    gold_low: int
    gold_high: int


class OntologyConfig(_Section):
    min_intents: int
    min_examples_per_side: int


class LLMConfig(_Section):
    max_retries: int = Field(ge=0)
    timeout_s: float = Field(ge=0)
    retry_backoff_s: float = Field(ge=0)


class AtlasConfig(_Section):
    map_min_similarity: float


class PersonaConfig(_Section):
    cluster_min_size: int
    cluster_min_samples: int


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
    ece_bins: int = Field(gt=1)
    confusion_confirm_min: int = Field(ge=1)
    # promote 규칙(§6-6)의 'critical intent 악화 없음' 대상. 도메인 합의 전까지 빈 목록 =
    # 그 조건이 항상 통과 — 지어낸 목록으로 게이트를 위장하지 않는다.
    critical_intents: list[str]
    first_intent_accuracy_target: float = Field(gt=0, le=1)


class LatencyConfig(_Section):
    live_p50_ms: int
    live_p95_ms: int
    client_deadline_ms: int
    useful_response_rate_min: float


class CampaignConfig(_Section):
    window_batches: int
    consensus_drop_max: float
    reject_rise_max: float
    unit_cost_rise_ratio: float
    domain_weights: dict[str, float]

    @field_validator("domain_weights")
    @classmethod
    def _weights_normalized(cls, v: dict[str, float]) -> dict[str, float]:
        """배분 가중치는 (0,1] 범위이고 합=1이어야 한다 (구조 무결성 가드, 실험 임계값 아님).

        도메인 '이름' 정합(정본 7개 여부)은 config가 ontology에 의존하지 않도록
        campaign 모듈(prepare 단계)에서 loud-fail로 검증한다.
        """
        if not v:
            raise ValueError("domain_weights가 비어 있음")
        if any(not (0.0 < w <= 1.0) for w in v.values()):
            raise ValueError("domain_weights 값은 (0,1] 범위여야 함")
        total = sum(v.values())
        if abs(total - 1.0) > 1e-6:
            raise ValueError(f"domain_weights 합이 1이 아님: {total}")
        return v


class ExperimentsConfig(_Section):
    foundry: FoundryConfig
    brain: BrainConfig
    decision: DecisionConfig
    fast_update: FastUpdateConfig
    growth: GrowthConfig
    gym: GymConfig
    diagnosis: DiagnosisConfig
    ontology: OntologyConfig
    llm: LLMConfig
    atlas: AtlasConfig
    persona: PersonaConfig
    label_aggregator: LabelAggregatorConfig
    version_gate: VersionGateConfig
    visual_semantics: VisualSemanticsConfig
    arena: ArenaConfig
    latency: LatencyConfig
    campaign: CampaignConfig


def load_config(path: Path | None = None) -> ExperimentsConfig:
    """지정 경로(기본: config/experiments.yaml)에서 읽어 전체 검증 후 반환."""
    target = path or DEFAULT_CONFIG_PATH
    data = yaml.safe_load(target.read_text(encoding="utf-8"))
    return ExperimentsConfig.model_validate(data)


@lru_cache(maxsize=1)
def get_config() -> ExperimentsConfig:
    """전역 단일 접근점 — 프로세스당 1회 로드·검증 후 캐시."""
    return load_config()
