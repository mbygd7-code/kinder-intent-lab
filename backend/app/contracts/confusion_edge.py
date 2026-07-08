"""confusion_edge.schema.json 파생 (§5-6). 방향성 edge — (A,B) ≠ (B,A)."""
from typing import ClassVar, Literal

from pydantic import Field

from app.contracts.base import Contract

EdgeState = Literal["hypothesized", "observed", "confirmed"]
EdgeOrigin = Literal["SKEPTIC", "CONSENSUS_DISAGREEMENT", "GYM_CORRECTION", "ARENA_MATRIX"]


class ContrastExemplar(Contract):
    utterance: str
    true_intent: str


class ConfusionEdge(Contract):
    # confusion_rate는 스키마상 nullable — 목록 제외
    _reject_explicit_null: ClassVar[tuple[str, ...]] = (
        "origin", "evidence_runs", "contrast_exemplars", "last_updated",
    )

    edge_id: str = Field(pattern=r"^CE_")
    from_true: str
    to_predicted: str
    confusion_rate: float | None = Field(default=None, ge=0, le=1)
    state: EdgeState
    origin: EdgeOrigin | None = None
    evidence_runs: list[str] | None = None
    contrast_exemplars: list[ContrastExemplar] | None = None
    last_updated: int | None = None
