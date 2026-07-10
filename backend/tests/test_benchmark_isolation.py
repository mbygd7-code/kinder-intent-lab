"""§8-2 격리 불변식: **학습 파이프라인은 KTIB에 접근할 수 없다.**

BENCHMARK_HOLDOUT 에피소드는 정의상 GOLD∧LABELED다(절대 규칙 2). 따라서 split을 보지 않는
모든 GOLD 질의는 자기도 모르게 벤치마크를 학습에 끌어들인다. 그러면 Arena 점수는 '암기'의
측정치가 되어 아무 의미가 없다.

여기서 잠그는 네 경로:
  1. exemplar 선정 (retrieval의 재료 — 가장 직접적인 누수)
  2. 노드 evidence_stats (3D Size·gold_count)
  3. Weakness 진단의 GOLD_LOW 축
  4. Version Gate의 new_gold (candidate 생성 트리거)
"""
import pytest
from sqlalchemy import delete, select

from app.brain.backfill import aggregate_evidence_stats, bootstrap_nodes, select_exemplars
from app.brain.diagnosis import diagnose_node
from app.brain.version_gate import count_gold, new_gold_since_base
from app.core.config import get_config
from app.core.datasets import is_training_gold
from app.core.ontology import load_ontology
from app.models.arena import KtibItem, KtibVersion
from app.models.brain import BrainNode, BrainVersion, Exemplar
from app.models.episodes import Episode, Evidence
from app.models.foundry import CanonicalScenario
from tests.brain_helpers import _embed

CFG = get_config()


@pytest.fixture(autouse=True)
def _empty(db_session):
    for model in (KtibItem, KtibVersion, Exemplar, Evidence, Episode, CanonicalScenario,
                  BrainVersion, BrainNode):
        db_session.execute(delete(model))
    db_session.flush()
    bootstrap_nodes(db_session, approved_by="lab")
    db_session.flush()


def _intent(i=0) -> str:
    return [x.intent_id for x in load_ontology().intents if x.domain][i]


def _episode(db, epid, intent, *, split, prompt) -> Episode:
    """GOLD∧LABELED 에피소드. split만 다르다 — 그것이 격리의 유일한 근거다."""
    ep = Episode(
        episode_id=epid, ontology_version="onto-1.0", lang="ko", dataset_split=split,
        reliability_tier="GOLD", label_state="LABELED", origin_channel="EXPERT_AUTHORED",
        episode_creator_type="HUMAN_ANNOTATOR", primary_subject_type="TEACHER",
        teacher_prompt=prompt, label_distribution={intent: 1.0},
    )
    db.add(ep)
    db.flush()
    return ep


# --- 술어 자체 ---


def test_is_training_gold_excludes_benchmark(db_session) -> None:
    intent = _intent(0)
    train = _episode(db_session, "EP_T", intent, split="TRAIN", prompt="학습 발화")
    bench = _episode(db_session, "EP_B", intent, split="BENCHMARK_HOLDOUT", prompt="벤치 발화")
    assert is_training_gold(train) is True
    assert is_training_gold(bench) is False   # GOLD∧LABELED이지만 학습 자산이 아니다


# --- 1. exemplar 누수 (가장 치명적) ---


def test_benchmark_episode_never_becomes_exemplar(db_session) -> None:
    """★ 벤치마크 발화가 exemplar가 되면 retrieval이 정답을 외운다 — Arena 점수가 무의미해진다."""
    intent = _intent(0)
    _episode(db_session, "EP_TRAIN", intent, split="TRAIN", prompt="학습용 발화")
    _episode(db_session, "EP_BENCH", intent, split="BENCHMARK_HOLDOUT", prompt="벤치마크 발화")

    select_exemplars(db_session, CFG, _embed())
    db_session.flush()

    chosen = set(db_session.scalars(select(Exemplar.episode_id)).all())
    assert "EP_TRAIN" in chosen
    assert "EP_BENCH" not in chosen  # ★ 격리


def test_benchmark_only_bank_yields_no_exemplars(db_session) -> None:
    """벤치마크만 있는 뱅크는 exemplar 0개 — '벤치마크로 학습된 뇌'가 존재할 수 없다."""
    _episode(db_session, "EP_BENCH", _intent(0), split="BENCHMARK_HOLDOUT", prompt="벤치마크 발화")
    assert select_exemplars(db_session, CFG, _embed()) == 0
    assert db_session.scalars(select(Exemplar)).first() is None


# --- 2. 노드 evidence_stats (3D Size) ---


def test_benchmark_gold_not_counted_in_node_stats(db_session) -> None:
    """벤치마크는 노드의 훈련량(size)·gold_count를 부풀리지 않는다 (§7-5 Size ← Training Volume)."""
    intent = _intent(0)
    _episode(db_session, "EP_TRAIN", intent, split="TRAIN", prompt="학습용")
    _episode(db_session, "EP_BENCH", intent, split="BENCHMARK_HOLDOUT", prompt="벤치마크")
    aggregate_evidence_stats(db_session)
    db_session.flush()

    node = db_session.scalar(select(BrainNode).where(BrainNode.intent_id == intent))
    assert (node.evidence_stats or {}).get("gold") == 1  # 학습분 1건만


# --- 3. Weakness 진단 GOLD_LOW 축 ---


def test_benchmark_gold_does_not_hide_gold_low(db_session) -> None:
    """벤치마크가 GOLD_LOW 진단을 가리면 '데이터가 충분하다'는 거짓 진단이 나온다(§7-3)."""
    intent = _intent(0)
    for k in range(CFG.diagnosis.gold_high + 2):
        _episode(db_session, f"EP_B{k}", intent, split="BENCHMARK_HOLDOUT", prompt=f"벤치 {k}")

    dg = diagnose_node(db_session, intent, CFG)
    assert dg.gold_data.value == 0        # 학습 GOLD는 0건
    assert dg.gold_data.level == "LOW"    # → 여전히 약하다고 진단해야 한다


# --- 4. Version Gate new_gold ---


def test_benchmark_growth_does_not_trigger_candidate(db_session) -> None:
    """★ 벤치마크를 늘렸다고 candidate 빌드가 트리거되면 안 된다 (§6-6 트리거는 학습 성장이다)."""
    intent = _intent(0)
    for k in range(CFG.version_gate.min_new_gold + 5):
        _episode(db_session, f"EP_B{k}", intent, split="BENCHMARK_HOLDOUT", prompt=f"벤치 {k}")

    assert count_gold(db_session) == 0
    assert new_gold_since_base(db_session) == 0

    _episode(db_session, "EP_T1", intent, split="TRAIN", prompt="학습 1건")
    assert count_gold(db_session) == 1  # 학습분만 센다
