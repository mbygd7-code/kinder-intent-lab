"""Foundry LLM 프롬프트 — 파일로 관리 (CLAUDE.md 저장소 구조).

프롬프트는 코드가 아니라 .md 파일로 두고 load_prompt로 읽는다 — 버전 관리·리뷰 용이.
"""
from pathlib import Path

_DIR = Path(__file__).resolve().parent


def load_prompt(name: str) -> str:
    """app/foundry/prompts/<name>.md 를 읽어 반환."""
    path = _DIR / f"{name}.md"
    if not path.exists():
        raise FileNotFoundError(f"프롬프트 파일 없음: {path.name}")
    return path.read_text(encoding="utf-8")
