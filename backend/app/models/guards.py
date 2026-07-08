"""앱 레벨 무결성 가드 (§3-3, §3-6, 절대 규칙 8).

GOLD 티어는 "인간 검수 2인 이상 일치 → 확정 라벨 보유"(§3-3)이므로
label_state=LABELED가 아닌 에피소드는 GOLD로 승격될 수 없다.

보장 범위: promote_tier() 경유와 ORM 속성 대입(unit-of-work flush)만 차단한다.
statement 레벨 쓰기(session.execute(update/insert(...)), bulk_*)는 이 리스너를
우회하므로 tier를 바꾸는 코드는 반드시 promote_tier()를 경유해야 한다.
(DB 레벨 CHECK 백스톱 추가는 설계 변경 제안으로 보류 중 — §3-4는 벤치마크
CHECK만 명시한다.)
"""
from sqlalchemy import event
from sqlalchemy.orm import Session

from app.models.episodes import Episode

VALID_TIERS = ("UNVERIFIED", "BRONZE", "SILVER", "GOLD")


class TierPromotionBlocked(Exception):
    """reliability_tier 승격 불변식 위반 (§3-3)."""


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
