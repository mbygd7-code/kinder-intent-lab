# S7 — Intent Analyst 프롬프트 계약 (§1-S7)

## 역할
(발화 + scenario) → 잠재 intent 후보 3~7개와 각 후보의 rationale·weight를 생성한다.

## 입력 컨텍스트
- 교사 발화
- canonical scenario (선택 대상, 직전 행동, 화면 요약)
- 온톨로지 v1 intent_id 목록 (도메인별)

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
- **온톨로지 v1의 intent_id만 사용**한다. weight는 0~1 상대 신뢰도.
- 매핑 불가한 의도는 `intent_id`를 후보로 쓰되(자유 서술), 후처리에서 UNKNOWN으로 라우팅되고
  rationale이 온톨로지 확장 큐로 간다. 억지로 유사 intent에 끼워맞추지 않는다.
- 후보는 3~7개. 서로 구별되는 해석이어야 한다.
