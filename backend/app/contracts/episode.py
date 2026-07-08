"""episode.schema.json 파생 (§3-2). benchmark_integrity 조건 포함 (절대 규칙 2)."""
from typing import Annotated, ClassVar, Literal

from pydantic import Field, field_validator, model_validator

from app.contracts.base import Contract

DatasetSplit = Literal["TRAIN", "VALIDATION", "TEST", "BENCHMARK_HOLDOUT"]
ReliabilityTier = Literal["UNVERIFIED", "BRONZE", "SILVER", "GOLD"]
LabelState = Literal[
    "UNLABELED", "EVIDENCE_ACCUMULATING", "AGGREGATION_READY",
    "LABEL_CANDIDATE", "REVIEW_REQUIRED", "LABELED", "REJECTED",
]
OriginChannel = Literal[
    "FOUNDRY_SYNTHETIC", "FOUNDRY_AUGMENTED", "GYM_HUMAN", "EXPERT_AUTHORED",
    "PRODUCTION_SHADOW", "OFFICIAL_CORPUS", "COMMUNITY_DERIVED",
]
EpisodeCreatorType = Literal[
    "FOUNDRY_PIPELINE", "GYM_SESSION", "SHADOW_CONVERTER", "HUMAN_ANNOTATOR"
]
PrimarySubjectType = Literal["TEACHER", "SIMULATED_TEACHER"]

SYNTHETIC_ORIGINS = ("FOUNDRY_SYNTHETIC", "FOUNDRY_AUGMENTED")


class HumanReview(Contract):
    reviewers: list[str] = Field(min_length=2)
    agreement_kappa: float


class IntentEpisode(Contract):
    # 스키마상 nullable이 아닌 선택 필드 (scenario_id 등 나머지는 type: [..., "null"])
    _reject_explicit_null: ClassVar[tuple[str, ...]] = (
        "disagreement_pairs", "evidence_refs", "dedup_hash",
    )

    episode_id: str = Field(pattern=r"^EP_")
    ontology_version: str
    lang: Literal["ko"]
    dataset_split: DatasetSplit
    reliability_tier: ReliabilityTier
    label_state: LabelState
    origin_channel: OriginChannel
    episode_creator_type: EpisodeCreatorType
    primary_subject_type: PrimarySubjectType
    scenario_id: str | None = None
    teacher_prompt: str = Field(min_length=1)
    persona_lens_used: str | None = None
    label_distribution: dict[str, float] = Field(min_length=1)
    consensus: float | None = Field(default=None, ge=0, le=1)
    disagreement_pairs: list[Annotated[list[str], Field(min_length=2, max_length=2)]] | None = None
    evidence_refs: list[str] | None = None
    human_review: HumanReview | None = None
    dedup_hash: str | None = None
    created_at: int

    @field_validator("label_distribution")
    @classmethod
    def _distribution_bounds(cls, v: dict[str, float]) -> dict[str, float]:
        for intent, p in v.items():
            if not 0 <= p <= 1:
                raise ValueError(f"label_distribution[{intent}]={p} — [0,1] 밖")
        return v

    @field_validator("evidence_refs")
    @classmethod
    def _evidence_ref_pattern(cls, v: list[str] | None) -> list[str] | None:
        for ref in v or []:
            if not ref.startswith("EV_"):
                raise ValueError(f"evidence_ref {ref!r}는 ^EV_ 패턴이어야 함")
        return v

    @model_validator(mode="after")
    def _benchmark_integrity(self) -> "IntentEpisode":
        if self.dataset_split == "BENCHMARK_HOLDOUT" and (
            self.reliability_tier != "GOLD"
            or self.label_state != "LABELED"
            or self.origin_channel in SYNTHETIC_ORIGINS
        ):
            raise ValueError(
                "benchmark_integrity: BENCHMARK_HOLDOUT ⇒ "
                "GOLD ∧ LABELED ∧ 비합성 origin (절대 규칙 2)"
            )
        return self
