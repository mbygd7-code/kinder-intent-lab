# S10 — Consensus Labeler 프롬프트 계약 (§1-S10)

> 상태(2026-07-17): S10 합의는 LLM이 아니라 **코드**(stages/s10_consensus.py)로
> 계산한다 — 이 프롬프트는 현재 로드되지 않으며, LLM 합의로 확장할 때의 계약 기준으로 유지한다.

## 역할
S7~S9 산출을 종합해 **단일 정답이 아니라 label distribution**을 만든다. 합의도와
disagreement를 함께 기록한다 — disagreement 자체가 confusion 후보의 두 번째 공급원.

## 입력 컨텍스트
- Analyst 후보(intent_id + weight)
- Skeptic 혼동 쌍
- Judge verdict(accept/reject + reason)

## 산출 (코드가 정규화)
```json
{
  "label_distribution": {"play_expand": 0.57, "play_transition_next_step": 0.25, "UNKNOWN": 0.08},
  "consensus": 0.57,
  "disagreement_pairs": [["play_expand", "play_transition_next_step"]]
}
```

## 규칙
- `label_distribution` 합 = 1 (코드가 정규화). 신호가 전무하면 UNKNOWN=1.0.
- Judge가 reject한 케이스는 학습 분포에서 제외되거나 REJECTED로 라우팅된다(하류 결정).
- disagreement_pairs는 Skeptic 쌍 + Analyst 상위 후보 간 이견을 합친다.
