"""앱 레벨 무결성 가드 (§3-3, §3-6, §8-2, 절대 규칙 3·8).

1. **GOLD 불변식(§3-3):** GOLD 티어는 "인간 검수 2인 이상 일치 → 확정 라벨 보유"이므로
   label_state=LABELED가 아닌 에피소드는 GOLD로 승격될 수 없다.
2. **KTIB 동결(§8-2):** 발급된 ktib_version의 스냅샷은 덮어쓸 수 없다 — extractor를 올려
   재추출하면 그것은 새 KTIB 버전이다. `config.visual_semantics.ktib_extractor_pinned`가 켜져
   있는 동안 기존 행의 수정을 차단한다.

보장 범위: ORM 속성 대입(unit-of-work flush)만 차단한다. statement 레벨 쓰기
(session.execute(update/insert(...)), bulk_*)는 이 리스너를 우회하므로 tier를 바꾸는 코드는
반드시 promote_tier()를 경유해야 한다. (DB 레벨 CHECK 백스톱 추가는 설계 변경 제안으로 보류
중 — §3-4는 벤치마크 CHECK만 명시한다.)
"""
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.core.config import get_config
from app.models.arena import KtibItem, KtibVersion
from app.models.episodes import Episode

VALID_TIERS = ("UNVERIFIED", "BRONZE", "SILVER", "GOLD")


class TierPromotionBlocked(Exception):
    """reliability_tier 승격 불변식 위반 (§3-3)."""


class KtibFrozen(Exception):
    """발급된 ktib_version의 스냅샷 수정 시도 — 재추출은 새 KTIB 버전이다 (§8-2)."""


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
