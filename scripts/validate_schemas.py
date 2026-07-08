#!/usr/bin/env python3
"""schemas/*.json 검증 + 예시 왕복 테스트.

사용: python scripts/validate_schemas.py
- 모든 스키마가 draft-07로 파싱되는지
- examples/ 폴더가 있으면 각 예시가 해당 스키마를 통과하는지
Phase 1 T1.4에서 jsonschema 기반으로 확장한다.
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "schemas"


def main() -> int:
    errors = 0
    schemas = sorted(SCHEMAS.glob("*.schema.json"))
    if not schemas:
        print("no schemas found", file=sys.stderr)
        return 1
    for p in schemas:
        try:
            doc = json.loads(p.read_text(encoding="utf-8"))
            assert doc.get("$schema", "").startswith("http://json-schema.org/draft-07"), "draft-07 아님"
            assert "title" in doc and "type" in doc, "title/type 누락"
            print(f"OK   {p.name}")
        except Exception as e:  # noqa: BLE001
            errors += 1
            print(f"FAIL {p.name}: {e}", file=sys.stderr)
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        print("(jsonschema 미설치 — 구조 검사만 수행. T1.4에서 예시 왕복 검증 추가)")
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
