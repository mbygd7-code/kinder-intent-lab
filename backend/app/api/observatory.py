"""GET /v1/observatory/brain — 3D Brain 렌더 상태 (§7-1·§7-5·§7-6).

원칙 8(절대 규칙 3): brightness 계열의 원천은 Arena뿐이다.
- ktib_global ← 최신 **run_type='brain'** arena_runs.metrics.first_intent_accuracy
  (zero-shot 베이스라인 run은 3D에 새지 않는다 — §8-2 베이스라인 규칙)
- node.heldout_accuracy ← brain_nodes 컬럼 그대로 (promote 경로만 기록; 여기선 읽기 전용)
- region.reliability ← region 내 비null heldout 평균 (전부 null이면 null)
- stage ← §7-6 성장 스테이지, 전부 위 Arena 산출에서 유도(저장하지 않고 매번 재계산)
여기서 어떤 값도 계산으로 지어내지 않는다 — 훈련량(size)·다양성(density)은 evidence_stats에서.
"""
from __future__ import annotations

import hashlib
import math
import uuid
from datetime import datetime

import yaml
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.aggregator.review import canonical_reviewer, weighted_cohens_kappa
from app.arena.ktib import EmptyKtib, build_ktib
from app.arena.stages import STAGE_NAMES, brain_stage, region_stages, stage4_inputs
from app.brain.diagnosis import diagnose_node
from app.brain.priors import current_state_version
from app.brain.version_gate import version_gate_status
from app.contracts.observatory import ObservatoryBrain, ObservatoryNode, ObservatoryRegion
from app.core.config import ExperimentsConfig, get_config
from app.core.db import get_session
from app.core.ontology import CANONICAL_DOMAINS, UNKNOWN_INTENT_ID, load_ontology
from app.foundry.expert_ingest import (
    BenchmarkNeedsReview,
    ExpertEpisode,
    SyntheticChannelRejected,
    TrainBenchmarkContamination,
    UnknownIngestIntent,
    ingest_expert_episodes,
)
from app.models.arena import KtibUpload
from app.models.benchmark_candidates import (
    BenchmarkCandidateBatch,
    BenchmarkCandidateItem,
)
from app.models.brain import BrainNode, BrainVersion, ConfusionEdge, Exemplar, InferenceLog
from app.models.episodes import Episode, Evidence
from app.models.foundry import AtlasExpansionEntry
from app.models.persona import PersonaCluster, PopulationPrior
from app.observatory import aggregate

router = APIRouter(prefix="/v1/observatory", tags=["observatory"])

# evidence_stats 버킷(§5-1 계약 EvidenceStats의 구조 상수 — 실험 임계값 아님)
_BUCKETS = ("synthetic", "weak_behavioral", "human_confirmed", "gold", "expert")


def _get_experiments() -> ExperimentsConfig:
    return get_config()


def _diversity(stats: dict) -> float:
    """Evidence Diversity(§7-5 Density 원천) = 버킷 분포의 정규화 섀넌 엔트로피 [0,1]."""
    counts = [int(stats.get(b, 0) or 0) for b in _BUCKETS]
    total = sum(counts)
    if total <= 0:
        return 0.0
    entropy = -sum((c / total) * math.log(c / total) for c in counts if c > 0)
    return round(entropy / math.log(len(_BUCKETS)), 4)


# §7-1 중앙 수치의 단일 원천 — 대시보드와 공유하려 app.observatory.aggregate로 이동.
# (배제 규칙 — baseline run·candidate run — 의 근거 주석은 aggregate.ktib_global에 있다.)
_ktib_global = aggregate.ktib_global


def _brain_version(session: Session) -> str:
    v = session.scalar(
        select(BrainVersion.version)
        .where(BrainVersion.decision == "promote")
        .order_by(BrainVersion.created_at.desc())
    )
    return v or "seed-v0"


@router.get("/brain", response_model=ObservatoryBrain)
def brain_state(
    session: Session = Depends(get_session),
    config: ExperimentsConfig = Depends(_get_experiments),
) -> ObservatoryBrain:
    nodes = list(session.scalars(select(BrainNode)))
    exemplar_counts = dict(
        session.execute(
            select(Exemplar.node_id, func.count()).group_by(Exemplar.node_id)
        ).all()
    )

    out_nodes: list[ObservatoryNode] = []
    region_acc: dict[str, dict] = {
        d: {"nodes": 0, "gold": 0, "synthetic": 0, "heldouts": []} for d in CANONICAL_DOMAINS
    }
    for n in nodes:
        stats = n.evidence_stats or {}
        buckets = {b: int(stats.get(b, 0) or 0) for b in _BUCKETS}
        total = sum(buckets.values())
        out_nodes.append(ObservatoryNode(
            node_id=n.node_id,
            intent_id=n.intent_id,
            region=n.region,
            evidence_total=total,
            evidence_diversity=_diversity(stats),
            gold_count=buckets["gold"],
            exemplar_count=int(exemplar_counts.get(n.node_id, 0)),
            heldout_accuracy=n.heldout_accuracy,   # Arena 전용 컬럼 — 그대로 통과
            calibration_ece=n.calibration_ece,
            last_arena_run=n.last_arena_run,
            pending_evaluation=n.pending_evaluation,
            evidence_buckets=buckets,              # §3-1 버킷 — 3D evidence 파티클 원천
        ))
        acc = region_acc[n.region]
        acc["nodes"] += 1
        acc["gold"] += int(stats.get("gold", 0) or 0)
        acc["synthetic"] += int(stats.get("synthetic", 0) or 0)
        if n.heldout_accuracy is not None:
            acc["heldouts"].append(float(n.heldout_accuracy))

    stages = region_stages(session, config)  # §7-6 — Arena 산출에서 유도
    regions = [
        ObservatoryRegion(
            region=d,
            reliability=(
                round(sum(a["heldouts"]) / len(a["heldouts"]), 4) if a["heldouts"] else None
            ),
            node_count=a["nodes"],
            gold_evidence=a["gold"],
            synthetic_evidence=a["synthetic"],
            stage=stages[d].stage,
            stage_name=stages[d].stage_name,
            measured_count=stages[d].measured_count,
        )
        for d, a in region_acc.items()
    ]

    ktib_global = _ktib_global(session)
    # Stage 4(Semantic Cross-Region Flow)는 confirmed cross-region edge + 동일 ktib_version의
    # 최근 W개 brain run 추세가 있어야 판정된다. 근거가 없으면 방출되지 않는다(§7-6).
    edges, run_history = stage4_inputs(session, config)
    global_stage = brain_stage(
        ktib_global, stages, config, edges=edges, run_history=run_history
    )
    return ObservatoryBrain(
        brain_version=_brain_version(session),
        ontology_version=load_ontology().version,
        ktib_global=ktib_global,
        brain_stage=global_stage,
        brain_stage_name=STAGE_NAMES[global_stage],
        regions=regions,
        nodes=out_nodes,
    )


# --- Persona Overlay (§4-2·§7-6, T5.4) ---


class PersonaOverlayCluster(BaseModel):
    cluster_id: str
    member_count: int | None
    state_version: str
    priors: dict[str, float]  # intent_id → persona prior (activation을 곱으로 재정렬, §5-5)


class PersonaOverlayOut(BaseModel):
    """같은 뇌를 페르소나 클러스터별 활성 분포로 전환해 본다 (§7-6).

    원천은 `population_priors` — §5-5에서 **LLM 밖에서 activation에 곱해지는 배수**다.
    측정된 클러스터별 정확도(Persona Lift/Harm)가 **아니다**. 그 지표는 docs/05-arena §8-3에
    정의돼 있고 `app/arena/persona.py`가 arena run 시점에 계산해 `metrics["persona"]`에 동결한다.
    이 엔드포인트는 의도적으로 **prior 배수만** 노출한다 — 여기서 측정값을 지어내지 않는다.
    """

    state_version: str | None
    prior_cap: float          # §5-5 persona_prior_cap — 오버레이가 과장돼 보이지 않도록 함께 준다
    clusters: list[PersonaOverlayCluster]


@router.get("/persona-overlay", response_model=PersonaOverlayOut)
def persona_overlay(
    session: Session = Depends(get_session),
    config: ExperimentsConfig = Depends(_get_experiments),
) -> PersonaOverlayOut:
    """클러스터별 prior 분포. 클러스터가 없으면 빈 목록(§4 Persona Discovery 미실행)."""
    state_version = current_state_version(session)
    clusters = {c.cluster_id: c for c in session.scalars(select(PersonaCluster))}
    if not clusters or state_version is None:
        return PersonaOverlayOut(
            state_version=state_version, prior_cap=config.brain.persona_prior_cap, clusters=[]
        )

    rows = session.scalars(
        select(PopulationPrior).where(PopulationPrior.state_version == state_version)
    ).all()
    grouped: dict[str, dict[str, float]] = {}
    for row in rows:
        grouped.setdefault(row.cluster_id, {})[row.intent_id] = float(row.prior)

    return PersonaOverlayOut(
        state_version=state_version,
        prior_cap=config.brain.persona_prior_cap,
        clusters=[
            PersonaOverlayCluster(
                cluster_id=cid,
                member_count=clusters[cid].member_count,
                state_version=state_version,
                priors=dict(sorted(priors.items())),
            )
            for cid, priors in sorted(grouped.items())
            if cid in clusters
        ],
    )


# --- 노드 Weakness 진단 (§7-3, T4.1 실계산) ---


class AxisOut(BaseModel):
    value: float | None  # §7-3 원값. null = 데이터 없음(계산 불가)
    level: str | None    # HIGH | MED | LOW | null


class NodeDiagnosisOut(BaseModel):
    intent_id: str
    ambiguous_language: AxisOut
    screen_context_coverage: AxisOut
    persona_diversity: AxisOut
    gold_data: AxisOut


@router.get("/node/{intent_id}/diagnosis", response_model=NodeDiagnosisOut)
def node_diagnosis(
    intent_id: str,
    session: Session = Depends(get_session),
    config: ExperimentsConfig = Depends(_get_experiments),
) -> NodeDiagnosisOut:
    """§7-3 4축 실계산. 데이터 없는 축은 value/level null(지어내지 않음)."""
    real = {i.intent_id for i in load_ontology().intents if i.intent_id != UNKNOWN_INTENT_ID}
    if intent_id not in real:
        raise HTTPException(status_code=404, detail="알 수 없는 intent")
    dg = diagnose_node(session, intent_id, config)

    def ax(a) -> AxisOut:
        return AxisOut(value=a.value, level=a.level)

    return NodeDiagnosisOut(
        intent_id=dg.intent_id,
        ambiguous_language=ax(dg.ambiguous_language),
        screen_context_coverage=ax(dg.screen_context_coverage),
        persona_diversity=ax(dg.persona_diversity),
        gold_data=ax(dg.gold_data),
    )


# --- 노드 방향성 혼동쌍 (§5-6 confusion_edges 실데이터) ---

# state 우선순위 — 대표 정렬용(높을수록 먼저). rate가 있는 edge가 우선이고, 그다음 이 순위.
_CONFUSION_STATE_RANK = {"confirmed": 2, "observed": 1, "hypothesized": 0}


class ConfusionEdgeOut(BaseModel):
    to_predicted: str            # 혼동 대상 intent (from_true=이 노드)
    confusion_rate: float | None  # §5-6 — Arena 측정 전이면 null(지어내지 않음)
    state: str                   # hypothesized | observed | confirmed
    origin: str | None           # SKEPTIC | CONSENSUS_DISAGREEMENT | GYM_CORRECTION | ARENA_MATRIX


class NodeConfusionsOut(BaseModel):
    """방향성 혼동쌍(from_true=이 노드). §5-6 실데이터 — rate는 Arena만 채운다.

    edges는 대표 순서(측정된 것 먼저 · rate 내림차순 · state 우선순위). measured=False면
    아직 Arena가 이 노드를 재지 않아 전부 가설(rate null)이다 — mock이 아니라 실제 가설 edge다.
    """

    intent_id: str
    measured: bool               # 이 노드에서 rate가 측정된 edge가 하나라도 있나
    edges: list[ConfusionEdgeOut]


@router.get("/node/{intent_id}/confusions", response_model=NodeConfusionsOut)
def node_confusions(
    intent_id: str,
    session: Session = Depends(get_session),
) -> NodeConfusionsOut:
    """§5-6 방향성 혼동쌍 — from_true=intent_id인 edge를 대표 순서로. 없으면 빈 목록."""
    real = {i.intent_id for i in load_ontology().intents if i.intent_id != UNKNOWN_INTENT_ID}
    if intent_id not in real:
        raise HTTPException(status_code=404, detail="알 수 없는 intent")
    rows = list(
        session.scalars(select(ConfusionEdge).where(ConfusionEdge.from_true == intent_id))
    )
    # 안정 정렬 2단: 먼저 이름 오름차순(결정론 tiebreak) → 대표성 키 내림차순
    rows.sort(key=lambda e: e.to_predicted)
    rows.sort(
        key=lambda e: (
            e.confusion_rate is not None,          # 측정된 edge 먼저
            e.confusion_rate or 0.0,               # rate 높은 순
            _CONFUSION_STATE_RANK.get(e.state, -1),  # 확정 > 관측 > 가설
        ),
        reverse=True,
    )
    return NodeConfusionsOut(
        intent_id=intent_id,
        measured=any(e.confusion_rate is not None for e in rows),
        edges=[
            ConfusionEdgeOut(
                to_predicted=e.to_predicted,
                confusion_rate=e.confusion_rate,
                state=e.state,
                origin=e.origin,
            )
            for e in rows
        ],
    )


# --- 전 노드 혼동 edge 목록 (§5-6·§7-5 — 3D edge 레이어 원천) ---


class GlobalConfusionEdgeOut(BaseModel):
    edge_id: str
    from_intent: str              # from_true — 방향성 유지
    to_intent: str                # to_predicted
    confusion_rate: float | None  # Arena 측정 전 null (지어내지 않음)
    state: str                    # hypothesized | observed | confirmed (단조)
    origin: str | None


class GlobalConfusionEdgesOut(BaseModel):
    """전체 방향성 혼동 edge. §7-5 Edge Thickness(state)·Edge Flicker(rate)의 원천.

    measured_count는 rate가 측정된 edge 수 — 프론트 HUD가 '가설 N · 측정 M'으로
    정직하게 표기한다(전부 가설이어도 mock이 아니라 실제 SKEPTIC 가설 edge다).
    """

    total: int
    measured_count: int
    edges: list[GlobalConfusionEdgeOut]


@router.get("/confusion-edges", response_model=GlobalConfusionEdgesOut)
def global_confusion_edges(
    session: Session = Depends(get_session),
) -> GlobalConfusionEdgesOut:
    """전 edge를 대표 순서(측정 우선 → rate 내림차순 → state 랭크 → 이름)로 반환."""
    rows = list(session.scalars(select(ConfusionEdge)))
    # 안정 정렬 2단 — node_confusions와 동일 규칙 (이름 오름차순 tiebreak)
    rows.sort(key=lambda e: (e.from_true, e.to_predicted))
    rows.sort(
        key=lambda e: (
            e.confusion_rate is not None,
            e.confusion_rate or 0.0,
            _CONFUSION_STATE_RANK.get(e.state, -1),
        ),
        reverse=True,
    )
    return GlobalConfusionEdgesOut(
        total=len(rows),
        measured_count=sum(1 for e in rows if e.confusion_rate is not None),
        edges=[
            GlobalConfusionEdgeOut(
                edge_id=e.edge_id,
                from_intent=e.from_true,
                to_intent=e.to_predicted,
                confusion_rate=e.confusion_rate,
                state=e.state,
                origin=e.origin,
            )
            for e in rows
        ],
    )


# --- Version Gate 상태 (§6-6, T4.5 — candidate pending 표시용, 읽기 전용) ---


class VersionGateOut(BaseModel):
    base_version: str
    new_gold: int
    min_new_gold: int
    condition_met: bool           # 신규 GOLD ≥ 임계 → 후보 빌드 가능
    pending_candidate: str | None  # 아직 Arena 판정 안 난 후보(있으면 버전명)


@router.get("/version-gate", response_model=VersionGateOut)
def version_gate(
    session: Session = Depends(get_session),
    config: ExperimentsConfig = Depends(_get_experiments),
) -> VersionGateOut:
    """§6-6 후보 생성 게이트 상태 — 읽기만 한다(후보 빌드는 배치 scripts/run_version_gate.py)."""
    s = version_gate_status(session, config)
    return VersionGateOut(
        base_version=s.base_version, new_gold=s.new_gold, min_new_gold=s.min_new_gold,
        condition_met=s.condition_met, pending_candidate=s.pending_candidate,
    )


# --- 시험지(KTIB) 업로드 — 전문가 저작 YAML 등록·동결 (§8-2, scripts CLI의 웹 진입점) ---


class KtibEpisodeIn(BaseModel):
    """구조화 입력(CSV/시트에서 프론트가 변환한 한 행). episode_id 없으면 내용 해시로 생성."""

    teacher_prompt: str
    intent: str
    episode_id: str | None = None
    lang: str = "ko"
    reviewers: list[str] = []
    agreement_kappa: float | None = None
    agreement_rate: float | None = None  # O/X 승인 검수의 관측 일치율(§3-3 v1.6 대체 인증)


class KtibUploadIn(BaseModel):
    commit: bool = False   # False=검증만(dry-run), True=실제 적재·동결
    # 입력 방식 A: 원문 YAML (헤더·episodes를 모두 담음)
    yaml_text: str | None = None
    # 입력 방식 B: 구조화(CSV/시트 → 프론트 변환). yaml_text가 없을 때 사용한다.
    authored_by: str | None = None
    approved_by: str | None = None
    origin_channel: str = "EXPERT_AUTHORED"
    dataset_split: str = "BENCHMARK_HOLDOUT"
    episodes: list[KtibEpisodeIn] | None = None
    # 올린 원문(CSV/YAML) 그대로 — 이력에 보관해 목록에서 다시 열람·회수한다(§ 마이그레이션 0018)
    source_document: str | None = None


class KtibUploadOut(BaseModel):
    ok: bool
    dry_run: bool
    inserted: int = 0
    skipped_duplicate: int = 0
    eligible_total: int = 0        # 등록 시 시험지에 담길 총 문항 수
    ktib_version: str | None = None
    message: str


def _parse_ktib_yaml(text: str) -> tuple[dict, list[ExpertEpisode]]:
    """업로드 YAML → (헤더 dict, 에피소드 목록). 형식 오류는 400으로 친절히 안내한다."""
    try:
        doc = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=400, detail=f"YAML 형식 오류: {exc}") from exc
    if not isinstance(doc, dict):
        raise HTTPException(status_code=400, detail="YAML 최상위가 객체(키:값)가 아닙니다")
    for key in ("authored_by", "approved_by", "origin_channel", "dataset_split"):
        val = str(doc.get(key, "")).strip()
        if not val or val.startswith("<"):
            raise HTTPException(status_code=400, detail=f"'{key}' 항목을 채워주세요")
    raw = doc.get("episodes")
    if not isinstance(raw, list) or not raw:
        raise HTTPException(status_code=400, detail="episodes(문항)가 비어 있습니다")
    episodes: list[ExpertEpisode] = []
    for e in raw:
        if not isinstance(e, dict):
            raise HTTPException(status_code=400, detail="episodes 항목 형식이 올바르지 않습니다")
        for key in ("episode_id", "teacher_prompt", "intent"):
            val = e.get(key)
            if not val or str(val).startswith("<"):
                raise HTTPException(
                    status_code=400,
                    detail=f"문항 {e.get('episode_id', '?')}의 '{key}'를 채워주세요",
                )
        episodes.append(ExpertEpisode(
            episode_id=str(e["episode_id"]),
            teacher_prompt=str(e["teacher_prompt"]),
            intent=str(e["intent"]),
            lang=str(e.get("lang", "ko")),
            reviewers=tuple(str(r) for r in (e.get("reviewers") or ())),
            agreement_kappa=e.get("agreement_kappa"),
            agreement_rate=e.get("agreement_rate"),
        ))
    return doc, episodes


def _episodes_from_rows(payload: KtibUploadIn) -> tuple[dict, list[ExpertEpisode]]:
    """구조화 입력(CSV/시트) → (헤더, 에피소드). 작성자/승인자는 별도 입력받는다."""
    if not payload.episodes:
        raise HTTPException(status_code=400, detail="문항이 비어 있습니다")
    for key, val in (("작성자", payload.authored_by), ("승인자", payload.approved_by)):
        if not val or not str(val).strip():
            raise HTTPException(status_code=400, detail=f"{key}를 입력해주세요")
    doc = {
        "authored_by": str(payload.authored_by).strip(),
        "approved_by": str(payload.approved_by).strip(),
        "origin_channel": payload.origin_channel,
        "dataset_split": payload.dataset_split,
    }
    episodes: list[ExpertEpisode] = []
    for i, e in enumerate(payload.episodes, 1):
        prompt = (e.teacher_prompt or "").strip()
        intent = (e.intent or "").strip()
        if not prompt or not intent:
            raise HTTPException(status_code=400, detail=f"{i}번째 행의 발화/의도를 채워주세요")
        # episode_id 미지정 시 내용 해시 — 같은 문항 재업로드는 같은 id → dedup으로 건너뜀
        eid = e.episode_id or (
            "EP_" + hashlib.sha1(f"{intent}\x1f{prompt}".encode()).hexdigest()[:12]
        )
        episodes.append(ExpertEpisode(
            episode_id=eid, teacher_prompt=prompt, intent=intent, lang=(e.lang or "ko"),
            reviewers=tuple(str(r).strip() for r in (e.reviewers or []) if str(r).strip()),
            agreement_kappa=e.agreement_kappa,
            agreement_rate=e.agreement_rate,
        ))
    return doc, episodes


@router.post("/ktib/upload", response_model=KtibUploadOut)
def ktib_upload(
    payload: KtibUploadIn,
    session: Session = Depends(get_session),
    config: ExperimentsConfig = Depends(_get_experiments),
) -> KtibUploadOut:
    """시험지 YAML을 등록한다. commit=False면 검증만(dry-run), True면 적재 + KTIB 동결.

    적재·동결은 savepoint 안에서 수행하고 dry-run이면 롤백한다 — 미리보기가 DB를 바꾸지 않는다.
    거부 사유(합성 채널·검수 미달·학습 오염·미지 intent 등)는 그대로 문구로 돌려준다.
    채점(Arena 실행)은 여기서 하지 않는다 — 운영자가 별도로 돌린다(과금·장시간).
    입력은 원문 YAML(yaml_text) 또는 구조화(episodes 행 + 작성자/승인자) 둘 다 받는다.
    """
    if payload.yaml_text:
        doc, episodes = _parse_ktib_yaml(payload.yaml_text)
    else:
        doc, episodes = _episodes_from_rows(payload)
    is_benchmark = str(doc["dataset_split"]) == "BENCHMARK_HOLDOUT"
    sp = session.begin_nested()
    try:
        report = ingest_expert_episodes(
            session, episodes, config,
            origin_channel=str(doc["origin_channel"]),
            dataset_split=str(doc["dataset_split"]),
            authored_by=str(doc["authored_by"]),
            approved_by=str(doc["approved_by"]),
        )
        ktib_version: str | None = None
        eligible_total = 0
        if is_benchmark:  # 시험지는 BENCHMARK_HOLDOUT일 때만 동결(KTIB)한다
            ktib = build_ktib(session, config)
            ktib_version = ktib.ktib_version
            eligible_total = ktib.episode_count
        # 업로드 이력 한 줄 — 원문·요약을 savepoint 안에서 남긴다. dry-run이면 함께 롤백되고
        # 실제 등록(commit)만 이력에 남는다(§ 마이그레이션 0018). 요약은 배치 균일값(episodes[0]).
        first = episodes[0]
        session.add(KtibUpload(
            upload_id="UP_" + uuid.uuid4().hex[:12],
            authored_by=str(doc["authored_by"]), approved_by=str(doc["approved_by"]),
            reviewers=list(first.reviewers),
            origin_channel=str(doc["origin_channel"]), dataset_split=str(doc["dataset_split"]),
            inserted=report.inserted, skipped_duplicate=report.skipped_duplicate,
            agreement_rate=first.agreement_rate, agreement_kappa=first.agreement_kappa,
            ktib_version=ktib_version, eligible_total=eligible_total,
            source_document=payload.source_document or payload.yaml_text,
        ))
        session.flush()
    except (SyntheticChannelRejected, BenchmarkNeedsReview, TrainBenchmarkContamination,
            UnknownIngestIntent, EmptyKtib, ValueError) as exc:
        sp.rollback()
        return KtibUploadOut(ok=False, dry_run=not payload.commit, message=f"거부: {exc}")

    if payload.commit:
        sp.commit()  # savepoint 해제 → 실제 저장 (get_session이 최종 커밋)
        msg = (f"시험지 등록 완료 — 신규 {report.inserted}문항 "
               f"(중복 {report.skipped_duplicate} 제외)")
        if ktib_version:
            msg += (f", 시험지 버전 {ktib_version} · 총 {eligible_total}문항. "
                    "채점(시험 실행)은 운영자가 별도로 돌립니다.")
    else:
        sp.rollback()  # 미리보기 — 저장하지 않음
        msg = f"검증 통과 — 신규 {report.inserted}문항 (중복 {report.skipped_duplicate} 제외)"
        if ktib_version:
            msg += f", 등록하면 시험지 총 {eligible_total}문항. '등록 확정'을 눌러 저장하세요."

    return KtibUploadOut(
        ok=True, dry_run=not payload.commit,
        inserted=report.inserted, skipped_duplicate=report.skipped_duplicate,
        eligible_total=eligible_total, ktib_version=ktib_version, message=msg,
    )


# --- 시험지 업로드 이력 (기록 + 원문 보관 · 리스트 · 열람) ---


class KtibUploadRecordOut(BaseModel):
    """목록 한 줄 — 언제·누가·몇 문항·어떤 버전. 원문(source_document)은 상세에서만."""

    upload_id: str
    created_at: datetime | None
    authored_by: str
    approved_by: str
    reviewers: list[str]
    origin_channel: str
    dataset_split: str
    inserted: int
    skipped_duplicate: int
    agreement_rate: float | None
    agreement_kappa: float | None
    ktib_version: str | None
    eligible_total: int


class KtibUploadDetailOut(KtibUploadRecordOut):
    source_document: str | None  # 올린 원문 그대로 — 확인·회수용


class KtibUploadListOut(BaseModel):
    uploads: list[KtibUploadRecordOut]


def _upload_record(row: KtibUpload) -> KtibUploadRecordOut:
    return KtibUploadRecordOut(
        upload_id=row.upload_id, created_at=row.created_at,
        authored_by=row.authored_by, approved_by=row.approved_by,
        reviewers=list(row.reviewers or []),
        origin_channel=row.origin_channel, dataset_split=row.dataset_split,
        inserted=row.inserted, skipped_duplicate=row.skipped_duplicate,
        agreement_rate=row.agreement_rate, agreement_kappa=row.agreement_kappa,
        ktib_version=row.ktib_version, eligible_total=row.eligible_total,
    )


@router.get("/ktib/uploads", response_model=KtibUploadListOut)
def ktib_uploads(session: Session = Depends(get_session)) -> KtibUploadListOut:
    """업로드 이력 목록(최근 순). 등록(commit)된 것만 남는다 — 원문은 상세에서만(경량)."""
    rows = session.scalars(
        select(KtibUpload).order_by(KtibUpload.created_at.desc(), KtibUpload.upload_id.desc())
    ).all()
    return KtibUploadListOut(uploads=[_upload_record(r) for r in rows])


@router.get("/ktib/uploads/{upload_id}", response_model=KtibUploadDetailOut)
def ktib_upload_detail(
    upload_id: str, session: Session = Depends(get_session)
) -> KtibUploadDetailOut:
    """업로드 상세 — 올린 원문(source_document)까지. 목록에서 열어 확인·회수한다."""
    row = session.get(KtibUpload, upload_id)
    if row is None:
        raise HTTPException(status_code=404, detail="업로드 기록을 찾을 수 없어요")
    return KtibUploadDetailOut(**_upload_record(row).model_dump(), source_document=row.source_document)


# --- 애매 발화 인사이트 리포트 (투트랙 채택 B′, 2026-07-17 사용자 승인) ---
#
# 의견서 목표② "의도 분류 자체가 현장 인사이트": 어떤 의도가 자주 애매한가(clarify권 분포),
# 사람이 무엇을 고쳤나(교정 사례), 무엇이 분류 불능인가(atlas 큐). 읽기 전용 집계 — 어떤
# 테이블에도 쓰지 않는다(brightness 불가침은 자명). 출처 분리: 추론은 mode(gym=오픈 전
# 실험실, live/shadow=오픈 후 실사용), 교정은 origin_channel — 11월 이후 같은 리포트가 이어진다.

_RECENT_LIMIT = 50  # 목록 상한 — 통계가 아니라 '최근 사례 열람'용 (임계값 아님)


class AmbiguousIntentCount(BaseModel):
    intent_id: str
    count: int


class AmbiguitySource(BaseModel):
    source: str  # gym | live | shadow — 오픈 전/후 분리 축
    total: int
    ambiguous: int
    top_ambiguous_intents: list[AmbiguousIntentCount]


class AmbiguityCorrection(BaseModel):
    utterance: str
    chosen: str          # 사람이 고른 정답
    guessed: str | None  # 뇌의 당시 추측(evidence.context.brain_guess 원천)
    origin_channel: str
    created_at: datetime | None


class UnclassifiedUtterance(BaseModel):
    utterance: str
    status: str
    created_at: datetime | None


class AmbiguityReportOut(BaseModel):
    thresholds: dict[str, float]  # config 에코 — 판정 기준의 단일 원천 표시(규칙 1)
    sources: list[AmbiguitySource]
    corrections: list[AmbiguityCorrection]
    unclassified: list[UnclassifiedUtterance]


@router.get("/ambiguity-report", response_model=AmbiguityReportOut)
def ambiguity_report(
    session: Session = Depends(get_session),
    config: ExperimentsConfig = Depends(_get_experiments),
) -> AmbiguityReportOut:
    m = config.decision.clarify_margin
    c = config.decision.clarify_confidence

    def _is_ambiguous(row: InferenceLog) -> bool:
        # NULL(미산출)은 확신의 증거가 없다 — 애매로 센다(지어내지 않음)
        return (row.margin is None or row.margin < m) or (
            row.confidence is None or row.confidence < c
        )

    logs = session.scalars(select(InferenceLog)).all()
    by_source: dict[str, dict] = {}
    for row in logs:
        s = by_source.setdefault(row.mode, {"total": 0, "ambiguous": 0, "intents": {}})
        s["total"] += 1
        if _is_ambiguous(row):
            s["ambiguous"] += 1
            key = row.top_intent or "UNKNOWN"
            s["intents"][key] = s["intents"].get(key, 0) + 1
    sources = [
        AmbiguitySource(
            source=mode, total=s["total"], ambiguous=s["ambiguous"],
            top_ambiguous_intents=[
                AmbiguousIntentCount(intent_id=i, count=n)
                for i, n in sorted(s["intents"].items(), key=lambda kv: (-kv[1], kv[0]))
            ],
        )
        for mode, s in sorted(by_source.items())
    ]

    corr_rows = session.execute(
        select(Evidence, Episode)
        .join(Episode, Episode.episode_id == Evidence.episode_id)
        .where(Evidence.evidence_type == "HUMAN_CORRECTION")
        .order_by(Evidence.created_at.desc())
        .limit(_RECENT_LIMIT)
    ).all()
    corrections = [
        AmbiguityCorrection(
            utterance=ep.teacher_prompt,
            chosen=ev.intent_id,
            guessed=(ev.context or {}).get("brain_guess"),
            origin_channel=ep.origin_channel,
            created_at=ev.created_at,
        )
        for ev, ep in corr_rows
    ]

    queue = session.scalars(
        select(AtlasExpansionEntry)
        .order_by(AtlasExpansionEntry.created_at.desc())
        .limit(_RECENT_LIMIT)
    ).all()
    unclassified = [
        UnclassifiedUtterance(utterance=q.utterance, status=q.status, created_at=q.created_at)
        for q in queue
    ]

    return AmbiguityReportOut(
        thresholds={"clarify_margin": m, "clarify_confidence": c},
        sources=sources, corrections=corrections, unclassified=unclassified,
    )


# --- 시험지 2차 검수 대기열 — 웹 1~5 평점 검수(§3-3·§8-2) ---
#
# 흐름: A가 문항+1~5 제출(create) → 대기(AWAITING_SECOND) → 다른 컴퓨터의 B가 blind로 1~5
# 제출(review) → 서로 다른 2명 ∧ 가중 kappa ≥ 임계면 등록 가능 → register로 KTIB 동결.
# 스테이징은 episodes가 아니라 별도 표(§8-2 anti-anchoring). 등록만이 ingest_expert_episodes로
# episodes에 들어가 benchmark_integrity CHECK가 최종 방어(절대 규칙 2). rating_a는 B에게 숨긴다.


class CandidateItemIn(BaseModel):
    intent: str
    teacher_prompt: str
    rating: int  # 작성자(A) 1~5 평점


class CandidateCreateIn(BaseModel):
    reviewer: str
    items: list[CandidateItemIn]


class CandidateBatchSummary(BaseModel):
    batch_id: str
    created_by: str
    status: str
    item_count: int
    agreement_kappa: float | None = None
    accepted_count: int = 0       # 두 검수자 모두 min_item_rating↑
    registerable: bool = False
    ktib_version: str | None = None


class PendingItemOut(BaseModel):
    item_id: str
    intent: str
    teacher_prompt: str
    # rating_a는 절대 내보내지 않는다 — 2차 검수자 anti-anchoring(§8-2)


class PendingBatchOut(BaseModel):
    batch_id: str
    created_by: str               # A 이름은 보여도 됨(점수만 숨김)
    item_count: int
    items: list[PendingItemOut]


class CandidateListOut(BaseModel):
    pending: list[PendingBatchOut]        # 내가 만들지 않은 2차 검수 대기
    mine: list[CandidateBatchSummary]     # 내가 만든 배치 + 상태


class SecondRatingIn(BaseModel):
    item_id: str
    rating: int


class SecondReviewIn(BaseModel):
    reviewer: str
    ratings: list[SecondRatingIn]


class RegisterCandidateIn(BaseModel):
    reviewer: str          # 등록 실행자(approved_by에 기록)
    commit: bool = False


def _batch_summary(
    session: Session, batch: BenchmarkCandidateBatch, config: ExperimentsConfig
) -> CandidateBatchSummary:
    items = session.scalars(
        select(BenchmarkCandidateItem).where(
            BenchmarkCandidateItem.batch_id == batch.batch_id
        )
    ).all()
    floor = config.review.min_item_rating
    accepted = sum(
        1 for it in items
        if it.rating_a >= floor and it.rating_b is not None and it.rating_b >= floor
    )
    registerable = (
        batch.status == "SECOND_DONE"
        and batch.agreement_kappa is not None
        and batch.agreement_kappa >= config.review.min_agreement_kappa
        and accepted > 0
    )
    return CandidateBatchSummary(
        batch_id=batch.batch_id, created_by=batch.created_by, status=batch.status,
        item_count=len(items), agreement_kappa=batch.agreement_kappa,
        accepted_count=accepted, registerable=registerable, ktib_version=batch.ktib_version,
    )


@router.post("/ktib/candidates", response_model=CandidateBatchSummary)
def create_candidate_batch(
    payload: CandidateCreateIn,
    session: Session = Depends(get_session),
    config: ExperimentsConfig = Depends(_get_experiments),
) -> CandidateBatchSummary:
    """A(작성자)가 문항+1~5 평점 제출 → 2차 검수 대기 배치 생성."""
    reviewer = canonical_reviewer(payload.reviewer)
    if not reviewer:
        raise HTTPException(status_code=400, detail="검수자 이름을 입력해주세요")
    if not payload.items:
        raise HTTPException(status_code=400, detail="문항이 비어 있습니다")
    real = {i.intent_id for i in load_ontology().intents if i.intent_id != UNKNOWN_INTENT_ID}
    seen: set[str] = set()
    rows: list[tuple[str, str, int]] = []
    for i, it in enumerate(payload.items, 1):
        prompt = (it.teacher_prompt or "").strip()
        intent = (it.intent or "").strip()
        if not prompt or not intent:
            raise HTTPException(status_code=400, detail=f"{i}번째 문항의 질문/의도를 채워주세요")
        if intent not in real:
            raise HTTPException(status_code=422, detail=f"온톨로지에 없는 의도입니다: {intent}")
        if not (1 <= it.rating <= 5):
            raise HTTPException(status_code=422, detail=f"{i}번째 문항 점수는 1~5여야 합니다")
        if prompt in seen:
            raise HTTPException(
                status_code=409, detail=f"배치 안에 같은 질문이 중복됩니다: {prompt}"
            )
        seen.add(prompt)
        # 학습 오염 가드(§8-2) — 이미 학습 분할에 있는 발화는 시험 후보가 될 수 없다(등록 시 재확인)
        clash = session.scalars(
            select(Episode.episode_id).where(
                Episode.teacher_prompt == prompt,
                Episode.dataset_split != "BENCHMARK_HOLDOUT",
            ).limit(1)
        ).first()
        if clash is not None:
            raise HTTPException(
                status_code=409, detail=f"이미 학습 문항에 있는 질문입니다: {prompt}"
            )
        rows.append((intent, prompt, it.rating))

    batch = BenchmarkCandidateBatch(
        batch_id="BC_" + uuid.uuid4().hex[:12], created_by=reviewer, status="AWAITING_SECOND"
    )
    session.add(batch)
    for intent, prompt, rating in rows:
        session.add(BenchmarkCandidateItem(
            item_id="BCI_" + uuid.uuid4().hex[:12], batch_id=batch.batch_id,
            intent_id=intent, teacher_prompt=prompt, rating_a=rating,
        ))
    session.flush()
    return _batch_summary(session, batch, config)


@router.get("/ktib/candidates", response_model=CandidateListOut)
def list_candidates(
    reviewer: str = "",
    session: Session = Depends(get_session),
    config: ExperimentsConfig = Depends(_get_experiments),
) -> CandidateListOut:
    """검수자 기준 목록: pending(내가 만들지 않은 대기, blind) + mine(내가 만든 배치·상태)."""
    me = canonical_reviewer(reviewer)
    pending: list[PendingBatchOut] = []
    mine: list[CandidateBatchSummary] = []
    if not me:
        return CandidateListOut(pending=pending, mine=mine)

    pend_batches = session.scalars(
        select(BenchmarkCandidateBatch).where(
            BenchmarkCandidateBatch.status == "AWAITING_SECOND",
            BenchmarkCandidateBatch.created_by != me,
        ).order_by(BenchmarkCandidateBatch.created_at)
    ).all()
    for b in pend_batches:
        items = session.scalars(
            select(BenchmarkCandidateItem).where(
                BenchmarkCandidateItem.batch_id == b.batch_id
            )
        ).all()
        pending.append(PendingBatchOut(
            batch_id=b.batch_id, created_by=b.created_by, item_count=len(items),
            # rating_a 미포함 — anti-anchoring
            items=[PendingItemOut(item_id=it.item_id, intent=it.intent_id,
                                  teacher_prompt=it.teacher_prompt) for it in items],
        ))

    my_batches = session.scalars(
        select(BenchmarkCandidateBatch).where(
            BenchmarkCandidateBatch.created_by == me
        ).order_by(BenchmarkCandidateBatch.created_at)
    ).all()
    mine = [_batch_summary(session, b, config) for b in my_batches]
    return CandidateListOut(pending=pending, mine=mine)


@router.post("/ktib/candidates/{batch_id}/review", response_model=CandidateBatchSummary)
def submit_second_review(
    batch_id: str,
    payload: SecondReviewIn,
    session: Session = Depends(get_session),
    config: ExperimentsConfig = Depends(_get_experiments),
) -> CandidateBatchSummary:
    """B(2차 검수자)가 blind로 1~5 평점 제출 → 가중 kappa 계산·기록."""
    batch = session.get(BenchmarkCandidateBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="검수 대상을 찾을 수 없습니다")
    reviewer = canonical_reviewer(payload.reviewer)
    if not reviewer:
        raise HTTPException(status_code=400, detail="검수자 이름을 입력해주세요")
    if reviewer == batch.created_by:
        raise HTTPException(
            status_code=409,
            detail="1차 검수자와 다른 사람이어야 해요 (같은 이름·대소문자만 다른 건 한 사람)",
        )
    if batch.status != "AWAITING_SECOND":
        # 멱등: 이미 2차가 끝난 배치에 다시 제출하면 중복 방지
        raise HTTPException(status_code=409, detail="이미 2차 검수가 끝난 시험지입니다")

    ordered = session.scalars(
        select(BenchmarkCandidateItem).where(
            BenchmarkCandidateItem.batch_id == batch_id
        ).order_by(BenchmarkCandidateItem.item_id)
    ).all()
    by_id = {it.item_id: it for it in ordered}
    ratings = {r.item_id: r.rating for r in payload.ratings}
    if set(ratings) != set(by_id):
        raise HTTPException(status_code=400, detail="모든 문항을 평가해주세요")
    for item_id, rating in ratings.items():
        if not (1 <= rating <= 5):
            raise HTTPException(status_code=422, detail="점수는 1~5여야 합니다")
        by_id[item_id].rating_b = rating

    # 가중 kappa(순서형 1~5) — 전부 동일 판정이면 None(변별 불가, 지어내지 않음)
    kappa = weighted_cohens_kappa(
        [it.rating_a for it in ordered], [by_id[it.item_id].rating_b for it in ordered]
    )
    batch.reviewer_second = reviewer
    batch.agreement_kappa = kappa
    batch.status = "SECOND_DONE"
    session.flush()
    return _batch_summary(session, batch, config)


@router.post("/ktib/candidates/{batch_id}/register", response_model=KtibUploadOut)
def register_candidate_batch(
    batch_id: str,
    payload: RegisterCandidateIn,
    session: Session = Depends(get_session),
    config: ExperimentsConfig = Depends(_get_experiments),
) -> KtibUploadOut:
    """2차 검수 완료 배치를 시험지(KTIB)로 등록. commit=False=검증(dry-run)/True=적재·동결.

    accepted(두 검수자 모두 min_item_rating↑) 문항만 ingest_expert_episodes로 등록 →
    §3-3 게이트(2명·kappa·비합성·오염)와 benchmark_integrity CHECK가 최종 강제(우회 없음).
    """
    batch = session.get(BenchmarkCandidateBatch, batch_id)
    if batch is None:
        raise HTTPException(status_code=404, detail="등록 대상을 찾을 수 없습니다")
    if batch.status == "REGISTERED":
        raise HTTPException(status_code=409, detail="이미 등록된 시험지입니다")
    if batch.status != "SECOND_DONE":
        raise HTTPException(status_code=409, detail="아직 2차 검수가 끝나지 않았습니다")
    if batch.reviewer_second is None or batch.reviewer_second == batch.created_by:
        raise HTTPException(status_code=409, detail="서로 다른 두 검수자가 필요합니다")
    if (batch.agreement_kappa is None
            or batch.agreement_kappa < config.review.min_agreement_kappa):
        raise HTTPException(
            status_code=409,
            detail="검수 일치도가 기준에 못 미쳐 등록할 수 없습니다 (2차 검수를 다시 확인해주세요)",
        )

    floor = config.review.min_item_rating
    items = session.scalars(
        select(BenchmarkCandidateItem).where(
            BenchmarkCandidateItem.batch_id == batch_id
        )
    ).all()
    accepted = [
        it for it in items
        if it.rating_a >= floor and it.rating_b is not None and it.rating_b >= floor
    ]
    if not accepted:
        raise HTTPException(
            status_code=409, detail="두 검수자가 모두 높게 평가한 문항이 없어 등록할 수 없습니다"
        )
    approver = canonical_reviewer(payload.reviewer) or batch.reviewer_second
    episodes = [
        ExpertEpisode(
            episode_id="EP_" + hashlib.sha1(
                f"{it.intent_id}\x1f{it.teacher_prompt}".encode()
            ).hexdigest()[:12],
            teacher_prompt=it.teacher_prompt, intent=it.intent_id, lang="ko",
            reviewers=(batch.created_by, batch.reviewer_second),
            agreement_kappa=batch.agreement_kappa,
        )
        for it in accepted
    ]

    sp = session.begin_nested()
    try:
        report = ingest_expert_episodes(
            session, episodes, config,
            origin_channel="EXPERT_AUTHORED", dataset_split="BENCHMARK_HOLDOUT",
            authored_by=batch.created_by, approved_by=approver,
        )
        ktib = build_ktib(session, config)
    except (SyntheticChannelRejected, BenchmarkNeedsReview, TrainBenchmarkContamination,
            UnknownIngestIntent, EmptyKtib, ValueError) as exc:
        sp.rollback()
        return KtibUploadOut(ok=False, dry_run=not payload.commit, message=f"거부: {exc}")

    if payload.commit:
        batch.status = "REGISTERED"
        batch.ktib_version = ktib.ktib_version
        session.flush()
        sp.commit()
        msg = (f"등록 완료 — 신규 {report.inserted}문항 (중복 {report.skipped_duplicate} 제외), "
               f"시험지 버전 {ktib.ktib_version} · 총 {ktib.episode_count}문항. "
               "채점(시험 실행)은 운영자가 별도로 돌립니다.")
    else:
        sp.rollback()
        msg = (f"검증 통과 — 등록 가능 {report.inserted}문항 "
               f"(중복 {report.skipped_duplicate} 제외), "
               f"등록하면 시험지 총 {ktib.episode_count}문항. '등록'을 눌러 저장하세요.")

    return KtibUploadOut(
        ok=True, dry_run=not payload.commit,
        inserted=report.inserted, skipped_duplicate=report.skipped_duplicate,
        eligible_total=ktib.episode_count,
        ktib_version=(ktib.ktib_version if payload.commit else None), message=msg,
    )
