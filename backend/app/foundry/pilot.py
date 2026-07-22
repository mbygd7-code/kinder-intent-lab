"""Pilot 500 러너 — S1~S11 E2E, run manifest(계보·토큰·비용), 게이트 리포트 (§1-14).

오프라인 실행: SyntheticFoundryProvider가 프롬프트에서 stage를 감지해 결정론적 JSON을 돌려준다.
Phase 1 게이트: 평균 합의도 ≥ consensus_min ∧ Judge reject ≤ judge_reject_max ∧ kappa ≥
pilot_kappa_min (전부 config). kappa는 사람 스팟 검수 입력이라 미입력이면 판정 보류(None).
"""
from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from dataclasses import dataclass, field

from app.core.config import ExperimentsConfig
from app.core.ontology import CANONICAL_DOMAINS, load_ontology
from app.foundry.agents.runner import AgentOutputError
from app.foundry.atlas import simulator_stats
from app.foundry.episode_builder import generate_episode
from app.foundry.situation_seeds import load_situation_seeds, pick_variants
from app.foundry.stages.s1_discovery import SourceCandidate, register_source
from app.foundry.stages.s2_governance import govern_source, store_raw_document
from app.foundry.stages.s3_extractor import FrameInput, build_situation_frame
from app.foundry.stages.s4_language_miner import cosine_similarity
from app.foundry.stages.s5_situation_builder import build_scenarios
from app.foundry.stages.s8_skeptic import ConfusionPair, record_confusion_edges
from app.llm.base import (
    CompletionResult,
    EmbeddingResult,
    LLMProvider,
    Usage,
)
from app.llm.client import LLMClient
from app.llm.mock import MockProvider
from app.models.episodes import Episode, Evidence

EmbedFn = Callable[[list[str]], list[list[float]]]


# --- 합성 LLM provider (오프라인 파일럿용) ---


class SyntheticFoundryProvider(LLMProvider):
    """프롬프트의 stage 표식을 감지해 결정론적·다양한 stage별 JSON을 반환한다.

    실제 벤더 호출 없음. 발화·라벨을 프롬프트 해시로 변주해 에피소드마다 달라진다(dedup 통과).
    """

    name = "pilot-synth"

    def __init__(self) -> None:
        self._intents = [
            i.intent_id for i in load_ontology().intents if i.intent_id != "UNKNOWN"
        ]
        self._mock = MockProvider()

    @staticmethod
    def _hash(text: str) -> int:
        return int(hashlib.sha256(text.encode("utf-8")).hexdigest(), 16)

    def complete(self, request) -> CompletionResult:
        prompt = request.prompt
        h = self._hash(prompt)
        payload = self._respond(prompt, h)
        text = json.dumps(payload, ensure_ascii=False)
        usage = Usage(
            prompt_tokens=max(1, len(prompt) // 4), completion_tokens=max(1, len(text) // 4)
        )
        return CompletionResult(
            text=text, model=request.model, provider=self.name, usage=usage, cost_usd=0.0
        )

    def embed(self, request) -> EmbeddingResult:
        return self._mock.embed(request)

    def _respond(self, prompt: str, h: int) -> dict:
        n = len(self._intents)
        top = self._intents[h % n]
        runner = self._intents[(h // 7) % n]
        if runner == top:
            runner = self._intents[(h // 7 + 1) % n]
        third = self._intents[(h // 13) % n]

        if "Teacher Language Miner" in prompt:
            return {
                "representative": f"이거 어떻게 하면 좋을까 (패턴 {h % 97})",
                "pattern_cluster": f"PC_{h % 7}",
                "ambiguity_types": ["TARGET_UNSPECIFIED"],
                "possible_intents": [top],
                "resolution_signals": [{"signal": "selection", "note": "화면 선택으로 해소"}],
            }
        if "Situation Builder" in prompt:
            return self._expand_variants(prompt, h)
        if "Teacher Simulator" in prompt:
            return {"utterance": f"이거 좀 해줄 수 있어? (변형 {h % 1_000_000})"}
        if "Intent Analyst" in prompt:
            return {
                "candidates": [
                    {"intent_id": top, "weight": 0.75, "rationale": "우세 해석"},
                    {"intent_id": runner, "weight": 0.15, "rationale": "대안"},
                    {"intent_id": third, "weight": 0.10, "rationale": "약한 후보"},
                ]
            }
        if "Skeptic" in prompt:
            if h % 3 == 0:
                return {"pairs": [{"from_true": top, "to_predicted": runner, "note": "표면 유사"}]}
            return {"pairs": []}
        if "Domain Judge" in prompt:
            if h % 10 == 0:  # ~10% reject (< judge_reject_max)
                return {"verdict": "reject", "reason_code": "IMPLAUSIBLE_FIELD", "note": "낮음"}
            return {"verdict": "accept", "reason_code": None, "note": "현장 개연성 충분"}
        # 알 수 없는 stage — 빈 객체 (실행기가 계약 위반으로 잡는다)
        return {}

    def _expand_variants(self, prompt: str, h: int) -> dict:
        """S5 씨드 확장 응답 — 앵커를 어휘 안에서 결정론 변주(정합 유지: 카드 ≥1·선택 수 1)."""
        body = prompt.rsplit("```json", 1)[1].split("```", 1)[0]
        ctx = json.loads(body)
        anchor = ctx["anchor_workspace_state"]
        actions = ctx["allowed"]["actions"]
        variants = []
        for i in range(ctx["variants_required"]):
            v = json.loads(json.dumps(anchor))
            for key in v["objects_summary"]:
                v["objects_summary"][key] = max(1, v["objects_summary"][key] + (h + i) % 3 - 1)
            v["recent_actions"] = [
                actions[(h + i + j) % len(actions)] for j in range(1 + (h + i) % 2)
            ]
            sel = v.get("selection") or {}
            if sel.get("type"):
                v["selection"] = {} if (h + i) % 2 == 0 else {"type": sel["type"], "count": 1}
            variants.append(v)
        return {"variants": variants}


# --- Run manifest ---


@dataclass
class RunManifest:
    run_id: str
    source_ids: list[str] = field(default_factory=list)
    frame_source: dict[str, str] = field(default_factory=dict)     # frame → source
    scenario_frame: dict[str, str] = field(default_factory=dict)   # scenario → frame
    episode_scenario: dict[str, str] = field(default_factory=dict) # episode → scenario
    episode_tokens: dict[str, int] = field(default_factory=dict)
    episode_cost: dict[str, float] = field(default_factory=dict)

    def trace_source(self, episode_id: str) -> str | None:
        """episode → scenario → frame → source 로 원천 소스를 역추적."""
        scenario = self.episode_scenario.get(episode_id)
        frame = self.scenario_frame.get(scenario) if scenario else None
        return self.frame_source.get(frame) if frame else None

    def total_tokens(self) -> int:
        return sum(self.episode_tokens.values())

    def total_cost(self) -> float:
        return sum(self.episode_cost.values())


# --- 게이트 리포트 ---


@dataclass
class GateReport:
    """Phase 1 게이트 리포트.

    mean_consensus는 '출하되는(채택된) 에피소드의 평균 합의도', judge_reject_rate는
    '전체 대비 reject 비율'이다 — 서로 다른 모집단(채택분 품질 vs 전체 폐기율)을 본다.
    """

    episodes: int
    mean_consensus: float
    judge_reject_rate: float
    human_kappa: float | None
    consensus_min: float
    judge_reject_max: float
    pilot_kappa_min: float

    def passed(self) -> bool | None:
        """3지표 게이트. 자동지표(합의도·reject) 실패는 kappa와 무관하게 확정 실패(False).
        자동지표는 통과했으나 kappa 미입력이면 판정 보류(None)."""
        auto_ok = (
            self.mean_consensus >= self.consensus_min
            and self.judge_reject_rate <= self.judge_reject_max
        )
        if not auto_ok:
            return False
        if self.human_kappa is None:
            return None
        return self.human_kappa >= self.pilot_kappa_min

    def as_dict(self) -> dict:
        return {
            "episodes": self.episodes,
            "mean_consensus": self.mean_consensus,
            "judge_reject_rate": self.judge_reject_rate,
            "human_kappa": self.human_kappa,
            "thresholds": {
                "consensus_min": self.consensus_min,
                "judge_reject_max": self.judge_reject_max,
                "pilot_kappa_min": self.pilot_kappa_min,
            },
            "passed": self.passed(),
        }


@dataclass
class PilotResult:
    manifest: RunManifest
    report: GateReport
    episode_ids: list[str]


# --- 파이프라인 ---


_DEFAULT_PERSONAS = ["P_hypo_1", "P_active_2", "P_struct_3"]


def _default_source_specs() -> list[SourceCandidate]:
    return [
        SourceCandidate(
            source_class="AUTHORITY", title="누리과정 해설서(발췌)",
            discovery_reason="교육 개념 밀도 높음", access="official_corpus",
        ),
        SourceCandidate(
            source_class="PRACTICE", title="놀이사례집(발췌)",
            discovery_reason="상황 프레임 풍부", access="official_corpus",
        ),
        SourceCandidate(
            source_class="TEACHER_LANGUAGE", title="교사 커뮤니티 Q&A(발췌)",
            discovery_reason="교사 언어 밀도 높음", access="public_web",
        ),
    ]


class _Deduper:
    """증분 dedup — 새 발화만 임베딩해 기존 벡터와 최대 유사도를 본다."""

    def __init__(self, embed_fn: EmbedFn, threshold: float) -> None:
        self._embed = embed_fn
        self._threshold = threshold
        self._vectors: list[list[float]] = []

    def is_duplicate(self, utterance: str) -> bool:
        vec = self._embed([utterance])[0]
        dup = any(cosine_similarity(vec, v) >= self._threshold for v in self._vectors)
        if not dup:
            self._vectors.append(vec)
        return dup


def run_pilot(
    session,
    *,
    n: int,
    llm_client: LLMClient,
    embed_fn: EmbedFn,
    config: ExperimentsConfig,
    run_id: str,
    personas: list[str] | None = None,
    source_specs: list[SourceCandidate] | None = None,
    human_kappa: float | None = None,
    model: str = "pilot",
) -> PilotResult:
    """S1~S11 E2E로 n 에피소드를 생성하고 manifest·게이트 리포트를 반환한다."""
    personas = personas or _DEFAULT_PERSONAS
    specs = source_specs or _default_source_specs()
    ontology_version = load_ontology().version
    manifest = RunManifest(run_id=run_id)

    # 호출별 토큰·비용을 에피소드에 귀속시키는 recorder (호출자 recorder는 finally에서 복원)
    call_log: list = []
    prev_recorder = llm_client._recorder  # noqa: SLF001
    llm_client._recorder = call_log.append  # noqa: SLF001 — 파일럿 계측
    try:
        return _run_pilot_body(
            session, n=n, llm_client=llm_client, embed_fn=embed_fn, config=config,
            run_id=run_id, personas=personas, specs=specs, human_kappa=human_kappa,
            model=model, ontology_version=ontology_version, manifest=manifest,
            call_log=call_log,
        )
    finally:
        llm_client._recorder = prev_recorder  # noqa: SLF001


def _run_pilot_body(
    session, *, n, llm_client, embed_fn, config, run_id, personas, specs, human_kappa,
    model, ontology_version, manifest, call_log,
) -> PilotResult:
    # --- S1~S5: 소스 → 프레임 → 시나리오 ---
    seed_file = load_situation_seeds()  # 화면 씨드(수동 작성) — 계약 위반이면 여기서 조기 실패
    scenarios: list[tuple[str, str, str]] = []  # (scenario_id, frame_id, source_id)
    workspace_by_scenario: dict[str, dict] = {}  # 화면 상태 — S6·S7 프롬프트 입력
    for si, spec in enumerate(specs):
        source = register_source(session, spec)
        govern_source(session, source.source_id, "ALLOW", reviewed_by="pilot")
        store_raw_document(session, source.source_id, f"[pilot raw excerpt {si}]")  # S2/S3 입력
        manifest.source_ids.append(source.source_id)

        domain = CANONICAL_DOMAINS[si % len(CANONICAL_DOMAINS)]
        frame = build_situation_frame(
            session,
            FrameInput(
                domain=domain,
                summary=f"소스 {si}에서 추출한 상황 프레임",
                teacher_concern="개입 시점과 방식",
                extraction_confidence=0.8,
            ),
        )
        session.flush()
        manifest.frame_source[frame.frame_id] = source.source_id

        variants = pick_variants(
            seed_file, domain=domain, k=config.foundry.scenario_variants,
            salt=f"{run_id}|{domain}|{si}",
        )
        built = build_scenarios(session, frame, variants, config)
        session.flush()
        for sc in built:
            manifest.scenario_frame[sc.scenario_id] = frame.frame_id
            scenarios.append((sc.scenario_id, frame.frame_id, source.source_id))
            # 화면 상태 수집 — S6·S7 프롬프트 입력(§1-S6·S7). domain은 싣지 않는다
            workspace_by_scenario[sc.scenario_id] = sc.workspace_state

    if not scenarios:
        raise ValueError("생성된 시나리오가 없습니다 (source_specs·scenario_variants 확인)")

    # --- S6~S11: 에피소드 생성 ---
    _stats = simulator_stats(session)  # Atlas 재보정(§2-3) — 비면 컨텍스트 생략
    atlas_stats = (
        {"sample_count": _stats.sample_count,
         "mean_word_length": round(_stats.mean_word_length, 2),
         "deixis_ratio": round(_stats.deixis_ratio, 3)}
        if _stats.sample_count else None
    )
    deduper = _Deduper(embed_fn, config.foundry.dedup_similarity)
    episodes: list[Episode] = []
    evidences: list[Evidence] = []
    all_pairs: list[ConfusionPair] = []
    consensus_scores: list[float] = []
    reject_count = 0
    episode_ids: list[str] = []

    for i in range(n):
        scenario_id, _frame_id, _source_id = scenarios[i % len(scenarios)]
        persona = personas[i % len(personas)]
        log_start = len(call_log)  # dedup 재시도 호출까지 이 에피소드에 귀속 (토큰 유실 방지)

        try:
            gen = generate_episode(
                llm_client, config=config, run_id=run_id, index=i,
                atlas_stats=atlas_stats, scenario_id=scenario_id,
                persona=persona, ontology_version=ontology_version, deduper=deduper, model=model,
                workspace_state=workspace_by_scenario.get(scenario_id),
            )
        except AgentOutputError as exc:
            # 실 LLM의 반복 계약 위반(교정 재시도까지 실패) — 이 에피소드만 버리고 계속 간다.
            # 런 전체를 죽이면 배치 체크포인트·비용이 통째로 유실된다(2026-07-17 실측 크래시).
            # reject_count에 넣지 않는다 — reject_rate는 품질 게이트 신호라 생성 실패와 섞으면
            # 게이트가 오염된다. 실패는 로그로 정직하게 남긴다.
            logging.getLogger("app.foundry.pilot").warning(
                "에피소드 %d 생성 실패(계약 위반 지속) — 건너뜀: %s", i, exc
            )
            continue
        episodes.append(gen.episode)
        evidences.extend(gen.evidences)
        all_pairs.extend(gen.pairs)
        if gen.accepted:
            consensus_scores.append(gen.consensus_score)
        else:
            reject_count += 1

        # manifest 계보 + 토큰·비용 귀속
        episode_id = gen.episode.episode_id
        manifest.episode_scenario[episode_id] = scenario_id
        new_calls = call_log[log_start:]
        manifest.episode_tokens[episode_id] = sum(c.total_tokens for c in new_calls)
        manifest.episode_cost[episode_id] = sum(c.cost_usd for c in new_calls)
        episode_ids.append(episode_id)

    session.add_all(episodes)
    session.add_all(evidences)
    session.flush()
    record_confusion_edges(session, all_pairs)  # dedup 내장

    mean_consensus = (sum(consensus_scores) / len(consensus_scores)) if consensus_scores else 0.0
    reject_rate = (reject_count / len(episode_ids)) if episode_ids else 0.0
    report = GateReport(
        episodes=len(episode_ids),
        mean_consensus=mean_consensus,
        judge_reject_rate=reject_rate,
        human_kappa=human_kappa,
        consensus_min=config.foundry.consensus_min,
        judge_reject_max=config.foundry.judge_reject_max,
        pilot_kappa_min=config.foundry.pilot_kappa_min,
    )
    return PilotResult(manifest=manifest, report=report, episode_ids=episode_ids)
