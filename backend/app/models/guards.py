"""앱 레벨 무결성 가드 (§3-3, §3-6, §8-2, 절대 규칙 2·3·8).

1. **GOLD 불변식(§3-3):** GOLD 티어는 "인간 검수 2인 이상 일치 → 확정 라벨 보유"이므로
   label_state=LABELED가 아닌 에피소드는 GOLD로 승격될 수 없다.
2. **KTIB 동결(§8-2):** 발급된 ktib_version의 스냅샷은 덮어쓸 수 없다 — extractor를 올려
   재추출하면 그것은 새 KTIB 버전이다. `config.visual_semantics.ktib_extractor_pinned`가 켜져
   있는 동안 기존 행의 수정을 차단한다.
3. **밝기의 원천(§8-2·절대 규칙 3):** `brain_nodes`의 brightness 계열(heldout_accuracy·
   calibration_ece·last_arena_run)은 **Arena 결과 반영 경로에서만** 쓸 수 있다. 훈련·교정·
   backfill 등 다른 코드 경로에서 대입하면 flush에서 `BrightnessWriteBlocked`로 실패한다.
   유일한 통로는 `arena_brightness_write(run_id)` 컨텍스트이고, 그 안에서도 노드의
   `last_arena_run`이 해당 run_id와 일치해야 한다(귀속 강제).

보장 범위: ORM 속성 대입(unit-of-work flush)만 차단한다. statement 레벨 쓰기
(session.execute(update/insert(...)), bulk_*)는 이 리스너를 우회하므로 tier를 바꾸는 코드는
반드시 promote_tier()를, 밝기를 쓰는 코드는 반드시 arena_brightness_write()를 경유해야 한다.
(DB 레벨 CHECK 백스톱 추가는 설계 변경 제안으로 보류 중 — §3-4는 벤치마크 CHECK만 명시한다.)
"""
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from sqlalchemy import event, inspect
from sqlalchemy.orm import Session

from app.core.config import get_config
from app.models.arena import KtibItem, KtibVersion
from app.models.brain import BrainNode
from app.models.episodes import Episode

VALID_TIERS = ("UNVERIFIED", "BRONZE", "SILVER", "GOLD")

# §7-5 Brightness 바인딩의 저장 필드 — Arena만이 쓴다(원칙 8).
BRIGHTNESS_FIELDS = ("heldout_accuracy", "calibration_ece", "last_arena_run")

# 현재 반영 중인 arena run_id. None이면 밝기 쓰기 금지.
_ARENA_RUN: ContextVar[str | None] = ContextVar("arena_brightness_run", default=None)


class TierPromotionBlocked(Exception):
    """reliability_tier 승격 불변식 위반 (§3-3)."""


class KtibFrozen(Exception):
    """발급된 ktib_version의 스냅샷 수정 시도 — 재추출은 새 KTIB 버전이다 (§8-2)."""


class BrightnessWriteBlocked(Exception):
    """Arena 반영 경로 밖에서 노드 brightness를 쓰려 함 (절대 규칙 3, 원칙 8)."""


@contextmanager
def arena_brightness_write(run_id: str) -> Iterator[None]:
    """밝기 쓰기를 허용하는 유일한 컨텍스트. run_id는 그 값을 만든 arena run이다.

    이 컨텍스트 안에서도 노드의 `last_arena_run`이 run_id와 같아야 한다 — 어떤 run이 그
    밝기를 만들었는지 귀속되지 않는 값은 §8-2 replay 무결성에서 의미가 없다.
    """
    if not run_id:
        raise BrightnessWriteBlocked("run_id 없이 밝기를 쓸 수 없다 (§8-2 replay 무결성)")
    token = _ARENA_RUN.set(run_id)
    try:
        yield
    finally:
        _ARENA_RUN.reset(token)


def promote_tier(episode: Episode, new_tier: str) -> None:
    """tier 승격 단일 경로. GOLD ⇒ label_state=LABELED 필수."""
    if new_tier not in VALID_TIERS:
        raise ValueError(f"알 수 없는 tier: {new_tier}")
    if new_tier == "GOLD" and episode.label_state != "LABELED":
        raise TierPromotionBlocked(
            f"GOLD 승격은 label_state=LABELED에서만 가능 "
            f"(현재 {episode.label_state}) — §3-3"
        )
    episode.reliability_tier = new_tier


@event.listens_for(Session, "before_flush")
def _enforce_gold_invariant(session: Session, flush_context, instances) -> None:
    for obj in list(session.new) + list(session.dirty):
        if (
            isinstance(obj, Episode)
            and obj.reliability_tier == "GOLD"
            and obj.label_state != "LABELED"
        ):
            raise TierPromotionBlocked(
                f"episode {obj.episode_id}: GOLD ∧ label_state={obj.label_state} "
                f"불변식 위반 — §3-3"
            )


def _changed_brightness_fields(node: BrainNode) -> list[str]:
    state = inspect(node)
    return [f for f in BRIGHTNESS_FIELDS if state.attrs[f].history.has_changes()]


@event.listens_for(Session, "before_flush")
def _enforce_brightness_source(session: Session, flush_context, instances) -> None:
    """★ 절대 규칙 3: brightness는 Arena 결과만 갱신한다.

    훈련(gym.growth)·교정(fast_update)·backfill은 size/density/pending_evaluation만 만진다.
    그 경로에서 heldout_accuracy 등을 대입하면 여기서 즉시 실패한다 — 조용히 밝아지는 지름길은
    구조적으로 존재하지 않는다(§6-7 "[4]→[6]에서 밝기가 바로 오르는 지름길은 없다").
    """
    run_id = _ARENA_RUN.get()
    for obj in session.dirty:
        if not isinstance(obj, BrainNode):
            continue
        changed = _changed_brightness_fields(obj)
        if not changed:
            continue
        if run_id is None:
            raise BrightnessWriteBlocked(
                f"node {obj.intent_id}: {changed} 갱신은 Arena 반영 경로에서만 가능하다 "
                f"(arena_brightness_write 컨텍스트 밖) — 절대 규칙 3 / 원칙 8"
            )
        if obj.last_arena_run != run_id:
            raise BrightnessWriteBlocked(
                f"node {obj.intent_id}: 밝기를 쓰면서 last_arena_run={obj.last_arena_run!r}가 "
                f"반영 중인 run({run_id!r})과 다르다 — 귀속 불가 (§8-2 replay 무결성)"
            )


@event.listens_for(Session, "before_flush")
def _enforce_ktib_frozen(session: Session, flush_context, instances) -> None:
    """이미 발급된 KTIB 스냅샷의 수정(=재추출)을 차단 — 새 ktib_version으로만 (§8-2).

    session.new(신규 버전 INSERT)는 통과시키고 session.dirty(기존 행 UPDATE)만 막는다.
    """
    if not get_config().visual_semantics.ktib_extractor_pinned:
        return  # 핀 해제 시에만 재추출 허용 (실험 파라미터)
    for obj in session.dirty:
        if not session.is_modified(obj, include_collections=False):
            continue
        if isinstance(obj, KtibItem):
            raise KtibFrozen(
                f"ktib_items({obj.ktib_version}, {obj.episode_id}) 수정 시도 — "
                f"재추출은 새 ktib_version이다 (§8-2)"
            )
        if isinstance(obj, KtibVersion):
            raise KtibFrozen(
                f"ktib_versions({obj.ktib_version}) 수정 시도 — 벤치마크는 동결된다 (§8-2)"
            )
