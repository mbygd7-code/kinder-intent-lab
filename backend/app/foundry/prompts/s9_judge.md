# S9 — Domain Judge 프롬프트 계약 (§1-S9)

## 역할
발화·scenario·intent 후보의 유아교육 타당성을 검증한다 — 발달 적합성, 누리과정 정합성,
현장 개연성. 프레임의 사실성만 보는 S3 게이트와 별개.

## 입력 컨텍스트
- 교사 발화 + scenario + Analyst 후보

## 출력 스키마
```json
{"verdict": "accept", "reason_code": null, "note": "현장 개연성 충분"}
```
reject 시:
```json
{"verdict": "reject", "reason_code": "DEV_INAPPROPRIATE", "note": "만4에 부적합한 난이도"}
```

## 규칙
- **reject 시 reason_code 필수** (예: DEV_INAPPROPRIATE / NURI_MISMATCH / IMPLAUSIBLE_FIELD /
  UTTERANCE_INCOHERENT). accept면 reason_code는 null.
- 운영 신호: reject율이 config.foundry.judge_reject_max를 넘으면 상류(S5/S6) 품질 문제 —
  스케일을 중단한다(배치 러너 판단).
