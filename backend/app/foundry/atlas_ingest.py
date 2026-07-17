"""수동 원문 → Atlas 채굴 주입구 (§2 원료) — S1 등록 + S2 저장 + S4 채굴을 한 번에.

2026-07-17 감사: Atlas가 완전 미가동(entries 0)이었다 — S4는 코드만 있고 파이프라인이
안 불렀다. 이 모듈이 원료 주입구다: 운영자가 실제 교사 언어 원문(커뮤니티 Q&A 발췌 등)을
넣으면 줄 단위로 S4(LLM)가 표현 패턴을 패러프레이즈해 Atlas에 적재한다.

- 절대 규칙 7(TRANSFORM_ONLY): 원문은 S2 raw 저장까지만. Atlas에는 패러프레이즈 대표형만
  들어가며, 원문과 임베딩 유사도 > paraphrase_max면 폐기된다(mine_atlas_entry 가드).
- Atlas가 자라면 그때부터 S6 재보정 통계·coverage 확장 큐가 자동으로 살아난다(batch 배선).
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field

from sqlalchemy.orm import Session

from app.core.config import ExperimentsConfig
from app.foundry.agents.runner import render_agent_prompt, run_json_agent
from app.foundry.prompts import load_prompt
from app.foundry.stages.s1_discovery import SourceCandidate, register_source
from app.foundry.stages.s2_governance import govern_source, store_raw_document
from app.foundry.stages.s4_language_miner import (
    AtlasInput,
    EmbedFn,
    ParaphraseTooSimilar,
    mine_atlas_entry,
)
from app.llm.client import LLMClient

logger = logging.getLogger(__name__)

PROMPT_S4 = load_prompt("s4_language_miner")


@dataclass
class IngestReport:
    source_id: str
    attempted: int = 0
    mined: int = 0
    discarded_similar: int = 0   # 패러프레이즈 가드 폐기 (원문 잔존 위험)
    failed: int = 0              # LLM 계약 위반 등 — 줄 단위 격리
    errors: list[str] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "source_id": self.source_id, "attempted": self.attempted, "mined": self.mined,
            "discarded_similar": self.discarded_similar, "failed": self.failed,
            "errors": self.errors[:5],
        }


def mine_text(
    session: Session,
    *,
    llm_client: LLMClient,
    embed_fn: EmbedFn,
    config: ExperimentsConfig,
    text: str,
    title: str,
    source_class: str = "TEACHER_LANGUAGE",
    model: str = "s4",
) -> IngestReport:
    """원문 텍스트를 줄 단위로 S4 채굴해 Atlas에 적재한다 (줄당 LLM 1회).

    한 줄의 실패가 전체를 죽이지 않는다(줄 단위 격리 — 에피소드 실패 허용과 같은 철학).
    """
    source = register_source(session, SourceCandidate(
        source_class=source_class, title=title,
        discovery_reason="수동 원문 채굴(atlas_ingest) — 교사 표현 패턴 원료",
        access="manual_ingest",
    ))
    govern_source(session, source.source_id, "ALLOW", reviewed_by="atlas_ingest")
    store_raw_document(session, source.source_id, text)

    report = IngestReport(source_id=source.source_id)
    for line in (ln.strip() for ln in text.splitlines()):
        if not line:
            continue
        report.attempted += 1
        try:
            atlas = run_json_agent(
                llm_client,
                render_agent_prompt(PROMPT_S4, {"raw_text": line, "source_class": source_class}),
                model,
                AtlasInput,
            )
            mine_atlas_entry(
                session, raw_text=line, atlas=atlas, embed_fn=embed_fn, config=config
            )
            report.mined += 1
        except ParaphraseTooSimilar as exc:
            report.discarded_similar += 1
            logger.info("패러프레이즈 가드 폐기: %s", exc)
        except Exception as exc:  # noqa: BLE001 — 줄 단위 격리, 채굴은 계속
            report.failed += 1
            report.errors.append(f"{type(exc).__name__}: {exc}"[:200])
            logger.warning("S4 채굴 실패(줄 격리): %s", exc)
    session.flush()
    return report
