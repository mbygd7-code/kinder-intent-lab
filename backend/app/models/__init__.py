"""SQLAlchemy 모델 — db/migrations/001_init.sql과 동기 (테스트로 강제).

import 시점에 guards의 flush 리스너(GOLD 불변식)가 활성화된다.
"""
from app.models import guards  # noqa: F401 — flush 리스너 등록
from app.models.arena import ArenaRun, KtibItem, KtibVersion
from app.models.base import Base
from app.models.benchmark_candidates import (
    BenchmarkCandidateBatch,
    BenchmarkCandidateItem,
)
from app.models.brain import (
    BrainNode,
    BrainVersion,
    ConfusionEdge,
    Exemplar,
    InferenceLog,
)
from app.models.episodes import Episode, Evidence
from app.models.foundry import (
    AtlasEntry,
    AtlasExpansionEntry,
    CanonicalScenario,
    FailedEpisode,
    FoundryWorkOrder,
    SituationFrame,
    Source,
    SourceDocument,
)
from app.models.governance import GovernanceEvent, OntologyVersion
from app.models.gym import ChallengePack, GymSession
from app.models.persona import (
    PersonaCluster,
    PersonaStateVersion,
    PopulationPrior,
    TeacherPrior,
)

__all__ = [
    "ArenaRun",
    "AtlasEntry",
    "AtlasExpansionEntry",
    "Base",
    "BenchmarkCandidateBatch",
    "BenchmarkCandidateItem",
    "BrainNode",
    "BrainVersion",
    "CanonicalScenario",
    "ChallengePack",
    "ConfusionEdge",
    "Episode",
    "Evidence",
    "Exemplar",
    "FailedEpisode",
    "FoundryWorkOrder",
    "GovernanceEvent",
    "GymSession",
    "InferenceLog",
    "KtibItem",
    "KtibVersion",
    "OntologyVersion",
    "PersonaCluster",
    "PersonaStateVersion",
    "PopulationPrior",
    "SituationFrame",
    "Source",
    "SourceDocument",
    "TeacherPrior",
]
