"""T1.11 AC (§1-14).

- S1~S11 E2E로 n 에피소드 생성 완료
- run manifest에서 임의 에피소드의 원천 소스 역추적 가능
- 게이트 리포트 3지표(평균 합의도·Judge reject율·kappa) 출력 + Phase 1 게이트 판정
"""
import pytest

from app.core.config import get_config
from app.foundry.pilot import (
    GateReport,
    SyntheticFoundryProvider,
    run_pilot,
)
from app.llm.client import LLMClient, LLMConfig
from app.llm.mock import MockProvider
from app.models.episodes import Episode

CFG = get_config()
FAST_LLM = LLMConfig(max_retries=0, timeout_s=5.0, retry_backoff_s=0.0)


def _mock_embed():
    provider = MockProvider(embed_dim=64)  # 파일럿 테스트는 저차원으로 가속

    def embed(texts: list[str]) -> list[list[float]]:
        from app.llm.base import EmbeddingRequest

        return provider.embed(EmbeddingRequest(inputs=texts, model="embed")).vectors

    return embed


def _run(session, n: int, kappa=None):
    client = LLMClient(SyntheticFoundryProvider(), FAST_LLM)
    return run_pilot(
        session,
        n=n,
        llm_client=client,
        embed_fn=_mock_embed(),
        config=CFG,
        run_id="testrun01",
        human_kappa=kappa,
    )


# --- AC 1: n 에피소드 E2E 생성 ---


def test_pilot_creates_requested_episodes(db_session) -> None:
    result = _run(db_session, 25)
    db_session.flush()
    assert result.report.episodes == 25
    persisted = (
        db_session.query(Episode)
        .filter(Episode.episode_id.like("EP_testrun01_%"))
        .count()
    )
    assert persisted == 25


def test_pilot_episodes_are_bronze_or_silver(db_session) -> None:
    """S11: 파이프라인 산출은 전부 BRONZE/SILVER — GOLD 절대 생성 안 함 (§S11)."""
    _run(db_session, 25)
    db_session.flush()
    tiers = {
        e.reliability_tier
        for e in db_session.query(Episode).filter(
            Episode.episode_id.like("EP_testrun01_%")
        )
    }
    assert tiers <= {"BRONZE", "SILVER"}
    assert "GOLD" not in tiers


def test_pilot_episodes_are_synthetic_provenance(db_session) -> None:
    _run(db_session, 10)
    db_session.flush()
    for e in db_session.query(Episode).filter(Episode.episode_id.like("EP_testrun01_%")):
        assert e.origin_channel == "FOUNDRY_SYNTHETIC"
        assert e.episode_creator_type == "FOUNDRY_PIPELINE"
        assert e.primary_subject_type == "SIMULATED_TEACHER"


# --- AC 2: manifest 계보 역추적 ---


def test_manifest_traces_episode_to_source(db_session) -> None:
    result = _run(db_session, 15)
    manifest = result.manifest
    for episode_id in manifest.episode_scenario:
        source_id = manifest.trace_source(episode_id)
        assert source_id is not None and source_id.startswith("SRC_")
        # 전체 계보가 이어져야 한다: episode → scenario → frame → source
        scenario_id = manifest.episode_scenario[episode_id]
        frame_id = manifest.scenario_frame[scenario_id]
        assert manifest.frame_source[frame_id] == source_id


def test_manifest_records_tokens_and_cost(db_session) -> None:
    result = _run(db_session, 10)
    assert result.manifest.total_tokens() > 0
    assert len(result.manifest.episode_tokens) == 10
    assert all(t > 0 for t in result.manifest.episode_tokens.values())


# --- AC 3: 게이트 리포트 3지표 + Phase 1 게이트 ---


def test_gate_report_has_three_metrics(db_session) -> None:
    report = _run(db_session, 30, kappa=0.7).report
    d = report.as_dict()
    assert "mean_consensus" in d
    assert "judge_reject_rate" in d
    assert "human_kappa" in d
    assert 0 <= report.mean_consensus <= 1
    assert 0 <= report.judge_reject_rate <= 1


def test_gate_undetermined_without_kappa(db_session) -> None:
    """kappa 미입력이면 게이트 통과를 단정할 수 없다 (입력 인터페이스)."""
    report = _run(db_session, 20, kappa=None).report
    assert report.passed() is None


def test_gate_passes_with_good_metrics(db_session) -> None:
    report = _run(db_session, 40, kappa=CFG.foundry.pilot_kappa_min + 0.05).report
    assert report.mean_consensus >= CFG.foundry.consensus_min
    assert report.judge_reject_rate <= CFG.foundry.judge_reject_max
    assert report.passed() is True


def test_gate_fails_with_low_kappa(db_session) -> None:
    report = _run(db_session, 20, kappa=CFG.foundry.pilot_kappa_min - 0.1).report
    assert report.passed() is False


def test_judge_reject_rate_within_bound(db_session) -> None:
    """합성 파이프라인은 reject율(~0.11)을 judge_reject_max(0.25) 아래로 유지한다.

    파일럿은 scenario_id가 uuid라 실행마다 판정이 달라진다(합성 provider가 해시 기반).
    작은 n에서는 분산이 커 꼬리에서 0.25를 넘을 수 있으므로 표본을 크게 잡아 안정화한다.
    """
    report = _run(db_session, 200).report
    assert report.judge_reject_rate <= CFG.foundry.judge_reject_max


# --- 온톨로지 정합: 생성된 라벨은 온톨로지 intent_id ---


def test_episode_labels_are_ontology_intents(db_session) -> None:
    from app.core.ontology import load_ontology

    valid = {i.intent_id for i in load_ontology().intents}
    _run(db_session, 20)
    db_session.flush()
    for e in db_session.query(Episode).filter(Episode.episode_id.like("EP_testrun01_%")):
        for intent in e.label_distribution:
            assert intent in valid, intent


# --- 리뷰 회귀 ---


def test_gate_autofail_is_false_even_without_kappa() -> None:
    """자동 지표(합의도·reject) 실패는 kappa 미입력이어도 확정 실패(None 아님)."""
    report = GateReport(
        episodes=10, mean_consensus=0.1, judge_reject_rate=0.9, human_kappa=None,
        consensus_min=CFG.foundry.consensus_min, judge_reject_max=CFG.foundry.judge_reject_max,
        pilot_kappa_min=CFG.foundry.pilot_kappa_min,
    )
    assert report.passed() is False


def test_recorder_restored_after_run(db_session) -> None:
    """run_pilot이 호출자 recorder를 파괴하지 않고 복원한다."""
    seen: list = []

    def rec(record) -> None:
        seen.append(record)

    client = LLMClient(SyntheticFoundryProvider(), FAST_LLM, recorder=rec)
    run_pilot(db_session, n=5, llm_client=client, embed_fn=_mock_embed(), config=CFG,
              run_id="rec001")
    assert client._recorder is rec


def test_dedup_exhaustion_raises(db_session) -> None:
    """항상 동일 발화를 뱉는 provider면 재시도 소진 후 명확히 실패 (n 미달 은폐 없음)."""
    class ConstProvider(SyntheticFoundryProvider):
        def _respond(self, prompt, h):
            if "Teacher Simulator" in prompt:
                return {"utterance": "완전히 동일한 발화"}
            return super()._respond(prompt, h)

    client = LLMClient(ConstProvider(), FAST_LLM)
    with pytest.raises(RuntimeError, match="dedup"):
        run_pilot(db_session, n=5, llm_client=client, embed_fn=_mock_embed(), config=CFG,
                  run_id="const01")
