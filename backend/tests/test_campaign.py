"""T2.5 AC (§10-2 Phase 2, §1-14 기준선).

- 캠페인 도메인 배분: DOCUMENT+VISUAL 우선 · 7개 도메인 전부 · config 가중치 반영
- 주간 품질 리포트: 윈도별 합의도·reject율·단가(시도당 토큰) + 기준선 대비 델타
- reject율·합의도·단가가 Pilot 대비 악화되면 자동 중단 (목표 도달 전 멈춤)

합성 파이프라인은 scenario_id가 uuid라 판정이 실행마다 흔들린다(T1.11과 동일). 따라서
자동중단 테스트는 해시 비의존·결정론적 degrade provider(judge 항상 reject / uniform 가중치 /
토큰 10배)로 구성하고, 악화 마진을 크게 둬 밴드 내 변동이 임계를 넘지 않게 한다.
"""
import pytest

from app.core.config import get_config
from app.core.ontology import CANONICAL_DOMAINS
from app.foundry.campaign import (
    PilotBaseline,
    prepare_campaign_scenarios,
    run_campaign,
)
from app.foundry.pilot import SyntheticFoundryProvider, run_pilot
from app.llm.base import CompletionResult, EmbeddingRequest, Usage
from app.llm.client import LLMClient, LLMConfig
from app.llm.mock import MockProvider
from app.models.episodes import Episode
from app.models.foundry import Source

CFG = get_config()
FAST_LLM = LLMConfig(max_retries=0, timeout_s=5.0, retry_backoff_s=0.0)


def _embed():
    p = MockProvider(embed_dim=64)
    return lambda texts: p.embed(EmbeddingRequest(inputs=texts, model="e")).vectors


def _client(provider=None):
    return LLMClient(provider or SyntheticFoundryProvider(), FAST_LLM)


def _baseline(db_session, run_id="basepilot") -> PilotBaseline:
    """소규모 Pilot을 돌려 기준선(합의도·reject율·단가)을 만든다."""
    res = run_pilot(
        db_session, n=30, llm_client=_client(), embed_fn=_embed(), config=CFG, run_id=run_id
    )
    return PilotBaseline.from_pilot(res)


# --- degrade provider들 (결정론적) ---


class _NeverReject(SyntheticFoundryProvider):
    """judge가 항상 accept — reject율 0, 합의도 표준(품질 유지 케이스)."""

    def _respond(self, prompt, h):
        if "Domain Judge" in prompt:
            return {"verdict": "accept", "reason_code": None, "note": "ok"}
        return super()._respond(prompt, h)


class _AlwaysReject(SyntheticFoundryProvider):
    """judge가 항상 reject — reject율 1.0 (기준선보다 크게 상승)."""

    def _respond(self, prompt, h):
        if "Domain Judge" in prompt:
            return {"verdict": "reject", "reason_code": "IMPLAUSIBLE_FIELD", "note": "x"}
        return super()._respond(prompt, h)


class _LowConsensus(_NeverReject):
    """analyst가 균등 가중치 — 합의도 ~0.34 (기준선보다 크게 하락). reject는 격리(accept)."""

    def _respond(self, prompt, h):
        if "Intent Analyst" in prompt:
            a, b, c = self._intents[0], self._intents[1], self._intents[2]
            return {
                "candidates": [
                    {"intent_id": a, "weight": 0.34, "rationale": "x"},
                    {"intent_id": b, "weight": 0.33, "rationale": "y"},
                    {"intent_id": c, "weight": 0.33, "rationale": "z"},
                ]
            }
        return super()._respond(prompt, h)


class _Costly(_NeverReject):
    """모든 완성 호출 토큰을 10배로 — 시도당 단가가 기준선을 크게 초과."""

    def complete(self, request) -> CompletionResult:
        r = super().complete(request)
        u = Usage(
            prompt_tokens=r.usage.prompt_tokens * 10,
            completion_tokens=r.usage.completion_tokens * 10,
        )
        return CompletionResult(
            text=r.text, model=r.model, provider=r.provider, usage=u, cost_usd=r.cost_usd
        )


# --- AC 1: 도메인 배분 (DOCUMENT+VISUAL 우선) ---


def test_campaign_allocation_prioritizes_document_visual(db_session) -> None:
    sched = prepare_campaign_scenarios(db_session, run_id="alloc01", config=CFG, target_n=200)
    alloc = sched.allocation
    assert set(alloc.keys()) == set(CANONICAL_DOMAINS)  # 7개 도메인 전부
    top2 = sorted(alloc, key=alloc.__getitem__, reverse=True)[:2]
    assert set(top2) == {"DOCUMENT", "VISUAL"}  # 최상위 두 도메인
    for d, w in CFG.campaign.domain_weights.items():  # config 가중치 반영 (근사)
        assert alloc[d] == pytest.approx(w, abs=0.02)
    assert len(sched.scenarios) == 200  # 슬롯 스케줄 길이 == target_n
    assert len(sched.slot_domains) == 200


def test_campaign_allocation_sums_to_one(db_session) -> None:
    sched = prepare_campaign_scenarios(db_session, run_id="alloc02", config=CFG, target_n=137)
    assert sum(sched.allocation.values()) == pytest.approx(1.0)
    assert len(sched.scenarios) == 137  # 임의 N도 정확히 채운다


# --- AC 2: 주간 품질 리포트 + AC 3: 품질 유지 시 목표 도달 ---


def test_campaign_reaches_target_when_quality_holds(db_session) -> None:
    baseline = _baseline(db_session)
    report = run_campaign(
        db_session, run_id="camp_ok", target_n=40, llm_client=_client(_NeverReject()),
        embed_fn=_embed(), config=CFG, baseline=baseline, batch_size=5,
    )
    assert report.stopped is False
    assert report.batch_report.created == 40  # 자동중단 없이 목표 도달
    assert len(report.windows) >= 1
    assert all(not w.degraded for w in report.windows)
    # generate_episode 상속 — 전부 BRONZE/SILVER (GOLD 생성 안 함), 합성 provenance
    rows = list(db_session.query(Episode).filter(Episode.episode_id.like("EP_camp_ok_%")))
    assert {e.reliability_tier for e in rows} <= {"BRONZE", "SILVER"}
    assert all(e.origin_channel == "FOUNDRY_SYNTHETIC" for e in rows)


def test_campaign_weekly_report_has_metrics(db_session) -> None:
    baseline = _baseline(db_session)
    report = run_campaign(
        db_session, run_id="camp_rep", target_n=40, llm_client=_client(_NeverReject()),
        embed_fn=_embed(), config=CFG, baseline=baseline, batch_size=5,
    )
    w = report.windows[0]
    d = w.as_dict()
    for key in (
        "week_index", "mean_consensus", "reject_rate", "unit_tokens", "unit_cost",
        "consensus_delta", "reject_delta", "unit_tokens_ratio", "degraded", "reasons",
    ):
        assert key in d, key
    assert 0 <= w.mean_consensus <= 1
    assert 0 <= w.reject_rate <= 1
    assert w.unit_tokens > 0  # 단가는 관측된다 (토큰>0)
    rd = report.as_dict()  # 캠페인 리포트도 직렬화 가능
    assert rd["stopped"] is False
    assert "baseline" in rd and "windows" in rd and "allocation" in rd


# --- AC 3: 악화 시 자동 중단 ---


def test_campaign_auto_stops_on_reject_rise(db_session) -> None:
    baseline = _baseline(db_session)
    report = run_campaign(
        db_session, run_id="camp_rej", target_n=60, llm_client=_client(_AlwaysReject()),
        embed_fn=_embed(), config=CFG, baseline=baseline, batch_size=5,
    )
    assert report.stopped is True
    assert report.batch_report.created < 60  # 목표 도달 전 중단
    degraded = [w for w in report.windows if w.degraded]
    assert degraded and "reject_rise" in degraded[0].reasons


def test_campaign_auto_stops_on_consensus_drop(db_session) -> None:
    baseline = _baseline(db_session)
    report = run_campaign(
        db_session, run_id="camp_con", target_n=60, llm_client=_client(_LowConsensus()),
        embed_fn=_embed(), config=CFG, baseline=baseline, batch_size=5,
    )
    assert report.stopped is True
    degraded = [w for w in report.windows if w.degraded]
    assert degraded and "consensus_drop" in degraded[0].reasons


def test_campaign_auto_stops_on_unit_cost_rise(db_session) -> None:
    baseline = _baseline(db_session)  # 정상 단가
    report = run_campaign(
        db_session, run_id="camp_cost", target_n=60, llm_client=_client(_Costly()),
        embed_fn=_embed(), config=CFG, baseline=baseline, batch_size=5,
    )
    assert report.stopped is True
    degraded = [w for w in report.windows if w.degraded]
    assert degraded and "unit_cost_rise" in degraded[0].reasons


def test_campaign_subwindow_degradation_surfaces_in_degraded_flag(db_session) -> None:
    """리뷰 F1: 배치 < window_batches면 윈도가 안 닫혀 stopped를 못 켜지만, 악화는 degraded로
    드러나야 한다 (CLI exit code의 근거). 부분 윈도 악화도 마찬가지."""
    baseline = _baseline(db_session)
    # batch_size=5, window_batches(config)=4 → n=10이면 배치 2개 < 4 → 완전 윈도 없음
    report = run_campaign(
        db_session, run_id="camp_sub", target_n=10, llm_client=_client(_AlwaysReject()),
        embed_fn=_embed(), config=CFG, baseline=baseline, batch_size=5,
    )
    assert report.stopped is False          # 멈출 완전 윈도가 없었다
    assert report.batch_report.created == 10  # 전량 생성됨(조기중단 불가)
    assert report.degraded is True          # 그래도 악화 신호는 드러난다
    assert any(w.degraded for w in report.windows)


def test_campaign_does_not_touch_brightness() -> None:
    """캠페인은 데이터 생성만 — 노드 brightness는 Arena만 갱신 (절대 규칙 3).

    구조적 보장: 캠페인 모듈은 brain 노드 모델을 import하지 않으므로 brightness를 쓸 수 없다.
    (docstring이 'brightness'를 언급하므로 대입/접근 토큰으로 검사한다.)
    """
    import app.foundry.campaign as camp_mod

    with open(camp_mod.__file__, encoding="utf-8") as f:
        body = f.read()
    assert "app.models.brain" not in body  # 노드 모델 미import
    assert "brightness =" not in body       # brightness 대입 없음
    assert ".brightness" not in body         # 노드 brightness 접근 없음


# --- 재시작 멱등 (10k+ 내구성) ---


def test_campaign_restart_creates_no_duplicates(db_session) -> None:
    baseline = _baseline(db_session)
    kw = dict(llm_client=_client(_NeverReject()), embed_fn=_embed(), config=CFG,
              baseline=baseline, batch_size=5)
    run_campaign(db_session, run_id="camp_re", target_n=20, **kw)
    first = db_session.query(Episode).filter(Episode.episode_id.like("EP_camp_re_%")).count()
    assert first == 20
    sources_after_first = db_session.query(Source).count()

    report2 = run_campaign(db_session, run_id="camp_re", target_n=20, **kw)
    assert report2.batch_report.created == 0  # 전량 스킵
    assert report2.batch_report.skipped_existing == 20
    again = db_session.query(Episode).filter(Episode.episode_id.like("EP_camp_re_%")).count()
    assert again == 20  # 중복 생성 0
    # 리뷰 F3: 전량 완료 재시작은 prepare를 건너뛰어 orphan 소스·시나리오를 만들지 않는다
    assert db_session.query(Source).count() == sources_after_first
    assert report2.degraded is False  # no-op 리포트도 정상 신호
    assert report2.allocation  # 배분은 DB 없이도 보고된다


def test_baseline_from_run_restores_from_db(db_session) -> None:
    """★ 재개 기준선: run의 DB 실측(합의도·reject율) 복원 — 없는 run은 거부 (감사 후속)."""
    from app.foundry.campaign import baseline_from_run
    from app.models.episodes import Episode

    cases = [("LABEL_CANDIDATE", 0.8), ("LABEL_CANDIDATE", 0.6), ("REJECTED", None)]
    for i, (state, cons) in enumerate(cases):
        db_session.add(Episode(
            episode_id=f"EP_run_resume_x_{i:05d}", ontology_version="onto-test", lang="ko",
            dataset_split="TRAIN", origin_channel="FOUNDRY_SYNTHETIC",
            episode_creator_type="FOUNDRY_PIPELINE", primary_subject_type="TEACHER",
            teacher_prompt=f"재개 발화 {i}", label_distribution={}, consensus=cons,
            label_state=state, reliability_tier="SILVER" if state != "REJECTED" else "BRONZE",
        ))
    db_session.flush()

    b = baseline_from_run(db_session, "run_resume_x")
    assert abs(b.mean_consensus - 0.7) < 1e-9
    assert abs(b.reject_rate - 1 / 3) < 1e-9
    assert b.unit_tokens == 0.0  # 비용 기준선 없음 — 0 가드로 비용 게이트 스킵

    with pytest.raises(ValueError, match="에피소드 0건"):
        baseline_from_run(db_session, "run_ghost")


def test_baseline_from_run_excludes_pilot_base(db_session) -> None:
    """재개 기준선은 캠페인 실측만 — 파일럿(run_id_base) 에피소드는 오포함 금지(적대 검증)."""
    from app.foundry.campaign import baseline_from_run
    from app.models.episodes import Episode

    cases = [
        ("EP_run_rsx2_00000", 0.8),
        ("EP_run_rsx2_base_00000", 0.0),  # 파일럿 — 섞이면 평균이 왜곡된다
    ]
    for eid, cons in cases:
        db_session.add(Episode(
            episode_id=eid, ontology_version="onto-test", lang="ko",
            dataset_split="TRAIN", origin_channel="FOUNDRY_SYNTHETIC",
            episode_creator_type="FOUNDRY_PIPELINE", primary_subject_type="TEACHER",
            teacher_prompt=f"기준선 {eid}", label_distribution={}, consensus=cons,
            label_state="LABEL_CANDIDATE", reliability_tier="SILVER",
        ))
    db_session.flush()
    b = baseline_from_run(db_session, "run_rsx2")
    assert abs(b.mean_consensus - 0.8) < 1e-9  # base(0.0)가 섞였다면 0.4가 됐을 것
