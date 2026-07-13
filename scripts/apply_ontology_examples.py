#!/usr/bin/env python3
"""예시 시트 → 온톨로지 반영 (반복 실행 가능한 편집 루프의 유일한 문).

사용:
  python scripts/apply_ontology_examples.py            # dry-run — 무엇이 바뀌는지 보여만 준다
  python scripts/apply_ontology_examples.py --write    # 온톨로지 파일 갱신 + 버전 minor bump
  python scripts/apply_ontology_examples.py --write --register   # + DB ontology_versions 기록

편집 루프(사람용): seeds/ontology_examples_draft.csv 를 엑셀로 열어
  - '예시 문장' 칸을 고치거나, '빼려면 X' 칸에 X를 적고 저장
  - 이 스크립트를 --write로 실행 → 커밋·푸시 → 재배포되면 강화하기 문제에 반영

계약: **시트가 각 의도의 positive_examples 원본이다.** 시트에 남아 있는(X 아닌) 문장이,
시트에 적힌 순서대로 그 의도의 예시 전부가 된다 — '기존' 줄을 고치면 기존 예시도 바뀐다.
negative_examples·정의·혼동 목록은 시트가 다루지 않으며 그대로 보존한다.

가드(전부 loud-fail — 조용히 넘어가지 않는다):
  - 시트의 의도 집합 == 온톨로지 실제 의도 63개 (UNKNOWN 제외)
  - 의도당 예시 ≥ config.ontology.min_examples_per_side (절대 규칙 1 — 임계는 config)
  - 의도 내 중복, 같은 의도의 negative 예시와 동일 → 거부
  - 의도 간 교차 중복은 **경고**만 — 온톨로지가 맥락 의존 사례("이거 좀 자연스럽게 만들어줘"가
    글/사진 양쪽 예시)를 설계로 담고 있어 강제 금지하면 의미 권위를 침해한다
  - 변경이 있으면 버전 minor bump(onto-X.Y → X.Y+1), 없으면 무변경 no-op(멱등)
  - 반영 후 구조 검증(load_ontology) + 시드 품질 검증(validate_seed_quality) 통과 필수
"""
import argparse
import csv
import re
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT / "backend"))
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

from dotenv import load_dotenv  # noqa: E402

load_dotenv(_ROOT / ".env")

import yaml  # noqa: E402

from app.core.config import get_config  # noqa: E402
from app.core.ontology import (  # noqa: E402
    UNKNOWN_INTENT_ID,
    load_ontology,
    validate_seed_quality,
)

SHEET = _ROOT / "seeds" / "ontology_examples_draft.csv"
SHEET_PUBLIC = _ROOT / "frontend" / "public" / "ontology_examples_draft.csv"
ONTOLOGY = _ROOT / "seeds" / "ontology_v1.yaml"


def read_sheet() -> dict[str, list[str]]:
    """시트 → 의도별 예시 목록(시트 순서, X·빈칸 제외). 헤더는 키워드로 찾는다(열 이동 허용)."""
    with open(SHEET, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    if len(rows) < 2:
        raise SystemExit("시트가 비어 있습니다")
    header = [h.strip() for h in rows[0]]

    def col(pattern: str) -> int:
        for i, h in enumerate(header):
            if re.search(pattern, h):
                return i
        raise SystemExit(f"시트에 '{pattern}' 열이 없습니다 — 헤더: {header}")

    i_id, i_text, i_drop = col(r"의도\s*id"), col(r"예시\s*문장"), col(r"빼려면|삭제|X$")
    out: dict[str, list[str]] = {}
    dropped = 0
    for r in rows[1:]:
        if len(r) <= max(i_id, i_text, i_drop):
            continue
        iid, text = r[i_id].strip(), r[i_text].strip()
        if not iid or not text:
            continue
        if r[i_drop].strip():  # X든 뭐든 표시가 있으면 제외
            dropped += 1
            continue
        out.setdefault(iid, []).append(text)
    print(f"시트: 의도 {len(out)}개 · 예시 {sum(map(len, out.values()))}개 · 제외 표시 {dropped}개")
    return out


def guard(sheet: dict[str, list[str]], onto_data: dict, config) -> None:
    real = {i["intent_id"] for i in onto_data["intents"] if i.get("domain")}
    missing, extra = real - set(sheet), set(sheet) - real
    if missing or extra:
        raise SystemExit(
            f"의도 불일치 — 시트에 없음: {sorted(missing)} / 미지 의도: {sorted(extra)}"
        )

    floor = config.ontology.min_examples_per_side
    owner: dict[str, str] = {}
    negatives = {
        i["intent_id"]: set(i.get("negative_examples") or [])
        for i in onto_data["intents"]
    }
    for iid, examples in sheet.items():
        if len(examples) < floor:
            raise SystemExit(
                f"{iid}: 예시 {len(examples)}개 < 최소 {floor}개 — X를 줄이거나 문장을 추가하세요"
            )
        if len(set(examples)) != len(examples):
            dups = sorted({s for s in examples if examples.count(s) > 1})
            raise SystemExit(f"{iid}: 의도 안에서 중복 문장 — {dups}")
        for s in examples:
            if s in owner:
                # 맥락 의존 문장(양쪽 다 정답일 수 있음) — 설계상 허용되나 퀴즈에선 헷갈리니 알린다
                print(f"⚠ 교차 중복(허용): {owner[s]} ↔ {iid} — {s!r}")
            else:
                owner[s] = iid
            if s in negatives[iid]:
                raise SystemExit(f"{iid}: negative 예시와 동일한 문장 — {s!r} (정답이 뒤집힙니다)")


def bump(version: str) -> str:
    m = re.fullmatch(r"onto-(\d+)\.(\d+)", version)
    if not m:
        raise SystemExit(f"버전 형식을 모릅니다: {version!r}")
    return f"onto-{m.group(1)}.{int(m.group(2)) + 1}"


HEADER_NOTE = (
    "# positive_examples는 seeds/ontology_examples_draft.csv가 원본 — 수정은 시트를 고치고 "
    "scripts/apply_ontology_examples.py --write (직접 편집 금지)\n"
)


def main() -> int:
    parser = argparse.ArgumentParser(description="예시 시트를 온톨로지에 반영")
    parser.add_argument("--write", action="store_true", help="실제 반영 (기본: dry-run)")
    parser.add_argument("--register", action="store_true",
                        help="--write 후 DB ontology_versions에 새 버전 기록")
    args = parser.parse_args()

    config = get_config()
    sheet = read_sheet()
    text = ONTOLOGY.read_text(encoding="utf-8")
    data = yaml.safe_load(text)
    guard(sheet, data, config)

    changed: list[str] = []
    for intent in data["intents"]:
        iid = intent["intent_id"]
        if iid == UNKNOWN_INTENT_ID or not intent.get("domain"):
            continue
        if intent["positive_examples"] != sheet[iid]:
            changed.append(
                f"  {iid}: {len(intent['positive_examples'])} → {len(sheet[iid])}개"
            )
            intent["positive_examples"] = sheet[iid]

    if not changed:
        print("변경 없음 — 온톨로지가 이미 시트와 일치합니다 (no-op)")
        return 0

    old_version, new_version = data["version"], bump(data["version"])
    data["version"], data["change_type"] = new_version, "minor"
    print(f"변경 의도 {len(changed)}개, 버전 {old_version} → {new_version}:")
    print("\n".join(changed))

    if not args.write:
        print("\n(dry-run — 반영하려면 --write)")
        return 0

    # 원본 상단 주석 블록 보존 + 시트-원본 계약 주석 1줄 유지
    comment_lines = []
    for line in text.splitlines(keepends=True):
        if line.startswith("#"):
            comment_lines.append(line)
        else:
            break
    if not any("apply_ontology_examples" in c for c in comment_lines):
        comment_lines.append(HEADER_NOTE)
    body = yaml.safe_dump(
        data, allow_unicode=True, sort_keys=False, default_flow_style=False, width=10_000
    )
    ONTOLOGY.write_text("".join(comment_lines) + body, encoding="utf-8")

    # 반영본 재검증 — 실패하면 여기서 죽는 게 조용히 깨진 사전보다 낫다
    reloaded = load_ontology()
    validate_seed_quality(reloaded, config)
    assert reloaded.version == new_version
    print(f"반영 완료: {ONTOLOGY} ({new_version}, 구조·품질 검증 통과)")

    # 시트 사본 동기화(웹 다운로드용)
    SHEET_PUBLIC.write_bytes(SHEET.read_bytes())

    if args.register:
        import os

        from sqlalchemy import create_engine
        from sqlalchemy.orm import Session
        from sqlalchemy.pool import NullPool

        from app.core.ontology import register_ontology

        url = os.environ.get("DATABASE_URL")
        if not url:
            raise SystemExit("DATABASE_URL이 없습니다 (.env 확인)")
        engine = create_engine(
            url.replace("postgresql://", "postgresql+psycopg://", 1), poolclass=NullPool
        )
        with Session(engine) as session:
            row = register_ontology(session, reloaded)
            session.commit()
            print(f"DB 기록: ontology_versions += {row.version} (멱등)")
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
