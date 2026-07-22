"""T2.1 AC (§10-2 Phase 2 배치 스케일화).

- 중단 후 재시작 시 중복 생성 0 (dedup_hash 기준)
- 배치별 비용 단가 리포트
- 실패 에피소드 격리 큐 (한 에피소드 실패가 배치를 중단시키지 않는다)
"""
import pytest

from app.core.config import get_config
from app.foundry.batch import prepare_scenarios, run_batch, slot_dedup_hash
from app.foundry.pilot import SyntheticFoundryProvider
from app.llm.base import EmbeddingRequest
from app.llm.client import LLMClient, LLMConfig
from app.llm.mock import MockProvider
from app.models.episodes import Episode
from app.models.foundry import FailedEpisode

CFG = get_config()
FAST_LLM = LLMConfig(max_retries=0, timeout_s=5.0, retry_backoff_s=0.0)


def _embed():
    provider = MockProvider(embed_dim=64)
    return lambda texts: provider.embed(EmbeddingRequest(inputs=texts, model="e")).vectors


def _client(provider=None):
    return LLMClient(provider or SyntheticFoundryProvider(), FAST_LLM)


def _scenarios(db_session, run_id):
    scenarios = prepare_scenarios(db_session, run_id=run_id, config=CFG)
    db_session.flush()
    return scenarios


def _count(db_session, run_id) -> int:
    return (
        db_session.query(Episode)
        .filter(Episode.episode_id.like(f"EP_{run_id}_%"))
        .count()
    )


# --- dedup_hash 재시작 멱등 (AC 1) ---


def test_slot_hash_deterministic() -> None:
    assert slot_dedup_hash("run1", 3) == slot_dedup_hash("run1", 3)
    assert slot_dedup_hash("run1", 3) != slot_dedup_hash("run1", 4)
    assert slot_dedup_hash("run1", 3) != slot_dedup_hash("run2", 3)


def test_batch_creates_n_episodes(db_session) -> None:
    scenarios = _scenarios(db_session, "batch01")
    report = run_batch(
        db_session, run_id="batch01", n=12, llm_client=_client(), embed_fn=_embed(),
        config=CFG, scenarios=scenarios, batch_size=5,
    )
    assert report.created == 12
    assert _count(db_session, "batch01") == 12


def test_restart_creates_no_duplicates(db_session) -> None:
    """전량 완료 후 같은 run_id로 재실행하면 0개 추가 (dedup_hash 스킵)."""
    scenarios = _scenarios(db_session, "batch02")
    kw = dict(llm_client=_client(), embed_fn=_embed(), config=CFG, scenarios=scenarios,
              batch_size=5)
    run_batch(db_session, run_id="batch02", n=10, **kw)
    assert _count(db_session, "batch02") == 10
    report2 = run_batch(db_session, run_id="batch02", n=10, **kw)
    assert report2.created == 0
    assert report2.skipped_existing == 10
    assert _count(db_session, "batch02") == 10  # 중복 생성 0


def test_resume_completes_remaining(db_session) -> None:
    """일부만 완료된 상태에서 재시작하면 나머지만 채운다 (총 n, 중복 0)."""
    scenarios = _scenarios(db_session, "batch03")
    kw = dict(llm_client=_client(), embed_fn=_embed(), config=CFG, scenarios=scenarios,
              batch_size=5)
    run_batch(db_session, run_id="batch03", n=6, **kw)   # 앞부분
    assert _count(db_session, "batch03") == 6
    run_batch(db_session, run_id="batch03", n=15, **kw)  # 재시작 — 6 스킵, 9 추가
    assert _count(db_session, "batch03") == 15


def test_dedup_hash_unique_in_db(db_session) -> None:
    scenarios = _scenarios(db_session, "batch04")
    run_batch(db_session, run_id="batch04", n=8, llm_client=_client(), embed_fn=_embed(),
              config=CFG, scenarios=scenarios, batch_size=4)
    hashes = [
        e.dedup_hash
        for e in db_session.query(Episode).filter(Episode.episode_id.like("EP_batch04_%"))
    ]
    assert all(h is not None for h in hashes)
    assert len(hashes) == len(set(hashes))  # 전부 유일


# --- 배치별 단가 리포트 (AC 2) ---


def test_batch_cost_report(db_session) -> None:
    scenarios = _scenarios(db_session, "batch05")
    report = run_batch(
        db_session, run_id="batch05", n=12, llm_client=_client(), embed_fn=_embed(),
        config=CFG, scenarios=scenarios, batch_size=5,
    )
    assert len(report.batches) == 3  # 5+5+2
    for b in report.batches:
        assert b.attempted > 0
        assert b.tokens > 0
        assert b.unit_tokens() == pytest.approx(b.tokens / b.attempted)
    assert report.total_tokens() == sum(b.tokens for b in report.batches)


def test_batch_size_defaults_to_config(db_session) -> None:
    scenarios = _scenarios(db_session, "batch08")
    report = run_batch(
        db_session, run_id="batch08", n=CFG.foundry.batch_size + 3, llm_client=_client(),
        embed_fn=_embed(), config=CFG, scenarios=scenarios,  # batch_size 미지정 → config
    )
    assert report.batches[0].attempted == CFG.foundry.batch_size


def test_all_failed_batch_unit_cost_not_zero(db_session) -> None:
    """전량 실패 배치라도 시도당 단가가 0이 아니다 (낭비 비용이 드러난다)."""
    scenarios = _scenarios(db_session, "batch09")

    class _AlwaysFailAnalyst(SyntheticFoundryProvider):
        def _respond(self, prompt, h):
            if "Intent Analyst" in prompt:
                return {"candidates": []}  # 항상 계약 위반
            return super()._respond(prompt, h)

    report = run_batch(
        db_session, run_id="batch09", n=4, llm_client=_client(_AlwaysFailAnalyst()),
        embed_fn=_embed(), config=CFG, scenarios=scenarios, batch_size=4,
    )
    assert report.created == 0 and report.failed == 4
    b = report.batches[0]
    assert b.created == 0 and b.attempted == 4
    assert b.tokens > 0 and b.unit_tokens() > 0  # 0.0 오보고 아님


# --- 실패 에피소드 격리 큐 ---


class _FlakyProvider(SyntheticFoundryProvider):
    """Intent Analyst에서 계약 위반 JSON을 내 특정 슬롯을 **지속** 실패시킨다.

    run_json_agent가 교정 재시도 1회를 갖게 되면서(2026-07-17), 1회성 실패는 구제된다 —
    격리 테스트의 의도는 '구제 불가능한 슬롯이 배치를 죽이지 않는다'이므로, 재시도
    프롬프트(원문 + 교정 지시)에서도 같은 판정이 나오도록 원문 단위로 실패를 고정한다.

    2026-07-22: md5%5 확률 방식 폐기 — 주변 DB 데이터 분포에 따라 20슬롯 전부 통과해
    `failed > 0`이 깨질 수 있었다(빈 격리 DB 실측, 17장 C3). 처음 만나는 서로 다른
    Analyst 원문 3개를 지속 실패로 지정해 어떤 데이터 분포에서도 결정론적으로 실패한다.
    """

    def __init__(self) -> None:
        super().__init__()
        self._fail_by_base: dict[str, bool] = {}

    def _respond(self, prompt, h):
        if "Intent Analyst" in prompt:
            base = prompt.split("\n\n## 교정 지시")[0]  # 재시도여도 원문 부분은 동일
            if base not in self._fail_by_base:
                self._fail_by_base[base] = len(self._fail_by_base) < 3  # 첫 3슬롯 지속 실패
            if self._fail_by_base[base]:
                return {"candidates": []}  # min_length=1 위반 → AgentOutputError (재시도도 동일)
        return super()._respond(prompt, h)


def test_failed_episode_isolated_not_aborting(db_session) -> None:
    scenarios = _scenarios(db_session, "batch06")
    report = run_batch(
        db_session, run_id="batch06", n=20, llm_client=_client(_FlakyProvider()),
        embed_fn=_embed(), config=CFG, scenarios=scenarios, batch_size=5,
    )
    # 일부 실패해도 배치는 끝까지 진행 (created + failed == 시도한 슬롯 수)
    assert report.failed > 0
    assert report.created + report.failed == 20
    isolated = (
        db_session.query(FailedEpisode)
        .filter(FailedEpisode.run_id == "batch06")
        .count()
    )
    assert isolated == report.failed


def test_hash_conflict_isolated_not_aborting_batch(db_session, monkeypatch) -> None:
    """동시 러너 슬롯 경합(같은 dedup_hash)이 배치 전체를 중단시키지 않고 해당 슬롯만 격리."""
    from app.foundry import batch as batch_mod

    real = batch_mod.slot_dedup_hash

    def colliding(run_id: str, i: int) -> str:
        return real(run_id, 0 if i in (0, 1) else i)  # 슬롯 0·1을 같은 해시로 충돌

    monkeypatch.setattr(batch_mod, "slot_dedup_hash", colliding)
    scenarios = _scenarios(db_session, "batch10")
    report = run_batch(
        db_session, run_id="batch10", n=4, llm_client=_client(), embed_fn=_embed(),
        config=CFG, scenarios=scenarios, batch_size=4,
    )
    # 슬롯 0·1 중 하나만 성공, 나머지는 유니크 위반으로 격리(스킵) — 배치는 끝까지
    assert report.created == 3
    assert report.skipped_existing >= 1
    assert _count(db_session, "batch10") == 3


def test_failed_slots_can_retry_on_rerun(db_session) -> None:
    """실패 슬롯은 dedup_hash가 없으므로 다음 실행에서 재시도된다."""
    scenarios = _scenarios(db_session, "batch07")
    flaky = run_batch(db_session, run_id="batch07", n=20, llm_client=_client(_FlakyProvider()),
                      embed_fn=_embed(), config=CFG, scenarios=scenarios, batch_size=5)
    created_first = flaky.created
    # 정상 provider로 재실행 — 성공분은 스킵, 실패분은 재시도되어 채워진다
    rerun = run_batch(db_session, run_id="batch07", n=20, llm_client=_client(),
                      embed_fn=_embed(), config=CFG, scenarios=scenarios, batch_size=5)
    assert rerun.skipped_existing == created_first
    assert _count(db_session, "batch07") == 20
