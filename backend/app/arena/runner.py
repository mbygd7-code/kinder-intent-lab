"""Arena 러너 — KTIB 위에서 Seed Brain을 채점한다 (§8-2·§5-6, T5.3).

- 추론은 `brain.inference.infer_core`를 그대로 쓴다 — 벤치마크가 다른 코드 경로로 도는
  귀속 오류를 구조적으로 없앤다.
- 입력은 동결된 KTIB 스냅샷(발화·workspace)뿐. **gold intent는 추론 입력에 넣지 않는다**
  (절대 규칙 5). teacher_ref는 중립 합성 ref라 개인 prior가 벤치마크를 조건화하지 못한다.
- 산출: 노드/region/global heldout accuracy · 방향성 confusion matrix · calibration(ECE),
  그리고 **replay 무결성 4버전**(model / ontology / persona_state / extractor).
- 같은 입력 + 같은 4버전 → 같은 metrics·confusion_matrix (run_id·created_at만 다르다).

confusion matrix는 `confusion_edges`를 갱신한다: count ≥ `config.arena.confusion_confirm_min`인
pair는 `state='confirmed'`(§5-6 상태 기계의 마지막 단계, origin=ARENA_MATRIX).

**밝기(heldout_accuracy)는 여기서 쓰지 않는다.** 그것은 promote 판정을 통과한 뒤 반영 잡
(arena.reflect)이 한다 — 훈련이 아니라 *승격*이 밝기를 켠다(§6-7 [9]).
"""
from __future__ import annotations

import hashlib
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.arena.ktib import EmptyKtib, latest_ktib, load_items
from app.arena.metrics import Prediction, compute_metrics, confusion_matrix
from app.brain.inference import CoreSignals, EmbedFn, infer_core
from app.brain.priors import current_state_version
from app.brain.promote import ArenaOutcome
from app.brain.version_gate import SEED_VERSION
from app.core.config import ExperimentsConfig
from app.core.ontology import load_ontology
from app.llm.client import LLMClient
from app.models.arena import (
    NO_PERSONA_STATE,
    RUN_TYPE_BRAIN,
    ArenaRun,
    KtibItem,
    KtibVersion,
)
from app.models.brain import BrainVersion, ConfusionEdge

# 벤치마크는 특정 교사의 개인 prior로 조건화되지 않는다 — prior tier는 neutral로 떨어진다(§5-3).
ARENA_TEACHER_REF = "arena:neutral"
ARENA_MODE = "arena"          # inference_log의 관측 라벨 (InferRequest mode enum 아님)
EDGE_ORIGIN = "ARENA_MATRIX"  # §5-6 origin


class KtibAxisMismatch(Exception):
    """서로 다른 ktib_version의 점수를 비교하려 함 — 같은 축에 그리지 않는다 (§8-2)."""


@dataclass
class ArenaRunResult:
    run: ArenaRun
    predictions: list[Prediction]


def core_signals_from_item(item: KtibItem) -> CoreSignals:
    """동결 스냅샷 → Core 신호. gold_intent·episode_id는 넣지 않는다(절대 규칙 5)."""
    ws = item.workspace_snapshot or {}
    summary = {k: ws[k] for k in ("objects_summary", "selection", "visual_semantics") if k in ws}
    return CoreSignals(
        prompt_text=item.teacher_prompt,
        lang=item.lang,
        surface_type=ws.get("surface_type", "unknown"),
        selection=[],  # 스냅샷은 객체 id를 보존하지 않는다 — 지어내지 않는다
        workspace_summary=summary,
        recent_actions=list(ws.get("recent_actions", []) or []),
        teacher_ref=ARENA_TEACHER_REF,
    )


def run_arena(
    session: Session,
    client: LLMClient,
    embed_fn: EmbedFn,
    config: ExperimentsConfig,
    *,
    model_version: str,
    ktib: KtibVersion | None = None,
    scorer_model: str = "brain",
) -> ArenaRunResult:
    """KTIB 전체를 Seed Brain으로 채점하고 arena_runs(run_type='brain')에 기록한다."""
    ktib = ktib or latest_ktib(session)
    if ktib is None:
        raise EmptyKtib("발급된 ktib_version이 없다 — 먼저 KTIB를 구성하라 (§8-2)")
    items = load_items(session, ktib.ktib_version)  # episode_id 순 — 재현성의 전제
    if not items:
        raise EmptyKtib(f"{ktib.ktib_version}에 아이템이 없다")

    ontology = load_ontology()
    regions = {i.intent_id: i.domain for i in ontology.intents if i.domain}

    predictions: list[Prediction] = []
    for item in items:
        result = infer_core(
            session,
            core_signals_from_item(item),
            client,
            embed_fn,
            config,
            request_id=f"{ktib.ktib_version}:{item.episode_id}",
            mode=ARENA_MODE,
            cluster_id=None,  # 벤치마크는 persona 클러스터로 조건화하지 않는다
            model=scorer_model,
        )
        predictions.append(Prediction(
            episode_id=item.episode_id,
            gold_intent=item.gold_intent,
            predicted_intent=result.top_intent,
            confidence=result.confidence,
        ))

    metrics = compute_metrics(predictions, regions, ece_bins=config.arena.ece_bins)
    run = ArenaRun(
        run_id="AR_" + uuid.uuid4().hex[:12],
        model_version=model_version,
        ontology_version=ontology.version,
        persona_state_version=current_state_version(session) or NO_PERSONA_STATE,
        extractor_versions=dict(ktib.extractor_versions),  # KTIB가 동결한 지문 그대로
        ktib_version=ktib.ktib_version,
        run_type=RUN_TYPE_BRAIN,
        metrics=metrics,
        confusion_matrix=confusion_matrix(
            predictions, confirm_min=config.arena.confusion_confirm_min
        ),
    )
    session.add(run)
    session.flush()
    return ArenaRunResult(run=run, predictions=predictions)


# --- confusion_edges 갱신 (§5-6 상태 기계의 confirmed 단계) ---


def _edge_id(from_true: str, to_predicted: str) -> str:
    """(from,to)에서 결정론적으로 유도 — 같은 pair를 재실행해도 같은 id."""
    digest = hashlib.sha1(f"{from_true}->{to_predicted}".encode()).hexdigest()
    return f"CE_{digest[:10]}"


def apply_confusion_edges(session: Session, run: ArenaRun) -> int:
    """arena 오답 매트릭스로 confusion_edges를 갱신한다. 갱신·생성된 edge 수를 반환.

    - confirmed=True pair → state='confirmed' (§5-6: Arena 오답 매트릭스 검증)
    - 측정은 됐으나 임계 미달인 pair → rate만 갱신, state는 낮추지 않는다(단조)
    - 이번 run에서 **정답 A가 측정됐는데** A→B 오답이 하나도 없던 기존 edge → rate 0.0
      (edge flicker 소등). A가 아예 측정되지 않았다면 손대지 않는다 — 미측정과 0은 다르다.
    """
    measured_true = set((run.metrics or {}).get("by_node", {}))
    matrix = run.confusion_matrix or []
    now = datetime.now(UTC)

    existing = {
        (e.from_true, e.to_predicted): e for e in session.scalars(select(ConfusionEdge))
    }
    touched = 0

    for row in matrix:
        key = (row["from_true"], row["to_predicted"])
        edge = existing.get(key)
        if edge is None:
            edge = ConfusionEdge(
                edge_id=_edge_id(*key), from_true=key[0], to_predicted=key[1],
                state="hypothesized", origin=EDGE_ORIGIN, evidence_runs=[],
            )
            session.add(edge)
            existing[key] = edge
        edge.confusion_rate = row["confusion_rate"]   # edge flicker의 원천(§7-5)
        if row["confirmed"]:
            edge.state = "confirmed"                  # §5-6 마지막 단계
            edge.origin = EDGE_ORIGIN
        edge.evidence_runs = sorted({*(edge.evidence_runs or []), run.run_id})
        edge.last_updated = now
        touched += 1

    seen = {(r["from_true"], r["to_predicted"]) for r in matrix}
    for key, edge in existing.items():
        if key in seen or key[0] not in measured_true:
            continue  # 이번 run에서 정답 A가 측정되지 않았으면 판단하지 않는다
        edge.confusion_rate = 0.0                     # 혼동이 사라졌다 — flicker 소등
        edge.evidence_runs = sorted({*(edge.evidence_runs or []), run.run_id})
        edge.last_updated = now
        touched += 1

    session.flush()
    return touched


# --- promote 판정 입력 만들기 (§6-6) ---


def baseline_run(session: Session, base_version: str, ktib_version: str) -> ArenaRun | None:
    """candidate의 base(현행 promote 버전)가 **같은 KTIB에서** 받은 점수 = 비교 기준.

    - seed 상태: model_version=seed-v0로 돌린 brain run 중 최신
    - promote된 base: 그 버전을 승격시킨 run(brain_versions.arena_result.run_id)
    - 기준 run의 ktib_version이 다르면 KtibAxisMismatch — 신·구 벤치마크를 같은 축에 그리지 않는다
    """
    if base_version == SEED_VERSION:
        return session.scalar(
            select(ArenaRun)
            .where(
                ArenaRun.model_version == SEED_VERSION,
                ArenaRun.run_type == RUN_TYPE_BRAIN,
                ArenaRun.ktib_version == ktib_version,
            )
            .order_by(ArenaRun.created_at.desc())
        )

    base = session.get(BrainVersion, base_version)
    run_id = ((base.arena_result or {}).get("run_id") if base else None)
    if not run_id:
        return None
    run = session.get(ArenaRun, run_id)
    if run is None:
        return None
    if run.ktib_version != ktib_version:
        raise KtibAxisMismatch(
            f"base {base_version}의 기준 run({run.run_id})은 {run.ktib_version}에서 측정됐다 — "
            f"현재 {ktib_version}과 같은 축에 그릴 수 없다. base를 새 KTIB로 재측정하라 (§8-2)"
        )
    return run


def _acc(metrics: dict, section: str, key: str) -> float | None:
    entry = (metrics.get(section) or {}).get(key)
    return None if entry is None else entry.get("accuracy")


def build_outcome(
    run: ArenaRun, base: ArenaRun | None, config: ExperimentsConfig
) -> ArenaOutcome:
    """arena run + 기준 run → promote 판정 입력(§6-6).

    기준 run이 없으면 global_delta=0.0 — '상승이 입증되지 않음'이므로 promote는 막힌다.
    없는 기준을 0%로 가정해 상승을 지어내지 않는다.
    """
    metrics = run.metrics or {}
    base_metrics = (base.metrics or {}) if base is not None else {}

    cur_global = metrics.get("first_intent_accuracy")
    base_global = base_metrics.get("first_intent_accuracy")
    global_delta = (
        0.0 if (base is None or cur_global is None or base_global is None)
        else round((cur_global - base_global) * 100, 4)  # pp
    )

    regressions = [
        region
        for region in (metrics.get("by_region") or {})
        if (b := _acc(base_metrics, "by_region", region)) is not None
        and (c := _acc(metrics, "by_region", region)) is not None
        and c < b
    ]
    critical_worse = [
        intent
        for intent in config.arena.critical_intents
        if (b := _acc(base_metrics, "by_node", intent)) is not None
        and (c := _acc(metrics, "by_node", intent)) is not None
        and c < b
    ]

    by_node = metrics.get("by_node") or {}
    return ArenaOutcome(
        run_id=run.run_id,
        global_delta=global_delta,
        region_regressions=sorted(regressions),
        critical_worse=sorted(critical_worse),
        node_heldout={
            intent: m["accuracy"] for intent, m in by_node.items() if m["accuracy"] is not None
        },
        node_ece={intent: m["ece"] for intent, m in by_node.items() if m["ece"] is not None},
    )
