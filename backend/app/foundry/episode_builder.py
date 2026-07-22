"""S6~S11 에피소드 생성 — pilot·batch 러너가 공유하는 단일 체인 (§1-S6~S11).

한 시나리오·persona에서 발화 생성(dedup 재시도) → 분석 → 회의 → 판정 → 합의 → tier 산출까지.
Episode/Evidence 객체를 만들어 반환하되 session에 add하지 않는다(러너가 배치로 적재).
"""
from __future__ import annotations

from dataclasses import dataclass

from app.aggregator.aggregator import EvidenceSignal, aggregate, recommend_tier
from app.core.config import ExperimentsConfig
from app.foundry.stages.s6_simulator import simulate
from app.foundry.stages.s7_analyst import analyze
from app.foundry.stages.s8_skeptic import ConfusionPair, challenge
from app.foundry.stages.s9_judge import judge
from app.foundry.stages.s10_consensus import build_consensus
from app.llm.client import LLMClient
from app.models.episodes import Episode, Evidence


class DedupExhausted(RuntimeError):
    """발화 dedup 재시도를 소진 — provider 다양성 부족."""


@dataclass
class GeneratedEpisode:
    episode: Episode
    evidences: list[Evidence]
    pairs: list[ConfusionPair]
    accepted: bool
    consensus_score: float


def generate_episode(
    llm_client: LLMClient,
    *,
    config: ExperimentsConfig,
    run_id: str,
    index: int,
    scenario_id: str,
    persona: str,
    ontology_version: str,
    deduper,
    model: str = "foundry",
    dedup_hash: str | None = None,
    atlas_stats: dict | None = None,
    workspace_state: dict | None = None,
) -> GeneratedEpisode:
    """S6~S11로 에피소드 1건을 만든다. dedup 폐기 시 nonce를 바꿔 재생성한다.

    atlas_stats: Atlas 재보정 통계(§2-3 소비처 1) — 있으면 S6 컨텍스트에 실린다.
    비었으면 아예 생략한다(0짜리 통계로 Simulator를 오도하지 않는다).

    workspace_state: 시나리오의 화면 상태(§1-S6 "scenario에서 발화가 나온다" ·
    §1-S7 "(발화 + scenario)"). 2026-07-22 실측: 이게 빠지면 발화가 화면 무관
    초애매형으로 굳고 Analyst가 발화만 보고 판단한다(camp_1b802fdf 94% UNKNOWN).
    도메인·정답성 메타는 절대 싣지 않는다 — 역방향 생성 금지(§1-S6)와 같은 정신.
    """
    max_retries = config.foundry.max_dedup_retries
    base_nonce = index * (max_retries + 1)

    utt = None
    for attempt in range(max_retries + 1):
        context: dict = {"nonce": base_nonce + attempt}
        if workspace_state:
            context["workspace"] = workspace_state
        if atlas_stats:
            context["atlas_stats"] = atlas_stats
        candidate = simulate(
            llm_client, scenario_id=scenario_id, persona_lens=persona, model=model,
            scenario_context=context,
        )
        if not deduper.is_duplicate(candidate.utterance):
            utt = candidate
            break
    if utt is None:
        raise DedupExhausted(
            f"발화 dedup 재시도 {max_retries}회 소진 (index {index})"
        )

    candidates = analyze(
        llm_client, utterance=utt.utterance, scenario_id=scenario_id, model=model,
        scenario_context={"workspace": workspace_state} if workspace_state else None,
    )
    pairs = challenge(
        llm_client, utterance=utt.utterance, scenario_id=scenario_id,
        candidates=[c.intent_id for c in candidates], model=model,
    )
    verdict = judge(
        llm_client, utterance=utt.utterance, scenario_id=scenario_id,
        candidates=[c.intent_id for c in candidates], model=model,
    )
    consensus = build_consensus(candidates, pairs, config)

    # S11 tier — Aggregator 산출 (전부 BRONZE/SILVER, GOLD 없음)
    signals = [
        EvidenceSignal(
            intent_id=consensus.top_intent, polarity="supports",
            strength=consensus.consensus, evidence_type="SYNTHETIC_CONSENSUS",
            actor_type="LLM_ANALYST", reliability=consensus.consensus,
        )
    ]
    if index % 2 == 0:  # 일부는 규칙 신호 추가 → 2 신호(SILVER 후보)
        signals.append(
            EvidenceSignal(
                intent_id=consensus.top_intent, polarity="supports", strength=0.8,
                evidence_type="DOMAIN_RULE", actor_type="RULE_ENGINE", reliability=0.85,
            )
        )
    tier = recommend_tier(aggregate(signals, config), config)
    accepted = verdict.verdict != "reject"

    episode = Episode(
        episode_id=f"EP_{run_id}_{index:05d}", ontology_version=ontology_version, lang="ko",
        dataset_split="TRAIN", reliability_tier=tier,
        label_state="LABEL_CANDIDATE" if accepted else "REJECTED",
        origin_channel="FOUNDRY_SYNTHETIC", episode_creator_type="FOUNDRY_PIPELINE",
        primary_subject_type="SIMULATED_TEACHER", scenario_id=scenario_id,
        teacher_prompt=utt.utterance, persona_lens_used=persona,
        label_distribution=consensus.label_distribution or {"UNKNOWN": 1.0},
        consensus=consensus.consensus, disagreement_pairs=consensus.disagreement_pairs,
        dedup_hash=dedup_hash,
    )
    evidences = [
        Evidence(
            evidence_id=f"EV_{run_id}_{index:05d}_{k}", episode_id=episode.episode_id,
            intent_id=sig.intent_id, polarity=sig.polarity, strength=sig.strength,
            evidence_type=sig.evidence_type, actor_type=sig.actor_type,
            reliability=sig.reliability, adversarial=False,
        )
        for k, sig in enumerate(signals)
    ]
    return GeneratedEpisode(
        episode=episode, evidences=evidences, pairs=pairs,
        accepted=accepted, consensus_score=consensus.consensus,
    )
