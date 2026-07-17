"""Atlas 배선 AC — §2가 '구조만 있는 죽은 모듈'에서 실동작으로 (2026-07-17 감사 후속).

- S6 재보정: Atlas 통계가 있으면 Simulator 컨텍스트에 실리고, 비면 생략(0 통계로 오도 금지)
- coverage(§2-4): 배치 신규 발화 중 미매핑 → 확장 큐. Atlas가 비어 있으면 스킵(큐 범람 방지)
- 원료 주입구(atlas_ingest): 원문 줄 단위 S4 채굴, 패러프레이즈 가드(절대 규칙 7),
  대표형 임베딩 저장(§5-4[1] retrieval 사전 계산)
"""
import hashlib

import pytest
from sqlalchemy import delete, select

from app.core.config import get_config
from app.foundry.atlas_ingest import mine_text
from app.foundry.batch import prepare_scenarios, run_batch
from app.foundry.episode_builder import generate_episode
from app.foundry.pilot import SyntheticFoundryProvider, _Deduper
from app.llm.client import LLMClient, LLMConfig
from app.models.foundry import AtlasEntry, AtlasExpansionEntry

CFG = get_config()
FAST_LLM = LLMConfig(max_retries=0, timeout_s=5.0, retry_backoff_s=0.0)
DIM = 1536  # AtlasEntry.embedding Vector(1536)와 일치


class _CaptureProvider(SyntheticFoundryProvider):
    """프롬프트 원문을 수집 — S6 컨텍스트에 무엇이 실렸는지 검증용."""

    def __init__(self) -> None:
        super().__init__()
        self.prompts: list[str] = []

    def complete(self, request):
        self.prompts.append(request.prompt)
        return super().complete(request)


def _one_hot_embed(texts: list[str]) -> list[list[float]]:
    """텍스트별 원-핫 벡터 — 서로 다른 텍스트는 유사도 0(결정론), 같은 텍스트는 1."""
    out = []
    for t in texts:
        vec = [0.0] * DIM
        vec[int(hashlib.sha256(t.encode()).hexdigest(), 16) % DIM] = 1.0
        out.append(vec)
    return out


@pytest.fixture(autouse=True)
def _clean_atlas(db_session):
    db_session.execute(delete(AtlasExpansionEntry))
    db_session.execute(delete(AtlasEntry))
    db_session.flush()


def _seed_atlas(db, n=1):
    for i in range(n):
        db.add(AtlasEntry(
            atlas_id=f"ATL_test_{i}", surface_form=f"기준 문장 전혀 다른 {i}",
            pattern_cluster="PC_t", ambiguity_types=[], possible_intents=[],
            resolution_signals=[],
        ))
    db.flush()


# --- S6 재보정 통계 주입 ---


def test_generate_episode_injects_atlas_stats_only_when_present(db_session) -> None:
    """★ atlas_stats가 있으면 S6 프롬프트에 실리고, 없으면 흔적도 없다."""
    cap = _CaptureProvider()
    client = LLMClient(cap, FAST_LLM)
    deduper = _Deduper(_one_hot_embed, CFG.foundry.dedup_similarity)

    generate_episode(
        client, config=CFG, run_id="run_atl_a", index=0, scenario_id="CS_x",
        persona="P_hypo_1", ontology_version="onto-test", deduper=deduper,
        atlas_stats={"sample_count": 5, "mean_word_length": 4.2, "deixis_ratio": 0.4},
    )
    s6 = [p for p in cap.prompts if "Teacher Simulator" in p]
    assert s6 and "atlas_stats" in s6[0] and "deixis_ratio" in s6[0]

    cap.prompts.clear()
    generate_episode(
        client, config=CFG, run_id="run_atl_b", index=1, scenario_id="CS_x",
        persona="P_hypo_1", ontology_version="onto-test", deduper=deduper,
    )
    s6b = [p for p in cap.prompts if "Teacher Simulator" in p]
    assert s6b and "atlas_stats" not in s6b[0]


# --- coverage → 확장 큐 (배치 배선) ---


def test_run_batch_skips_queue_when_atlas_empty(db_session) -> None:
    """Atlas가 비면 확장 큐 적재를 스킵 — 전량 미매핑으로 큐가 범람하지 않는다."""
    scen = prepare_scenarios(db_session, run_id="run_atl_q0", config=CFG)
    run_batch(
        db_session, run_id="run_atl_q0", n=2,
        llm_client=LLMClient(SyntheticFoundryProvider(), FAST_LLM),
        embed_fn=_one_hot_embed, config=CFG, scenarios=scen, batch_size=2,
    )
    assert db_session.scalar(select(AtlasExpansionEntry.queue_id).limit(1)) is None


def test_run_batch_enqueues_unmapped_and_feeds_s6(db_session) -> None:
    """★ Atlas가 있으면: S6에 통계가 실리고, 미매핑 신규 발화가 확장 큐에 쌓인다(run 표기)."""
    _seed_atlas(db_session)
    cap = _CaptureProvider()
    scen = prepare_scenarios(db_session, run_id="run_atl_q1", config=CFG)
    run_batch(
        db_session, run_id="run_atl_q1", n=2, llm_client=LLMClient(cap, FAST_LLM),
        embed_fn=_one_hot_embed, config=CFG, scenarios=scen, batch_size=2,
    )
    s6 = [p for p in cap.prompts if "Teacher Simulator" in p]
    assert s6 and "atlas_stats" in s6[0]  # 재보정 통계가 실제로 흘렀다

    rows = db_session.scalars(select(AtlasExpansionEntry)).all()
    assert rows, "미매핑 발화가 확장 큐에 안 쌓임"
    assert all(r.source_run == "run_atl_q1" and r.status == "PENDING" for r in rows)


# --- 원료 주입구 (atlas_ingest) ---


def test_mine_text_ingests_lines_with_guard_and_embedding(db_session) -> None:
    """★ 원문 3줄 → S4 채굴 3건(패러프레이즈 대표형·임베딩 저장). 원문은 Atlas에 없다."""
    text = "이거 좀 봐줄래?\n\n다음엔 뭐 하지?\n사진 정리 어떻게 해?"
    report = mine_text(
        db_session, llm_client=LLMClient(SyntheticFoundryProvider(), FAST_LLM),
        embed_fn=_one_hot_embed, config=CFG, text=text, title="테스트 원문",
    )
    assert report.attempted == 3 and report.mined == 3 and report.failed == 0

    entries = db_session.scalars(select(AtlasEntry)).all()
    assert len(entries) == 3
    assert all(e.embedding is not None for e in entries)  # §5-4[1] retrieval 사전 계산
    assert all("이거 좀 봐줄래" not in e.surface_form for e in entries)  # 원문 저장 금지(규칙 7)


def test_mine_text_discards_paraphrase_too_similar(db_session) -> None:
    """대표형이 원문과 같게 임베딩되면 폐기 — 절대 규칙 7 가드가 주입구에도 작동한다."""
    same_vec = [1.0] + [0.0] * (DIM - 1)
    report = mine_text(
        db_session, llm_client=LLMClient(SyntheticFoundryProvider(), FAST_LLM),
        embed_fn=lambda texts: [same_vec for _ in texts],
        config=CFG, text="원문 한 줄", title="유사도 가드 테스트",
    )
    assert report.discarded_similar == 1 and report.mined == 0
    assert db_session.scalar(select(AtlasEntry.atlas_id).limit(1)) is None


def test_run_batch_survives_coverage_failure(db_session) -> None:
    """coverage 계산이 죽어도 증산 run은 살아남는다(부가 지표 격리 — 적대 검증)."""
    _seed_atlas(db_session)
    trigger = "기준 문장 전혀 다른 0"  # coverage가 Atlas surface_form을 임베딩할 때만 존재

    def _bomb_embed(texts):
        if any(trigger in t for t in texts):
            raise RuntimeError("embed 폭발(주입)")
        return _one_hot_embed(texts)

    scen = prepare_scenarios(db_session, run_id="run_atl_bomb", config=CFG)
    report = run_batch(
        db_session, run_id="run_atl_bomb", n=2,
        llm_client=LLMClient(SyntheticFoundryProvider(), FAST_LLM),
        embed_fn=_bomb_embed, config=CFG, scenarios=scen, batch_size=2,
    )
    assert report.created > 0  # 에피소드 생성은 완료 — coverage 실패가 run을 못 죽였다
    assert db_session.scalar(select(AtlasExpansionEntry.queue_id).limit(1)) is None
