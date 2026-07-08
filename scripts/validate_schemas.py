#!/usr/bin/env python3
"""schemas/*.json 검증 + 예시 왕복 테스트 (T1.4에서 jsonschema 기반으로 확장).

사용: python scripts/validate_schemas.py
- 모든 스키마가 draft-07 메타스키마를 통과하는지 (jsonschema)
- examples/<이름>[.변형].json이 schemas/<이름>.schema.json을 통과하는지
  ($ref는 kinder:// $id 레지스트리로 해석)
"""
import json
import sys
from pathlib import Path

# Windows 콘솔(cp949)에서 한글 출력이 UnicodeEncodeError로 죽지 않도록
sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS = ROOT / "schemas"
EXAMPLES = ROOT / "examples"


def main() -> int:
    try:
        import jsonschema
        from referencing import Registry, Resource
    except ImportError:
        print(
            "jsonschema 미설치 — backend venv로 실행하거나 pip install jsonschema",
            file=sys.stderr,
        )
        return 1

    errors = 0
    schema_docs: dict[str, dict] = {}

    schema_files = sorted(SCHEMAS.glob("*.schema.json"))
    if not schema_files:
        print("no schemas found", file=sys.stderr)
        return 1

    seen_ids: dict[str, str] = {}
    for path in schema_files:
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
            assert doc.get("$schema", "").startswith(
                "http://json-schema.org/draft-07"
            ), "draft-07 아님"
            assert "title" in doc and "type" in doc, "title/type 누락"
            # $id 무결성: 존재 + 파일명 일치 + 유일 — $ref가 엉뚱한 스키마로 풀리는 사고 방지
            schema_id = doc.get("$id")
            assert schema_id == f"kinder://schemas/{path.name}", f"$id 불일치: {schema_id}"
            assert schema_id not in seen_ids, f"$id 중복: {seen_ids[schema_id]}와 충돌"
            seen_ids[schema_id] = path.name
            jsonschema.Draft7Validator.check_schema(doc)
            schema_docs[path.stem.removesuffix(".schema")] = doc
            print(f"OK   {path.name}")
        except Exception as e:  # noqa: BLE001
            errors += 1
            print(f"FAIL {path.name}: {e}", file=sys.stderr)

    registry = Registry().with_resources(
        (doc["$id"], Resource.from_contents(doc))
        for doc in schema_docs.values()
        if "$id" in doc
    )

    example_files = sorted(EXAMPLES.glob("*.json")) if EXAMPLES.exists() else []
    # 역방향 커버리지: 모든 스키마에 예시가 최소 1개
    example_names = {p.name.split(".")[0] for p in example_files}
    for name in sorted(set(schema_docs) - example_names):
        errors += 1
        print(f"FAIL {name}.schema.json: examples/에 예시가 없음", file=sys.stderr)
    for path in example_files:
        name = path.name.split(".")[0]
        schema = schema_docs.get(name)
        if schema is None:
            errors += 1
            print(f"FAIL examples/{path.name}: 대응 스키마 {name}.schema.json 없음", file=sys.stderr)
            continue
        try:
            instance = json.loads(path.read_text(encoding="utf-8"))
            jsonschema.Draft7Validator(schema, registry=registry).validate(instance)
            print(f"OK   examples/{path.name}")
        except Exception as e:  # noqa: BLE001
            errors += 1
            first_line = str(e).splitlines()[0]
            print(f"FAIL examples/{path.name}: {first_line}", file=sys.stderr)

    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
