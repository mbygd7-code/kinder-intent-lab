"""Arena → Observatory 반영 잡 (§7-5·§8-2, T5.4).

**Arena 결과만이** 3D 뇌의 brightness와 edge flicker를 바꾼다(절대 규칙 3 / 원칙 8):

| 시각 요소 | 저장 위치 | 갱신 시점 |
|---|---|---|
| Node Brightness | `brain_nodes.heldout_accuracy` | 이 잡 (아래 규칙) |
| Edge Flicker | `confusion_edges.confusion_rate` | 이 잡 — 모든 brain run |
| Pending Ring | `brain_nodes.pending_evaluation` | 훈련이 점등, **promote만** 소등 (§6-7 [6]→[9]) |

## 밝기는 "현행 뇌"의 heldout이다

`arena_runs.model_version`이 어떤 뇌를 쟀는지 말해준다:

- **현행 base 버전을 잰 run**(주간 정기 실행) → 그 숫자가 곧 지금 뇌의 밝기다 → 반영한다.
  단 **pending 링은 끄지 않는다** — 이 run은 candidate에 담긴 훈련을 검증한 것이 아니다.
- **candidate를 잰 run** → 그 숫자는 아직 뇌의 것이 아니다.
  - promote → `promote.resolve_candidate`가 밝기를 켜고 링을 끄고 Resonance를 발동한다(§6-7 [9]).
  - reject → 숫자는 폐기된다. 밝기·링 불변(§6-6).
- **zero-shot 베이스라인 run** → 3D 반영 대상이 아니다(§8-2). 여기서 loud-fail한다.

훈련(gym)이 밝기를 올리는 지름길은 어느 경로에도 없다 —
§6-7 "[4]→[6]에서 밝기가 바로 오르는 지름길은 구조적으로 존재하지 않는다".
강제 수단은 `models.guards.arena_brightness_write` 컨텍스트 + flush 리스너다.
"""
from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from app.arena.runner import apply_confusion_edges, build_outcome
from app.brain.promote import apply_arena_brightness
from app.brain.version_gate import SEED_VERSION, current_base
from app.core.config import ExperimentsConfig
from app.models.arena import RUN_TYPE_BRAIN, ArenaRun


class BaselineRunNotReflectable(Exception):
    """zero-shot 베이스라인 run을 3D 뇌에 반영하려 함 — 밝기의 원천은 brain run뿐 (§8-2)."""


@dataclass
class ReflectResult:
    run_id: str
    edges_touched: int
    nodes_brightened: int
    resonance: bool  # promote 순간의 Full Brain Resonance 발동 여부(§6-6)


def measures_current_brain(session: Session, run: ArenaRun) -> bool:
    """이 run이 현행(promote된) 뇌를 잰 것인가. 아니면 candidate를 잰 것이다."""
    base = current_base(session)
    return run.model_version == (base.version if base is not None else SEED_VERSION)


def reflect_arena_run(
    session: Session, run: ArenaRun, config: ExperimentsConfig, *, promoted: bool = False
) -> ReflectResult:
    """arena run을 3D 뇌 상태에 반영한다 — edge flicker + (해당하면) 현행 뇌의 밝기."""
    if run.run_type != RUN_TYPE_BRAIN:
        raise BaselineRunNotReflectable(
            f"run {run.run_id}(run_type={run.run_type})은 3D 반영 대상이 아니다 (§8-2)"
        )
    edges = apply_confusion_edges(session, run)

    brightened = 0
    if promoted:
        pass  # promote 경로가 이미 밝기를 켜고 링을 껐다 — 두 번 쓰지 않는다
    elif measures_current_brain(session, run):
        # 정기 run: 현행 뇌를 다시 잰 숫자 = 지금 밝기. 링은 건드리지 않는다(검증한 바 없다).
        brightened = apply_arena_brightness(
            session, build_outcome(run, None, config), clear_pending=False
        )
    return ReflectResult(
        run_id=run.run_id, edges_touched=edges, nodes_brightened=brightened, resonance=promoted
    )
