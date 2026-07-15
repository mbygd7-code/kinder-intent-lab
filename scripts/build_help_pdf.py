#!/usr/bin/env python3
"""도움말 통합 안내서 HTML → PDF (헤드리스 Chromium 인쇄).

소스: docs/09-teacher-guide/help-booklet.html (화면 도움말 4탭의 미러 — 함께 갱신).
출력: docs/09-teacher-guide/킨더브레인-도움말.pdf

이 저장소엔 PDF 라이브러리가 없다(reportlab·weasyprint 등 미설치). 대신 Windows에 항상 있는
Edge(또는 Chrome)의 `--headless --print-to-pdf`로 렌더한다 — 무설치이고, 한글(맑은 고딕)·
이모지(Segoe UI Emoji)·HTML 표를 시스템 폰트로 네이티브 렌더한다.

사용:
  python scripts/build_help_pdf.py            # 기본 소스→기본 출력
  python scripts/build_help_pdf.py --open     # 렌더 후 파일 열기(Windows)
"""
import argparse
import subprocess
import sys
import tempfile
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.stdout.reconfigure(encoding="utf-8")

DEFAULT_SRC = _ROOT / "docs" / "09-teacher-guide" / "help-booklet.html"
DEFAULT_OUT = _ROOT / "docs" / "09-teacher-guide" / "킨더브레인-도움말.pdf"

# Windows 표준 설치 경로 — PATH에 없으므로 전체 경로로 호출한다.
_BROWSER_CANDIDATES = [
    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    r"C:\Program Files\Google\Chrome\Application\chrome.exe",
    r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
]


def _find_browser() -> Path:
    for p in _BROWSER_CANDIDATES:
        if Path(p).exists():
            return Path(p)
    raise SystemExit(
        "Edge/Chrome 실행 파일을 찾지 못했습니다. 아래 경로 중 하나에 있어야 합니다:\n  "
        + "\n  ".join(_BROWSER_CANDIDATES)
    )


def build(src: Path, out: Path) -> Path:
    if not src.exists():
        raise SystemExit(f"소스 HTML이 없습니다: {src}")
    browser = _find_browser()
    out.parent.mkdir(parents=True, exist_ok=True)
    if out.exists():
        out.unlink()  # 이전 산출물 제거 — '갱신 안 됨'을 성공으로 오인하지 않게

    # 헤드리스는 격리 프로필이 필요할 수 있어 임시 user-data-dir 부여.
    with tempfile.TemporaryDirectory(prefix="kib-pdf-") as profile:
        cmd = [
            str(browser),
            "--headless=new",
            "--disable-gpu",
            "--no-first-run",
            "--no-default-browser-check",
            f"--user-data-dir={profile}",
            "--no-pdf-header-footer",  # 머리글/바닥글(URL·페이지번호) 제거
            "--virtual-time-budget=6000",  # 폰트·레이아웃 안정화 대기(ms)
            f"--print-to-pdf={out}",
            src.as_uri(),  # file:// 절대경로 — 상대경로·CORS 회피
        ]
        # Edge stderr는 UTF-8 — Windows 콘솔 기본(cp949)로 디코드하면 깨지므로 명시.
        proc = subprocess.run(
            cmd, capture_output=True, encoding="utf-8", errors="replace", timeout=120
        )

    if not out.exists() or out.stat().st_size < 5_000:
        raise SystemExit(
            f"PDF 생성 실패 (exit={proc.returncode}). stderr:\n{(proc.stderr or '')[:2000]}"
        )
    print(f"OK — {out}  ({out.stat().st_size:,} bytes, {browser.name})")
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="도움말 HTML → PDF (헤드리스 Chromium)")
    ap.add_argument("--src", type=Path, default=DEFAULT_SRC)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    ap.add_argument("--open", action="store_true", help="렌더 후 파일 열기(Windows)")
    args = ap.parse_args()
    out = build(args.src, args.out)
    if args.open:
        import os

        os.startfile(out)  # noqa: S606 — 로컬 개발 편의
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
