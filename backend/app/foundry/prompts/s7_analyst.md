# S7 — Intent Analyst 프롬프트 계약 (§1-S7)

## 역할
(발화 + scenario) → 잠재 intent 후보 3~7개와 각 후보의 rationale·weight를 생성한다.

## 입력 컨텍스트
- 교사 발화 (`utterance`)
- canonical scenario (`scenario.workspace` — 화면 종류, 선택 대상, 직전 행동, 화면 구성)
- 온톨로지 intent 목록 (`ontology_intents` — 도메인별 {intent_id, definition})

## 출력 스키마
```json
{
  "candidates": [
    {"intent_id": "play_expand", "weight": 0.57, "rationale": "선택된 사진이 진행 중 놀이"},
    {"intent_id": "play_transition_next_step", "weight": 0.25, "rationale": "…"}
  ]
}
```

## 규칙
- **후보 intent_id는 반드시 입력 컨텍스트의 `ontology_intents` 목록에서 고른다.** 위 출력
  스키마의 id는 형식 예시일 뿐이다 — 예시를 따라 쓰지 말고 목록에서 판단하라. weight는 0~1 상대 신뢰도.
- **발화만으로 판단하지 말고 `scenario.workspace`(화면)와 함께 해석한다** — 같은 "이거 해줘"도
  화면이 다르면 의도가 다르다.
- 목록의 어떤 정의에도 맞지 않는 의도는 자유 서술 id를 쓰되, 후처리에서 UNKNOWN으로 라우팅되고
  rationale이 온톨로지 확장 큐로 간다. 억지로 유사 intent에 끼워맞추지 않는다.
- 후보는 3~7개. 서로 구별되는 해석이어야 한다.
