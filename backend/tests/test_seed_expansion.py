"""씨드 확장 AC — 최소기준을 채운 씨드를 앵커로 LLM이 변형을 생성 (2026-07-17 사용자 요청).

"씨드가 요구(최소기준)대로 채워지면 그 씨드가 확장되게" —
- 최소기준(expansion_unmet): 카드 ≥1 · 사진↔사진서술 정합 · 선택 수 ≤ 화면 카드 수
- 확장 출력은 §1-S5 계약 그대로(ScenarioWorkspaceState) + 씨드 어휘 안에서만 — 위반은 거부
- 확장이 실패해도 증산은 죽지 않는다: 씨드 원본(pick_variants)으로 폴백
"""
from sqlalchemy import select

from app.core.config import get_config
from app.foundry.pilot import SyntheticFoundryProvider
from app.foundry.seed_expansion import (
    SeedExpansionError,
    expand_variants,
    variants_for_domain,
)
from app.foundry.situation_seeds import (
    expansion_unmet,
    load_situation_seeds,
    pick_variants,
)
from app.foundry.stages.s5_situation_builder import ScenarioWorkspaceState
from app.llm.client import LLMClient, LLMConfig
from app.models.foundry import CanonicalScenario

CFG = get_config()
FAST_LLM = LLMConfig(max_retries=0, timeout_s=5.0, retry_backoff_s=0.0)


def _client(provider=None):
    return LLMClient(provider or SyntheticFoundryProvider(), FAST_LLM)


def _strip_nulls(d):
    """저장분은 명시적 null 포함 덤프(기존 유일문) — vs-1.0 재검증 전 걷어낸다."""
    if isinstance(d, dict):
        return {k: _strip_nulls(v) for k, v in d.items() if v is not None}
    if isinstance(d, list):
        return [_strip_nulls(v) for v in d]
    return d


def _ready_anchor(domain="PLAY"):
    sf = load_situation_seeds()
    for seed in sf.seeds:
        in_domain = not seed.domains or domain in seed.domains
        if in_domain and not expansion_unmet(seed.workspace_state):
            return sf, seed
    raise AssertionError(f"{domain}에 최소기준을 채운 씨드가 없음 — 실파일 점검")


# --- 최소기준 판정 ---


def test_expansion_unmet_flags_incoherent_seed() -> None:
    """사진↔서술 불일치·과다 선택은 미달 사유로 나온다(확장 부적격)."""
    sf = load_situation_seeds()
    base = next(s for s in sf.seeds if s.workspace_state.objects_summary.get("photo"))
    ws = base.workspace_state

    assert expansion_unmet(ws) == []  # 실파일 씨드는 기준 충족

    no_vs = ws.model_copy(update={"visual_semantics": []})
    assert any("사진 서술" in m for m in expansion_unmet(no_vs))

    over_select = ws.model_copy(update={
        "selection": {"type": "photo", "count": ws.objects_summary["photo"] + 5}
    })
    assert any("선택" in m for m in expansion_unmet(over_select))

    empty = ws.model_copy(update={"objects_summary": {}, "visual_semantics": [], "selection": {}})
    assert any("카드가 하나도" in m for m in expansion_unmet(empty))


def test_real_seed_file_has_expansion_ready_seed_per_domain() -> None:
    """★ 8개 도메인 모두 확장 가능한 씨드가 최소 1개 — '채우면 확장된다' 약속의 전제."""
    from app.core.ontology import CANONICAL_DOMAINS

    sf = load_situation_seeds()
    for domain in CANONICAL_DOMAINS:
        ready = [
            s for s in sf.seeds
            if (not s.domains or domain in s.domains) and not expansion_unmet(s.workspace_state)
        ]
        assert ready, f"도메인 {domain}에 확장 가능한 씨드가 없음"


# --- 확장 계약 ---


def test_expand_variants_returns_k_contract_valid_variants() -> None:
    """★ 확장 출력 k개 전부: §1-S5 스키마 + 씨드 어휘 + 최소기준 정합을 통과한다."""
    sf, anchor = _ready_anchor("PLAY")
    k = CFG.foundry.scenario_variants
    out = expand_variants(
        _client(), anchor=anchor, vocabulary=sf.vocabulary, k=k, domain="PLAY", model="s5-test"
    )
    assert len(out) == k
    for v in out:
        ws = ScenarioWorkspaceState.model_validate(v)  # 계약 재검증(§1-S5 유일문과 동일)
        assert ws.surface_type in sf.vocabulary.surface_types
        assert set(ws.recent_actions) <= set(sf.vocabulary.actions)
        assert set(ws.objects_summary) <= set(sf.vocabulary.object_kinds)
        assert expansion_unmet(ws) == []


def test_expand_rejects_out_of_vocabulary_variant() -> None:
    """어휘 밖 행동을 섞으면 거부 — 확장이 조용히 어휘를 오염시키지 못한다."""

    class _OffVocab(SyntheticFoundryProvider):
        def _respond(self, prompt, h):
            out = super()._respond(prompt, h)
            if "Situation Builder" in prompt:
                out["variants"][0]["recent_actions"] = ["teleport"]
            return out

    sf, anchor = _ready_anchor("PLAY")
    try:
        expand_variants(
            _client(_OffVocab()), anchor=anchor, vocabulary=sf.vocabulary,
            k=CFG.foundry.scenario_variants, domain="PLAY", model="s5-test",
        )
        raise AssertionError("어휘 밖 변형이 통과함")
    except SeedExpansionError as exc:
        assert "teleport" in str(exc)


def test_expand_rejects_wrong_variant_count() -> None:
    """변형 수 ≠ k면 거부 — §1-S5 '정확히 scenario_variants개' 계약."""

    class _ShortCount(SyntheticFoundryProvider):
        def _respond(self, prompt, h):
            out = super()._respond(prompt, h)
            if "Situation Builder" in prompt:
                out["variants"] = out["variants"][:1]
            return out

    sf, anchor = _ready_anchor("PLAY")
    try:
        expand_variants(
            _client(_ShortCount()), anchor=anchor, vocabulary=sf.vocabulary,
            k=CFG.foundry.scenario_variants, domain="PLAY", model="s5-test",
        )
        raise AssertionError("변형 수 위반이 통과함")
    except SeedExpansionError as exc:
        assert "변형" in str(exc)


# --- 폴백: 확장이 죽어도 증산은 계속 ---


def test_variants_for_domain_falls_back_to_verbatim_on_failure() -> None:
    """확장 실패 시 같은 salt의 씨드 원본과 동일한 변형을 반환한다(증산 무중단)."""

    class _Broken(SyntheticFoundryProvider):
        def _respond(self, prompt, h):
            if "Situation Builder" in prompt:
                return {"boom": True}  # 계약 위반 — 교정 재시도로도 구제 불가
            return super()._respond(prompt, h)

    sf = load_situation_seeds()
    k = CFG.foundry.scenario_variants
    got = variants_for_domain(
        sf, domain="VISUAL", k=k, salt="run_fb|VISUAL",
        llm_client=_client(_Broken()), model="s5-test", enabled=True,
    )
    assert got == pick_variants(sf, domain="VISUAL", k=k, salt="run_fb|VISUAL")


def test_variants_for_domain_disabled_never_calls_llm() -> None:
    """config로 끄면 LLM을 아예 부르지 않는다(비용 0 보장)."""
    calls = {"n": 0}

    class _Counting(SyntheticFoundryProvider):
        def complete(self, request):
            calls["n"] += 1
            return super().complete(request)

    sf = load_situation_seeds()
    k = CFG.foundry.scenario_variants
    got = variants_for_domain(
        sf, domain="PLAY", k=k, salt="run_off|PLAY",
        llm_client=_client(_Counting()), model="s5-test", enabled=False,
    )
    assert calls["n"] == 0
    assert got == pick_variants(sf, domain="PLAY", k=k, salt="run_off|PLAY")


# --- 증산 본선 배선 ---


def test_campaign_prepare_expands_with_llm(db_session) -> None:
    """★ campaign 준비가 확장 경로를 실제로 타고, 적재분 전부가 계약·어휘를 지킨다."""
    from app.foundry.campaign import prepare_campaign_scenarios

    s5_calls = {"n": 0}

    class _Watch(SyntheticFoundryProvider):
        def complete(self, request):
            if "Situation Builder" in request.prompt:
                s5_calls["n"] += 1
            return super().complete(request)

    target = CFG.foundry.scenario_variants * 2
    sched = prepare_campaign_scenarios(
        db_session, run_id="run_seed_exp", config=CFG, target_n=target,
        llm_client=_client(_Watch()), model="s5-test",
    )
    assert s5_calls["n"] > 0, "확장 LLM 호출이 없었음 — 배선 누락"
    assert len(sched.scenarios) == target

    sf = load_situation_seeds()
    ids = {s[0] for s in sched.scenarios}
    rows = db_session.scalars(
        select(CanonicalScenario).where(CanonicalScenario.scenario_id.in_(ids))
    ).all()
    assert rows
    for r in rows:
        ws = ScenarioWorkspaceState.model_validate(_strip_nulls(r.workspace_state))
        assert ws.surface_type in sf.vocabulary.surface_types
        assert set(ws.recent_actions) <= set(sf.vocabulary.actions)


def test_expand_coherence_violation_recovered_by_corrective_retry() -> None:
    """★ 실측 유형(2026-07-17): 정합 위반(선택>카드)은 교정 재시도 1회로 구제된다."""

    class _OneShotIncoherent(SyntheticFoundryProvider):
        def _respond(self, prompt, h):
            out = super()._respond(prompt, h)
            if "Situation Builder" in prompt and "교정 지시" not in prompt:
                out["variants"][0]["selection"] = {"type": "photo", "count": 99}  # 카드보다 많음
            return out

    sf, anchor = _ready_anchor("PLAY")
    got = expand_variants(
        _client(_OneShotIncoherent()), anchor=anchor, vocabulary=sf.vocabulary,
        k=CFG.foundry.scenario_variants, domain="PLAY", model="s5-test",
    )
    assert len(got) == CFG.foundry.scenario_variants  # 재시도가 구제 — 폴백까지 안 감
