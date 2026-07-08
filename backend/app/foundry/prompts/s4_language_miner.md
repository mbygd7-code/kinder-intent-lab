# S4 — Teacher Language Miner 프롬프트 계약 (§1-S4, §2)

## 역할
TRANSFORM_ONLY 소스에서 **표현 패턴만** 추출한다 — Teacher Language Atlas(§2)의 원료.
원문 인용 저장 금지. 패러프레이즈된 대표형(surface_form)만 만든다.

## 입력 컨텍스트
- 소스의 발화 표현들 (in-memory, 저장 안 됨)
- 기존 Atlas pattern_cluster 목록 (매핑 우선)

## 출력 스키마 (AtlasInput)
```json
{
  "representative": "자연스럽게 해달라는 요청",
  "pattern_cluster": "NATURALIZE",
  "ambiguity_types": ["TARGET_UNSPECIFIED", "VERB_POLYSEMY"],
  "possible_intents": ["text_naturalize", "visual_layout_refine"],
  "resolution_signals": [
    {"signal": "selection_type", "rule": "선택 대상이 photo면 VISUAL 계열 우세"}
  ],
  "register": {"style": "반말·해요체 혼재", "typical_length": "5-9어절"},
  "source_class_mix": {"TEACHER_LANGUAGE": 0.71, "SYNTHETIC": 0.29}
}
```

## 금지사항 (절대 규칙 7)
- 원문 문장을 그대로(또는 거의 그대로) 대표형으로 쓰지 않는다.
- representative가 원문과 임베딩 유사도 `> config.foundry.paraphrase_max`면 원문 잔존으로
  간주되어 **폐기된다**. 충분히 추상화·일반화하라.
