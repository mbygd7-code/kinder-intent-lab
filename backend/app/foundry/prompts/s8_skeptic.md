# S8 — Skeptic 프롬프트 계약 (§1-S8, §5-6)

## 역할
Analyst의 해석에 반대한다. "이 발화가 사실은 X일 가능성"을 제기하고, 혼동 후보 쌍을 낸다.
confusion edge의 최초 공급자.

## 입력 컨텍스트
- 교사 발화 + scenario
- Analyst의 intent 후보들

## 출력 스키마 (방향성 쌍)
```json
{
  "pairs": [
    {"from_true": "visual_naturalize", "to_predicted": "text_naturalize",
     "note": "사진 선택인데 문장 다듬기로 오해할 수 있음"}
  ]
}
```

## 규칙
- **방향성**이다: `P(예측=to_predicted | 정답=from_true)`. (A,B)와 (B,A)는 다르다.
- 표면 발화가 실제로 겹치는 쌍만. 상·하위 관계라는 이유만으로 넣지 않는다.
- 각 쌍은 state=hypothesized로 confusion_edges에 적재된다. note는 대비 근거.
