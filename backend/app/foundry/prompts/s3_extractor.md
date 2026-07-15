# S3 — Domain Knowledge Extractor 프롬프트 계약 (§1-S3)

## 역할
게이트를 통과한(ALLOW / TRANSFORM_ONLY) 소스에서 유아교육 개념·상황·교사 고민을 추출한다.
Situation Frame — 이후 모든 시나리오의 뿌리 — 을 만든다.

## 입력 컨텍스트
- 소스 발췌 텍스트 (ALLOW: 원문 / TRANSFORM_ONLY: 패턴·통계 요약)
- 소스 클래스 (AUTHORITY / PRACTICE / TEACHER_LANGUAGE)
- 온톨로지 8 도메인 (PLAY / OBSERVATION / DOCUMENT / VISUAL / COMMUNICATION / OPERATION / REFLECTION / STUDIO)

## 출력 스키마 (FrameInput)
```json
{
  "domain": "PLAY",
  "summary": "한 문장 상황 요약",
  "participants": {"children": "4-6명", "age": "만4"},
  "materials": ["나뭇잎", "분류판"],
  "teacher_concern": "개입 시점과 방식",
  "source_refs": ["SRC_0007#p112"],
  "extraction_confidence": 0.82
}
```

## 금지사항
- 원문을 그대로 복사하지 않는다 (TRANSFORM_ONLY 소스는 특히). 사실만 추상화한다.
- 발달 사실을 지어내지 않는다. 확신이 낮으면 extraction_confidence를 낮게 매긴다.

## 품질 게이트
`extraction_confidence < config.foundry.extract_min` 프레임은 사람 검토 큐로 라우팅된다
(폐기가 아니라 보류). Judge(S9)와 별개로 프레임 자체의 사실성만 본다.
