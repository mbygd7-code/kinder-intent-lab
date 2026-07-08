"""visual_semantics.schema.json 파생 — vs-1.0 통제 어휘, 자유 서술 금지 (§1-S5)."""
from typing import ClassVar, Literal

from pydantic import ConfigDict, Field, field_validator

from app.contracts.base import Contract

SceneType = Literal[
    "INDOOR_CLASSROOM", "OUTDOOR_YARD", "HALLWAY", "GYM_ROOM",
    "ART_CORNER", "READING_CORNER", "UNKNOWN",
]
ActivityType = Literal[
    "NATURE_SORTING", "BLOCK_PLAY", "ROLE_PLAY", "DRAWING_PAINTING", "BOOK_READING",
    "MUSIC_MOVEMENT", "SAND_WATER_PLAY", "BOARD_GAME", "FREE_PLAY", "MEAL_SNACK",
    "CIRCLE_TIME", "UNKNOWN",
]
Material = Literal[
    "LEAF", "TRAY", "BLOCK", "PAPER", "CRAYON", "PAINT", "BOOK", "SAND", "WATER",
    "FABRIC", "RECYCLED", "TOY_FIGURE", "UNKNOWN",
]
ObservedAction = Literal[
    "SORT", "COMPARE", "STACK", "DRAW", "CUT", "POUR", "OBSERVE", "TALK", "SHARE",
    "BUILD", "PRETEND", "UNKNOWN",
]
InteractionPattern = Literal[
    "SOLO", "PEER_PARALLEL", "PEER_COLLABORATIVE", "TEACHER_GUIDED", "GROUP_CIRCLE", "UNKNOWN"
]
GroupSizeBand = Literal["INDIVIDUAL", "PAIR", "SMALL_GROUP", "LARGE_GROUP", "UNKNOWN"]
SpatialPattern = Literal["OBJECT_GROUPING", "SCATTERED", "LINED_UP", "CENTERED", "UNKNOWN"]


class VisualSemantics(Contract):
    model_config = ConfigDict(extra="forbid", strict=True)  # additionalProperties: false

    _reject_explicit_null: ClassVar[tuple[str, ...]] = (
        "scene_type", "activity_types", "materials", "observed_actions",
        "interaction_pattern", "group_size_band", "spatial_pattern",
    )

    schema_version: str = Field(pattern=r"^vs-")
    extractor_version: str
    scene_type: list[SceneType] | None = None
    activity_types: list[ActivityType] | None = None
    materials: list[Material] | None = None
    observed_actions: list[ObservedAction] | None = None
    interaction_pattern: list[InteractionPattern] | None = None
    group_size_band: GroupSizeBand | None = None
    spatial_pattern: list[SpatialPattern] | None = None
    identity_removed: Literal[True]

    @field_validator("identity_removed", mode="before")
    @classmethod
    def _strict_true(cls, v: object) -> object:
        # Literal[True]는 1 == True 코어션을 허용하므로 (스키마 const true와 어긋남) 차단
        if v is not True:
            raise ValueError("identity_removed는 반드시 불리언 true (비식별 가드)")
        return v
