"""infer_request.schema.json 파생 (runtime §3-0·§3-1).

Envelope + IntentCoreInput + mode별 extension.
절대 규칙 5: 훈련 메타데이터(gym_extension)는 Core에 절대 넣지 않는다 —
mode=live/shadow에서 gym_extension 키가 오면(null 포함) 거부.
"""
from typing import Any, ClassVar, Literal

from pydantic import Field, model_validator

from app.contracts.base import Contract
from app.contracts.visual_semantics import VisualSemantics


class ConversationTurn(Contract):
    _reject_explicit_null: ClassVar[tuple[str, ...]] = ("text", "shown_intent", "accepted")

    role: Literal["teacher", "brain"]
    text: str | None = None
    shown_intent: str | None = None
    accepted: bool | None = None
    ts: int


class SessionInfo(Contract):
    session_id: str
    surface_type: str
    conversation_history: list[ConversationTurn] = Field(max_length=6)


class PromptInfo(Contract):
    _reject_explicit_null: ClassVar[tuple[str, ...]] = ("input_method",)

    text: str = Field(min_length=1)
    lang: str
    input_method: Literal["typed", "voice"] | None = None


class WorkspaceObject(Contract):
    _reject_explicit_null: ClassVar[tuple[str, ...]] = (
        "bbox", "selected", "text_preview", "created_at", "modified_at",
        "relations", "visual_semantics",
    )

    object_id: str
    type: str
    bbox: list[float] | None = Field(default=None, min_length=4, max_length=4)
    selected: bool | None = None
    text_preview: str | None = Field(default=None, max_length=200)
    created_at: int | None = None
    modified_at: int | None = None
    relations: list[Any] | None = None
    visual_semantics: VisualSemantics | None = None


class WorkspaceContext(Contract):
    _reject_explicit_null: ClassVar[tuple[str, ...]] = ("derived_summary",)

    objects: list[WorkspaceObject] = Field(max_length=50)
    selection: list[str]
    derived_summary: dict[str, Any] | None = None


class RecentAction(Contract):
    action: str
    ts: int


class TeacherContext(Contract):
    _reject_explicit_null: ClassVar[tuple[str, ...]] = ("profile",)

    teacher_ref: str
    profile: dict[str, Any] | None = None


class RuntimeExtension(Contract):
    _reject_explicit_null: ClassVar[tuple[str, ...]] = ("timeout_ms", "max_candidates")

    timeout_ms: int | None = None
    max_candidates: int | None = None
    allowed_intents: list[str] | None = None  # 스키마상 nullable


class GymExtension(Contract):
    _reject_explicit_null: ClassVar[tuple[str, ...]] = (
        "scenario_id", "challenge_pack", "target_confusion", "difficulty", "training_strategy",
    )

    scenario_id: str | None = None
    challenge_pack: str | None = None
    target_confusion: list[Any] | None = None
    difficulty: str | None = None
    training_strategy: str | None = None


class ShadowExtension(Contract):
    _reject_explicit_null: ClassVar[tuple[str, ...]] = ("capture_batch_id",)

    capture_batch_id: str | None = None


class InferRequest(Contract):
    _reject_explicit_null: ClassVar[tuple[str, ...]] = (
        "runtime_extension", "gym_extension", "shadow_extension",
    )

    request_id: str
    schema_version: str
    mode: Literal["live", "shadow", "gym"]
    session: SessionInfo
    prompt: PromptInfo
    workspace_context: WorkspaceContext
    recent_actions: list[RecentAction] = Field(max_length=10)
    teacher_context: TeacherContext
    runtime_extension: RuntimeExtension | None = None
    gym_extension: GymExtension | None = None
    shadow_extension: ShadowExtension | None = None

    @model_validator(mode="after")
    def _core_extension_separation(self) -> "InferRequest":
        # 명시적 null은 _reject_explicit_null이 먼저 거부 — 여기선 존재만 검사
        if self.mode in ("live", "shadow") and self.gym_extension is not None:
            raise ValueError(
                f"mode={self.mode}에서는 gym_extension 금지 — "
                "훈련 메타데이터는 Core에 넣지 않는다 (절대 규칙 5, runtime §3-0)"
            )
        return self
