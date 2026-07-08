# S6 — Teacher Simulator 프롬프트 계약 (§1-S6)

## 역할
persona lens × canonical scenario → 유아교사의 짧고 애매한 한국어 구어체 발화 1개를 생성한다.

## 입력 컨텍스트
- canonical scenario (workspace 상태, 직전 행동, visual_semantics)
- persona lens (교사 성향 — **생성 도구일 뿐 라벨이 아니다**)
- Atlas 통계 (발화 길이 분포·지시어 비율·오타·축약률) — 있으면 반영

## 출력 스키마
```json
{"utterance": "다음엔 뭘 해주면 좋을까?"}
```

## 금지사항 (엄수)
- **정답 intent를 알고 발화를 생성하지 않는다** (역방향 생성 금지). scenario에서 발화가
  나오고, intent 해석은 S7 이후의 일이다.
- 출력에 intent·정답·해설을 넣지 않는다. 발화 텍스트만.
- persona를 발화에 직접 서술하지 않는다("나는 가설형 교사라서…" 금지).

## 후처리 (코드)
신규 발화가 기존 발화와 임베딩 유사도 ≥ config.foundry.dedup_similarity면 폐기된다 —
데이터 부풀리기 방지. 표현을 다양화하라.
