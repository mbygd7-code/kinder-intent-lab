"""T3.7 AC (§8-1): Gym 3모드 → 세션 기록 → evidence 적재.

- Guess My Intent / Choose the Right Meaning → HUMAN_CONFIRMATION
- Correction Drill → HUMAN_CORRECTION + recovery_turns 기록
- gym evidence는 actor_type=TEACHER_TRAINER, adversarial 기본 false (§8-1, 절대 규칙 6)
- 아이템 발화는 온톨로지 positive_examples에서 (빈 뱅크에서도 동작)
- 세션 산출 evidence가 aggregator로 흘러 라벨 분포를 만든다 (루프 폐합)
"""
import pytest
from sqlalchemy import delete, select

from app.aggregator.aggregator import EvidenceSignal, aggregate
from app.core.config import get_config
from app.core.ontology import load_ontology
from app.gym.pack import build_items, build_pack
from app.gym.session import start_session, submit_results
from app.models.arena import ArenaRun, KtibItem, KtibVersion
from app.models.brain import Exemplar
from app.models.episodes import Episode, Evidence
from app.models.gym import ChallengePack, GymSession

CFG = get_config()


@pytest.fixture(autouse=True)
def _empty_bank(db_session):
    """전역 evidence/episode 카운트 단언은 빈 뱅크 전제 — 실DB에 gym 산출이 쌓여도(운영에선
    당연히 쌓인다) 깨지지 않게 세이브포인트 안에서 비운다(FK 순서, 롤백으로 원복)."""
    # 실 KTIB(ktib_items)가 episodes를 FK로 잡는다 — 자식 먼저
    db_session.execute(delete(ArenaRun))
    db_session.execute(delete(KtibItem))
    db_session.execute(delete(KtibVersion))
    db_session.execute(delete(Evidence))
    db_session.execute(delete(Exemplar))
    db_session.execute(delete(Episode))
    db_session.flush()


def _real_intent(idx=0):
    return [i.intent_id for i in load_ontology().intents if i.domain][idx]


def _pack(db, node_intent):
    return build_pack(
        db, trigger="observatory_click", node=node_intent, region=None,
        diagnosis=["CONFUSION_HIGH"], target_confusion=_real_intent(1), config=CFG,
    )


def _session_with_items(db, mode, node_intent):
    pack = _pack(db, node_intent)
    items = build_items(node_intent=node_intent, mode=mode, config=CFG)
    return start_session(db, trainer_ref="TR_GYM", mode=mode, pack=pack, items=items), items


# --- 아이템·pack ---


def test_pack_persisted_with_three_gym_modes(db_session) -> None:
    node = _real_intent()
    pack = _pack(db_session, node)
    row = db_session.get(ChallengePack, pack.pack_id)
    assert row is not None and row.pack_id.startswith("CP_")
    assert set(row.delivery_modes) >= {
        "guess_my_intent", "choose_right_meaning", "correction_drill",
    }
    assert row.origin["node"] == node


def test_pack_without_target_confusion(db_session) -> None:
    """target_confusion 없이도 pack 생성(계약상 target_edges 키 생략) — null 명시 거부 회귀."""
    node = _real_intent()
    pack = build_pack(
        db_session, trigger="observatory_click", node=node, region=None,
        diagnosis=["GOLD_LOW"], target_confusion=None, config=CFG,
    )
    row = db_session.get(ChallengePack, pack.pack_id)
    assert row is not None and row.target_edges is None
    assert row.strategy == ["B_HUMAN_EVIDENCE"]


def test_pack_without_diagnosis(db_session) -> None:
    """diagnosis 생략(None)에도 pack 생성 — origin.diagnosis 명시 null 거부 회귀(리뷰 MAJOR)."""
    node = _real_intent()
    pack = build_pack(
        db_session, trigger="observatory_click", node=node, region=None,
        diagnosis=None, target_confusion=None, config=CFG,
    )
    row = db_session.get(ChallengePack, pack.pack_id)
    assert row is not None
    assert "diagnosis" not in row.origin           # 키 생략(명시 null 아님)
    assert row.strategy == ["B_HUMAN_EVIDENCE"]     # 진단 없으면 B 폴백


def test_items_from_ontology_examples(db_session) -> None:
    node = _real_intent()
    items = build_items(node_intent=node, mode="guess_my_intent", config=CFG)
    assert 1 <= len(items) <= CFG.gym.session_items
    onto = {i.intent_id: i for i in load_ontology().intents}
    for it in items:
        assert it["utterance"]  # 실 발화(온톨로지 예시)
        assert node in it["candidate_intents"]
        # true_intent의 발화는 그 intent의 positive_examples 중 하나
        assert it["utterance"] in onto[it["true_intent"]].positive_examples


# --- evidence 적재 (§8-1) ---


def test_guess_my_intent_creates_human_confirmation(db_session) -> None:
    node = _real_intent()
    gym, items = _session_with_items(db_session, "guess_my_intent", node)
    responses = [{"item_id": items[0]["item_id"], "chosen_intent": node, "recovery_turns": 0}]
    report = submit_results(db_session, gym, responses, CFG)
    db_session.flush()
    assert report.evidence_created == 1 and report.episodes_created == 1
    ev = db_session.scalars(select(Evidence)).all()[0]
    assert ev.evidence_type == "HUMAN_CONFIRMATION"
    assert ev.actor_type == "TEACHER_TRAINER"
    assert ev.adversarial is False          # 절대 규칙 6: gym 기본 false
    assert ev.polarity == "supports" and ev.intent_id == node
    assert ev.trainer_ref == "TR_GYM"
    # GYM_HUMAN 에피소드에 붙는다
    ep = db_session.get(Episode, ev.episode_id)
    assert ep.origin_channel == "GYM_HUMAN" and ep.episode_creator_type == "GYM_SESSION"


def test_correction_drill_creates_human_correction_with_recovery(db_session) -> None:
    """핵심 AC: 교정 세션 → HUMAN_CORRECTION + recovery_turns 기록."""
    node = _real_intent()
    wrong = _real_intent(1)
    gym, items = _session_with_items(db_session, "correction_drill", node)
    # 브레인이 wrong으로 오답 → 트레이너가 node로 교정, 2턴 만에
    responses = [{
        "item_id": items[0]["item_id"], "chosen_intent": node,
        "brain_guess": wrong, "recovery_turns": 2,
    }]
    report = submit_results(db_session, gym, responses, CFG)
    db_session.flush()
    ev = db_session.scalars(select(Evidence)).all()[0]
    assert ev.evidence_type == "HUMAN_CORRECTION"
    assert ev.intent_id == node and ev.polarity == "supports"
    assert ev.adversarial is False
    # recovery_turns가 세션 결과에 기록된다
    gym_row = db_session.get(GymSession, gym.session_id)
    resp = gym_row.results["responses"][0]
    assert resp["recovery_turns"] == 2
    assert report.by_type["HUMAN_CORRECTION"] == 1


def test_evidence_strength_from_config(db_session) -> None:
    """절대 규칙 10: evidence strength는 config.gym.evidence_strength에서 온다(리터럴 아님)."""
    node = _real_intent()
    custom = CFG.model_copy(update={"gym": CFG.gym.model_copy(update={"evidence_strength": 0.42})})
    gym, items = _session_with_items(db_session, "guess_my_intent", node)
    submit_results(
        db_session, gym,
        [{"item_id": items[0]["item_id"], "chosen_intent": node, "recovery_turns": 0}], custom,
    )
    db_session.flush()
    ev = db_session.scalars(select(Evidence)).all()[0]
    assert ev.strength == 0.42


def test_choose_right_meaning_confirmation(db_session) -> None:
    node = _real_intent()
    gym, items = _session_with_items(db_session, "choose_right_meaning", node)
    responses = [{"item_id": items[0]["item_id"], "chosen_intent": node, "recovery_turns": 0}]
    submit_results(db_session, gym, responses, CFG)
    db_session.flush()
    ev = db_session.scalars(select(Evidence)).all()[0]
    assert ev.evidence_type == "HUMAN_CONFIRMATION"


def test_gym_evidence_flows_into_aggregator(db_session) -> None:
    """루프 폐합: 세션 evidence를 aggregate()에 넣으면 그 intent가 top."""
    node = _real_intent()
    gym, items = _session_with_items(db_session, "guess_my_intent", node)
    responses = [{"item_id": it["item_id"], "chosen_intent": node, "recovery_turns": 0}
                 for it in items]
    submit_results(db_session, gym, responses, CFG)
    db_session.flush()
    signals = [
        EvidenceSignal(intent_id=e.intent_id, polarity=e.polarity, strength=e.strength,
                       evidence_type=e.evidence_type, actor_type=e.actor_type,
                       trainer_ref=e.trainer_ref, adversarial=e.adversarial)
        for e in db_session.scalars(select(Evidence)).all()
    ]
    result = aggregate(signals, CFG)
    assert result.top_intent == node
    assert result.excluded_adversarial == 0


def test_unknown_item_id_rejected(db_session) -> None:
    node = _real_intent()
    gym, _items = _session_with_items(db_session, "guess_my_intent", node)
    report = submit_results(
        db_session, gym, [{"item_id": "NOPE", "chosen_intent": node, "recovery_turns": 0}], CFG
    )
    assert report.evidence_created == 0  # 세션에 없는 아이템은 무시(지어내지 않음)
