"""Seed Brain 추론 파이프라인 4단계 (§5-4·§5-5, T3.2).

[1] RETRIEVAL    발화 임베딩 ↔ 노드 exemplar 유사도 + Atlas 매치 → 후보 노드 ≤ retrieval_top_k
[2] LLM SCORER   후보 + 명시된 컨텍스트 신호(Core만) → 후보별 activation 0~1
[3] PRIOR 재정렬  activation × persona_prior × domain_prior (LLM 밖에서 곱, cap)
[4] 정규화        → 후보 목록 + confidence + margin(top1−top2)

절대 규칙 5: 훈련 메타데이터(gym_extension: scenario_id/target_confusion 등)는 Core 추론 입력에
절대 넣지 않는다 — mode=gym이어도 scorer는 Core 신호만 받는다(Core+extension 분리).
prior는 LLM 밖에서 곱하고 persona_prior_cap으로 제한(§5-5, 필터버블 방지). 4단계 기여는
inference_log(stages JSONB)에 분리 기록한다. decision 정책·HTTP는 T3.3.
"""
from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass, field

from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.brain.priors import (
    capped_prior_factor,
    current_state_version,
    get_population_priors,
    get_teacher_priors,
)
from app.brain.prompts import load_prompt
from app.contracts.infer_request import InferRequest
from app.core.config import ExperimentsConfig
from app.core.ontology import load_ontology
from app.foundry.agents.runner import render_agent_prompt, run_json_agent
from app.foundry.stages.s4_language_miner import cosine_similarity
from app.llm.client import LLMClient
from app.models.brain import BrainNode, Exemplar, InferenceLog
from app.models.foundry import AtlasEntry

EmbedFn = Callable[[list[str]], list[list[float]]]

_NEUTRAL_PRIOR = 0.5   # prior 중립값(=배수 1.0). 구조 상수, 실험 임계값 아님
_SCORER_PROMPT = load_prompt("scorer")


# --- [2] scorer 출력 계약 ---


class _ScoreItem(BaseModel):
    intent_id: str
    activation: float
    rationale: str = ""


class ScorerOutput(BaseModel):
    scores: list[_ScoreItem]


# --- Core 신호 추출 (절대 규칙 5) ---


@dataclass
class CoreSignals:
    """Brain 추론에 들어가는 Core 신호 — gym_extension(훈련 메타)은 절대 포함하지 않는다."""

    prompt_text: str
    lang: str
    surface_type: str
    selection: list[str]
    workspace_summary: dict
    recent_actions: list[str]
    teacher_ref: str


def core_signals(request: InferRequest) -> CoreSignals:
    ws = request.workspace_context
    return CoreSignals(
        prompt_text=request.prompt.text,
        lang=request.prompt.lang,
        surface_type=request.session.surface_type,
        selection=list(ws.selection),
        workspace_summary=ws.derived_summary or {"object_count": len(ws.objects)},
        recent_actions=[a.action for a in request.recent_actions],
        teacher_ref=request.teacher_context.teacher_ref,
    )


# --- [1] retrieval ---


@dataclass
class RetrievalCandidate:
    intent_id: str
    node_id: str
    source: str      # "exemplar" | "atlas"
    similarity: float  # 1 - cosine_distance (높을수록 가까움)


def retrieve_candidates(
    session: Session,
    utterance_vec: list[float],
    config: ExperimentsConfig,
    embed_fn: EmbedFn | None = None,
) -> list[RetrievalCandidate]:
    """exemplar 최근접(pgvector) + Atlas possible_intents → 후보 노드 ≤ retrieval_top_k."""
    top_k = config.brain.retrieval_top_k
    nodes = {n.intent_id: n.node_id for n in session.scalars(select(BrainNode))}

    # exemplar: 코사인 거리 오름차순(hnsw 인덱스) → intent별 최근접만
    best: dict[str, float] = {}
    dist = Exemplar.embedding.cosine_distance(utterance_vec).label("dist")
    rows = session.execute(
        select(Exemplar.intent_id, dist).order_by(dist)
    ).all()
    cands: list[RetrievalCandidate] = []
    for intent, dist in rows:
        if intent not in best:
            best[intent] = 1.0 - float(dist)
            cands.append(RetrievalCandidate(intent, nodes[intent], "exemplar", best[intent]))

    # Atlas 보강: 발화와 map_min_similarity 이상 가까운 atlas surface_form의 possible_intents.
    # intent가 여러 atlas entry에 걸치면 최대 유사도를 취한다(최초 아님 — 순서 무관·결정론).
    if embed_fn is not None:
        atlas = list(session.scalars(select(AtlasEntry)))
        if atlas:
            svecs = embed_fn([a.surface_form for a in atlas])
            min_sim = config.atlas.map_min_similarity
            atlas_best: dict[str, float] = {}
            for a, sv in zip(atlas, svecs, strict=True):
                sim = cosine_similarity(list(utterance_vec), sv)
                if sim < min_sim:
                    continue
                for intent in a.possible_intents or []:
                    if intent in nodes and intent not in best:  # exemplar 후보 우선
                        atlas_best[intent] = max(atlas_best.get(intent, 0.0), sim)
            for intent, sim in atlas_best.items():
                best[intent] = sim
                cands.append(RetrievalCandidate(intent, nodes[intent], "atlas", sim))

    cands.sort(key=lambda c: c.similarity, reverse=True)
    return cands[:top_k]


# --- [2] LLM scorer (Core 신호만) ---


def score_candidates(
    client: LLMClient, core: CoreSignals, candidate_intents: list[str], model: str
) -> dict[str, tuple[float, str]]:
    """후보별 activation을 LLM으로 채점한다. 입력은 Core 신호만(절대 규칙 5)."""
    if not candidate_intents:
        return {}
    context = {
        "candidate_intents": candidate_intents,
        "utterance": core.prompt_text,
        "lang": core.lang,
        "surface_type": core.surface_type,
        "selection": core.selection,
        "workspace_summary": core.workspace_summary,
        "recent_actions": core.recent_actions,
    }  # gym_extension/scenario_id/target_confusion 없음 — Core만
    out = run_json_agent(
        client, render_agent_prompt(_SCORER_PROMPT, context), model, ScorerOutput
    )
    allowed = set(candidate_intents)
    scored: dict[str, tuple[float, str]] = {}
    for s in out.scores:
        if s.intent_id in allowed:  # 후보 밖 intent는 무시(scorer가 새 intent 못 만든다)
            scored[s.intent_id] = (max(0.0, min(1.0, s.activation)), s.rationale)
    # LLM이 일부 후보를 누락하면 0으로 백필 — 후보가 파이프라인에서 조용히 사라지지 않게 한다
    for intent in candidate_intents:
        scored.setdefault(intent, (0.0, "not scored"))
    return scored


# --- [3] prior 재정렬 (LLM 밖, cap) ---


@dataclass
class PriorApplied:
    reranked: dict[str, float]         # intent -> activation × prior factor
    factors: dict[str, float]          # intent -> 적용된 prior 배수
    persona_state_version: str | None
    fallback_used: bool
    tier: str                          # "individual" | "population" | "neutral"


def apply_priors(
    session: Session,
    scored: dict[str, tuple[float, str]],
    teacher_ref: str,
    config: ExperimentsConfig,
    cluster_id: str | None = None,
) -> PriorApplied:
    """activation에 cap 적용된 persona prior 배수를 곱한다. domain_prior는 v1 중립(1.0).

    persona prior는 2-tier(§5-3): 개인(teacher) prior 우선 → 없으면 population(cluster) prior
    (신규·워밍업 교사의 콜드스타트, §4-1) → 둘 다 없으면 중립 default. fallback_used는 어느
    tier도 prior를 못 준 경우(진짜 조회 실패)만 True — '개인 prior 미분기'는 fallback이 아니다.
    (persona_warmup 회수 기반 분기 시점 자체는 개인 prior 적재 정책 소관 — 여기선 존재로 판정.)
    """
    cap = config.brain.persona_prior_cap
    tset = get_teacher_priors(session, teacher_ref)  # state_version 항상 동반(replay)
    priors, psv, tier = tset.priors, tset.state_version, "individual"
    if not priors and cluster_id is not None:
        pset = get_population_priors(session, cluster_id)
        if pset.priors:
            priors, psv, tier = pset.priors, pset.state_version, "population"
    if not priors:
        tier = "neutral"
        psv = psv or current_state_version(session)
    fallback_used = tier == "neutral"

    reranked: dict[str, float] = {}
    factors: dict[str, float] = {}
    for intent, (act, _rationale) in scored.items():
        p = priors.get(intent, _NEUTRAL_PRIOR)
        factor = capped_prior_factor(p, cap)  # persona prior (× domain_prior 1.0)
        factors[intent] = factor
        reranked[intent] = act * factor
    return PriorApplied(reranked, factors, psv, fallback_used, tier)


# --- [4] 정규화 + margin ---


@dataclass
class RankResult:
    ranked: list[tuple[str, float]]  # (intent, normalized_score) 내림차순
    top_intent: str | None
    confidence: float                # 분포상 top 우세도(합=1 정규화)
    margin: float                    # top1 − top2 (정규화)
    top_activation: float            # top 후보의 원(raw) 활성도×prior — 절대 강도(abstain 판정용)


def normalize_and_rank(reranked: dict[str, float]) -> RankResult:
    if not reranked:
        return RankResult([], None, 0.0, 0.0, 0.0)
    total = sum(reranked.values()) or 1.0
    normalized = {i: s / total for i, s in reranked.items()}
    ranked = sorted(normalized.items(), key=lambda kv: kv[1], reverse=True)
    top = ranked[0][1]
    second = ranked[1][1] if len(ranked) > 1 else 0.0
    # 단일 후보는 정규화상 confidence=1이 되므로, 절대 강도(raw)를 별도로 남겨 T3.3 abstain이
    # 약한 단일 후보를 실행으로 오판하지 않게 한다.
    top_activation = min(1.0, max(0.0, reranked[ranked[0][0]]))
    return RankResult(
        ranked, ranked[0][0], round(top, 4), round(top - second, 4), round(top_activation, 4)
    )


# --- 오케스트레이션 + inference_log ---


@dataclass
class InferenceResult:
    candidates: list[dict] = field(default_factory=list)  # [{intent_id, domain, score}]
    top_intent: str | None = None
    confidence: float = 0.0
    margin: float = 0.0
    top_activation: float = 0.0       # top 절대 강도(raw) — T3.3 abstain 판정용
    persona_state_version: str | None = None
    fallback_used: bool = False
    prior_tier: str = "neutral"       # individual | population | neutral
    inference_id: str = ""
    # prior를 곱하기 **전**의 순수 activation (intent → 0~1). §5-5가 prior를 LLM 밖에서 곱하는
    # 이유 ①("Persona Lift/Harm을 측정 가능")이 여기에 걸려 있다: 이 값이 있으면 LLM을 다시
    # 부르지 않고 다른 prior로 재정렬해 lift/harm을 잴 수 있다. 소비처는 Arena뿐.
    activations: dict[str, float] = field(default_factory=dict)


def infer(
    session: Session,
    request: InferRequest,
    client: LLMClient,
    embed_fn: EmbedFn,
    config: ExperimentsConfig,
    model: str = "brain",
) -> InferenceResult:
    """4단계 추론을 실행하고 stages를 inference_log에 분리 기록한다."""
    profile = request.teacher_context.profile or {}
    return infer_core(
        session,
        core_signals(request),  # 절대 규칙 5: Core만
        client,
        embed_fn,
        config,
        request_id=request.request_id,
        mode=request.mode,
        cluster_id=profile.get("persona_cluster"),  # 있으면 population prior 콜드스타트
        model=model,
    )


def infer_core(
    session: Session,
    core: CoreSignals,
    client: LLMClient,
    embed_fn: EmbedFn,
    config: ExperimentsConfig,
    *,
    request_id: str,
    mode: str,
    cluster_id: str | None = None,
    model: str = "brain",
) -> InferenceResult:
    """Core 신호에서 곧바로 4단계를 실행한다 — HTTP 요청 계약에 묶이지 않는 단일 추론 경로.

    Arena(§8-2)처럼 InferRequest envelope이 없는 호출자가 **같은 파이프라인**을 쓰게 해서
    '벤치마크는 다른 코드로 돌았다'는 귀속 오류를 구조적으로 없앤다. mode는 inference_log에만
    남는 관측 라벨이다(계약 enum이 아니다).
    """
    uvec = embed_fn([core.prompt_text])[0]

    retrieved = retrieve_candidates(session, uvec, config, embed_fn)          # [1]
    scored = score_candidates(client, core, [c.intent_id for c in retrieved], model)  # [2]
    prior = apply_priors(session, scored, core.teacher_ref, config, cluster_id)  # [3]
    rank = normalize_and_rank(prior.reranked)                                # [4]

    domains = {i.intent_id: i.domain for i in load_ontology().intents}
    candidates = [
        {"intent_id": i, "domain": domains.get(i), "score": s} for i, s in rank.ranked
    ]
    stages = {
        "retrieval": [
            {"intent_id": c.intent_id, "source": c.source, "similarity": round(c.similarity, 4)}
            for c in retrieved
        ],
        "scorer": [
            {"intent_id": i, "activation": round(a, 4), "rationale": r}
            for i, (a, r) in scored.items()
        ],
        "prior": {
            "tier": prior.tier,
            "factors": [{"intent_id": i, "factor": round(f, 4)} for i, f in prior.factors.items()],
        },
        "normalize": {
            "top_activation": rank.top_activation,
            "scores": [{"intent_id": i, "score": round(s, 4)} for i, s in rank.ranked],
        },
    }
    inference_id = "IL_" + uuid.uuid4().hex[:12]
    session.add(
        InferenceLog(
            inference_id=inference_id,
            request_id=request_id,
            mode=mode,
            top_intent=rank.top_intent,
            confidence=rank.confidence,
            margin=rank.margin,
            persona_state_version=prior.persona_state_version,
            fallback_used=prior.fallback_used,
            stages=stages,
        )
    )
    session.flush()
    return InferenceResult(
        candidates=candidates[:5],
        top_intent=rank.top_intent,
        confidence=rank.confidence,
        margin=rank.margin,
        top_activation=rank.top_activation,
        persona_state_version=prior.persona_state_version,
        fallback_used=prior.fallback_used,
        prior_tier=prior.tier,
        inference_id=inference_id,
        activations={i: a for i, (a, _r) in scored.items()},  # prior 곱하기 전 (§5-5)
    )
