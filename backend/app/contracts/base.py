"""계약 베이스. schemas/*.json이 원천 — pydantic은 파생이며 왕복 테스트로 고정한다.

- strict=True: JSON Schema의 타입 규율을 그대로 강제 (조용한 코어션 금지)
- extra="allow": JSON Schema 기본값(additionalProperties: true)과 동일하게
  미지 필드를 수용·보존한다 (additionalProperties: false인 스키마만 forbid 오버라이드)
- _reject_explicit_null: 스키마가 nullable(type: [..., "null"])로 선언하지 않은
  선택 필드에 명시적 null이 오면 거부한다 (키 생략은 허용) — 스키마와 판정 일치
"""
from typing import ClassVar, Literal

from pydantic import BaseModel, ConfigDict, model_validator

Domain = Literal[
    "PLAY", "OBSERVATION", "DOCUMENT", "VISUAL", "COMMUNICATION", "OPERATION", "REFLECTION"
]


class Contract(BaseModel):
    model_config = ConfigDict(extra="allow", strict=True)

    # 스키마상 null 불가인 선택 필드 이름들 — 하위 모델이 선언
    _reject_explicit_null: ClassVar[tuple[str, ...]] = ()

    @model_validator(mode="before")
    @classmethod
    def _no_explicit_null(cls, data: object) -> object:
        if isinstance(data, dict):
            for field in cls._reject_explicit_null:
                if field in data and data[field] is None:
                    raise ValueError(
                        f"{field}: 스키마상 null 불가 — 값이 없으면 키를 생략하라"
                    )
        return data
