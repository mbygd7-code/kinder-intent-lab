"""Zero-shot 베이스라인 러너 + 리포트 (§8-2 베이스라인 규칙, T5.2).

"첫 KTIB 완성 직후 범용 LLM zero-shot 베이스라인을 측정하고, 그 위에서 80% 목표의 난이도를
재확정한다. **목표 수치를 베이스라인보다 먼저 확정하지 않는다.**" (§8-2)

zero-shot = 이 시스템이 만든 어떤 것도 쓰지 않는다:
- retrieval·exemplar 없음 (훈련 산출물)
- persona/domain prior 없음 (§5-5의 곱셈 단계 자체를 건너뛴다)
- 입력은 온톨로지 intent 카탈로그(id + 정의) + 동결된 KTIB 스냅샷(발화·workspace)뿐

기록은 `arena_runs(run_type='zero_shot_baseline')`. run_type 분리 덕에 이 run은 3D 뇌의
밝기·ktib_global로 절대 새지 않는다(절대 규칙 3 — 밝기는 brain run만이 만든다).

리포트는 노드/도메인별 분해와 **목표 재확정 제안서**를 담는다. 제안서는 측정값에서 유도한
사실(절대 격차·상대 오류 감소율)만 제시하고 새 목표 수치를 임의로 확정하지 않는다 —
확정은 사람 승인 + docs Change Log 소관이다(CLAUDE.md 작업 방식 5).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass

from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.arena.ktib import EmptyKtib, latest_ktib, load_items
from app.arena.metrics import Prediction, compute_metrics, confusion_matrix
from app.arena.prompts import load_prompt
from app.brain.priors import current_state_version
from app.core.config import ExperimentsConfig
from app.core.ontology import UNKNOWN_INTENT_ID, load_ontology
from app.foundry.agents.runner import AgentOutputError, render_agent_prompt, run_json_agent
from app.llm.client import LLMClient
from app.models.arena import (
    NO_PERSONA_STATE,
    RUN_TYPE_BASELINE,
    ArenaRun,
    KtibItem,
    KtibVersion,
)

_ZERO_SHOT_PROMPT = load_prompt("zero_shot")


class ZeroShotOutput(BaseModel):
    intent_id: str
    confidence: float = Field(ge=0, le=1)
    rationale: str = ""


@dataclass
class BaselineResult:
    run: ArenaRun
    predictions: list[Prediction]
    invalid_predictions: int   # 카탈로그 밖 id를 낸 횟수 (계약 위반 — abstain으로 처리)
    abstained: int             # UNKNOWN 또는 계약 위반 → 어떤 intent도 고르지 못함


def intent_catalog() -> list[dict]:
    """온톨로지 intent id + 정의. UNKNOWN 포함 — '해당 없음'을 고를 수 있어야 한다(§5-8)."""
    return [
        {"intent_id": i.intent_id, "domain": i.domain, "definition": i.definition}
        for i in load_ontology().intents
    ]


def _item_context(item: KtibItem, catalog: list[dict]) -> dict:
    """동결 스냅샷만 넣는다 — 훈련 메타데이터·정답은 절대 넣지 않는다(절대 규칙 5)."""
    return {
        "intent_catalog": catalog,
        "utterance": item.teacher_prompt,
        "lang": item.lang,
        "workspace": item.workspace_snapshot,  # None이면 화면 컨텍스트 없음(지어내지 않음)
    }


def predict_one(
    client: LLMClient, model: str, item: KtibItem, catalog: list[dict], valid_ids: set[str]
) -> tuple[Prediction, bool]:
    """아이템 1건 zero-shot 예측. (Prediction, 계약위반여부) 반환.

    - 카탈로그 밖 id → abstain 처리 + 위반으로 집계 (LLM이 새 intent를 만들지 못한다)
    - UNKNOWN → abstain. '어느 intent와도 혼동한 것'이 아니므로 confusion pair를 만들지 않는다
    - JSON/스키마 위반 → abstain (러너 전체를 죽이지 않되 조용히 정답 처리하지도 않는다)
    """
    prompt = render_agent_prompt(_ZERO_SHOT_PROMPT, _item_context(item, catalog))
    try:
        out = run_json_agent(client, prompt, model, ZeroShotOutput)
    except AgentOutputError:
        return Prediction(item.episode_id, item.gold_intent, None, 0.0), True

    if out.intent_id not in valid_ids:
        return Prediction(item.episode_id, item.gold_intent, None, 0.0), True
    if out.intent_id == UNKNOWN_INTENT_ID:
        return Prediction(item.episode_id, item.gold_intent, None, out.confidence), False
    return Prediction(item.episode_id, item.gold_intent, out.intent_id, out.confidence), False


def run_zero_shot_baseline(
    session: Session,
    client: LLMClient,
    config: ExperimentsConfig,
    *,
    model: str,
    ktib: KtibVersion | None = None,
) -> BaselineResult:
    """KTIB 전체를 zero-shot으로 채점하고 arena_runs에 베이스라인 run을 기록한다."""
    ktib = ktib or latest_ktib(session)
    if ktib is None:
        raise EmptyKtib("발급된 ktib_version이 없다 — 먼저 KTIB를 구성하라 (§8-2)")
    items = load_items(session, ktib.ktib_version)
    if not items:
        raise EmptyKtib(f"{ktib.ktib_version}에 아이템이 없다")

    catalog = intent_catalog()
    valid_ids = {c["intent_id"] for c in catalog}
    regions = {i.intent_id: i.domain for i in load_ontology().intents if i.domain}

    predictions: list[Prediction] = []
    invalid = 0
    for item in items:  # load_items가 episode_id 순 — 결정론
        pred, violated = predict_one(client, model, item, catalog, valid_ids)
        predictions.append(pred)
        invalid += int(violated)

    metrics = compute_metrics(predictions, regions, ece_bins=config.arena.ece_bins)
    metrics["baseline_model"] = model
    metrics["invalid_prediction_count"] = invalid

    run = ArenaRun(
        run_id="AR_" + uuid.uuid4().hex[:12],
        model_version=f"zero_shot:{model}",
        ontology_version=load_ontology().version,
        persona_state_version=current_state_version(session) or NO_PERSONA_STATE,
        extractor_versions=dict(ktib.extractor_versions),  # KTIB가 동결한 지문 그대로
        ktib_version=ktib.ktib_version,
        run_type=RUN_TYPE_BASELINE,
        metrics=metrics,
        confusion_matrix=confusion_matrix(
            predictions, confirm_min=config.arena.confusion_confirm_min
        ),
    )
    session.add(run)
    session.flush()
    return BaselineResult(
        run=run,
        predictions=predictions,
        invalid_predictions=invalid,
        abstained=sum(p.predicted_intent is None for p in predictions),
    )


# --- 리포트 (AC: 노드/도메인별 분해 포함) ---


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


def _target_reframing(baseline: float | None, target: float) -> list[str]:
    """§8-2: 베이스라인 '위에서' 목표의 난이도를 재확정한다.

    새 목표 수치를 여기서 정하지 않는다 — 측정값에서 유도되는 사실만 제시한다.
    """
    if baseline is None:
        return ["- 베이스라인 미측정 — 목표 난이도를 논할 수 없다."]
    gap_pp = (target - baseline) * 100
    lines = [
        f"- zero-shot 베이스라인: **{_pct(baseline)}**",
        f"- 현행 목표(`config.arena.first_intent_accuracy_target`): **{_pct(target)}**",
        f"- 절대 격차: **{gap_pp:+.1f}pp**",
    ]
    if baseline < 1.0:
        reduction = (target - baseline) / (1.0 - baseline)
        lines.append(
            f"- 목표 도달에 필요한 **상대 오류 감소율**: {reduction * 100:.1f}% "
            f"(잔여 오류 {_pct(1 - baseline)} 중)"
        )
    if baseline >= target:
        lines.append(
            "- ⚠️ 베이스라인이 이미 목표를 넘었다 — 목표가 너무 낮게 잡혔다는 뜻이므로 "
            "**상향 재확정이 필요**하다(§8-2)."
        )
    return lines


def baseline_report(result: BaselineResult, config: ExperimentsConfig) -> str:
    """베이스라인 리포트(markdown) — 노드/도메인별 분해 + 목표 재확정 제안서."""
    run, metrics = result.run, result.run.metrics
    target = config.arena.first_intent_accuracy_target
    accuracy = metrics["first_intent_accuracy"]

    lines = [
        f"# KTIB Zero-shot 베이스라인 — {run.ktib_version}",
        "",
        "> §8-2 베이스라인 규칙: 목표 수치를 베이스라인보다 먼저 확정하지 않는다.",
        "> 이 문서는 **측정 결과 + 제안서**다. 확정은 사람 승인 + docs Change Log 소관.",
        "",
        "## Run 메타데이터 (replay 무결성 4종)",
        "",
        "| 축 | 값 |",
        "|---|---|",
        f"| run_id | `{run.run_id}` |",
        f"| run_type | `{run.run_type}` (밝기 원천 아님) |",
        f"| model_version | `{run.model_version}` |",
        f"| ontology_version | `{run.ontology_version}` |",
        f"| persona_state_version | `{run.persona_state_version}` |",
        f"| extractor_versions | `{run.extractor_versions}` |",
        f"| ktib_version | `{run.ktib_version}` |",
        "",
        "## 전역 지표",
        "",
        f"- First Intent Accuracy: **{_pct(accuracy)}** "
        f"({metrics['correct']}/{metrics['item_count']})",
        f"- Calibration ECE: **{metrics['ece'] if metrics['ece'] is not None else '—'}**",
        f"- Abstain(UNKNOWN·계약위반): {metrics['abstain_count']}건 "
        f"(그중 카탈로그 밖 id {result.invalid_predictions}건)",
        "",
        "## 도메인(region)별 분해",
        "",
        "| region | n | 정확도 |",
        "|---|---:|---:|",
    ]
    for region, m in metrics["by_region"].items():
        lines.append(f"| {region} | {m['n']} | {_pct(m['accuracy'])} |")

    lines += [
        "",
        "## 노드(intent)별 분해 — 정확도 오름차순",
        "",
        "| intent | n | 정확도 | ECE |",
        "|---|---:|---:|---:|",
    ]
    ranked = sorted(
        metrics["by_node"].items(), key=lambda kv: (kv[1]["accuracy"] or 0.0, kv[0])
    )
    for intent, m in ranked:
        ece = "—" if m["ece"] is None else f"{m['ece']:.4f}"
        lines.append(f"| `{intent}` | {m['n']} | {_pct(m['accuracy'])} | {ece} |")

    matrix = run.confusion_matrix or []
    lines += ["", "## 상위 방향성 혼동 쌍 (P(예측=B | 정답=A))", ""]
    if matrix:
        lines += ["| 정답 A | 예측 B | count | rate |", "|---|---|---:|---:|"]
        lines += [
            f"| `{r['from_true']}` | `{r['to_predicted']}` | {r['count']} "
            f"| {_pct(r['confusion_rate'])} |"
            for r in matrix[:10]
        ]
    else:
        lines.append("혼동 쌍 없음.")

    lines += [
        "",
        "## 제안서 — 목표·Stage 게이트 재확정 (§8-2 · §7-6)",
        "",
        *_target_reframing(accuracy, target),
        "",
        "### 사람 승인이 필요한 결정",
        "",
        "1. `config.arena.first_intent_accuracy_target` 유지 or 조정 "
        "(조정 시 설계 문서 §10-2의 80% 표기도 함께 갱신 — Change Log 항목 필수)",
        "2. §7-6 Stage 게이트(region reliability 50%/70%, global 80%)를 이 베이스라인 위에서 "
        "재확정할지 여부",
        "3. 위 노드별 분해에서 정확도 하위 노드 = Phase 5 훈련 사이클의 첫 진입점(§6-3 ①)",
        "",
        "> 이 러너는 어떤 수치도 자동 변경하지 않는다. 위 항목은 제안일 뿐이다.",
        "",
    ]
    return "\n".join(lines)
