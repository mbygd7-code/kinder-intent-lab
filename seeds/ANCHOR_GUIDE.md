# 인간 앵커 작성 가이드 (Phase A)

뇌의 "증명된 정확도"는 사람이 만든 정답에서만 나옵니다 (§3-3, §8-2).
이 폴더의 두 파일이 그 정답의 원천입니다. **우선순위가 중요합니다.**

## 1순위 — KTIB 시험지: `ktib_seed_template.yaml` (또는 `.csv`)

지금 사람이 할 수 있는 **가장 값진 작업**입니다. 진척은 언제든
`python scripts/ktib_coverage.py`로 확인하세요(의도별 등록 수 · 게이트 하한까지의 갭).
**되돌릴 수 없는 위험 의도 7개(CRITICAL)부터** 채우는 걸 권장합니다 —
`seeds/ktib_critical7_template.csv`(7×30, '혼동 주의' 힌트 포함)를 웹 ExamUpload로 올리면 돼요.
의도별 구별 요령은 `docs/09-teacher-guide/exam-authoring-critical7.md`.

전체 63개로 넓힐 때는 아래 YAML 흐름을 씁니다. 63개 의도 × 1문항 초안이 이미 채워져
있으니, 두 분이 함께:

1. 각 `teacher_prompt`를 실제 현장에서 쓰는 표현인지 검토하고 어색하면 교체한다
   (**LLM으로 생성 금지** — 시험 점수가 무의미해집니다. §8-2)
2. `reviewers: ["검수자1", "검수자2"]`를 실명(또는 고정 id)으로 바꾼다 — 서로 다른 2인 필수
3. 두 사람의 판단이 일치하면 `agreement_kappa: 1.0` 유지, 이견이 있던 문항은 낮춰 기록
4. `authored_by` / `approved_by` 채우기
5. 여유가 되면 의도당 2~3문항으로 늘리기 (문항이 많을수록 점수의 통계적 의미가 커짐)

적재(내가 실행): `python scripts/ingest_expert_episodes.py --file seeds/ktib_seed_template.yaml --commit`

## 2순위(현재 보류 권장) — 검수 큐: `review_queue_300.yaml`

`run_human_review.py --queue`로 뽑은 합성 에피소드 300건입니다. **그런데 현재 DB의 합성
2,200건은 전부 mock 자리표시자**("이거 좀 해줄 수 있어? (변형 N)" — 고유 문장 1개)라서,
지금 이 큐를 검수하는 것은 시간 낭비입니다 (내용 없는 문장에 의도를 붙일 수 없음).

이 큐가 의미를 가지려면 먼저 둘 중 하나가 필요합니다:
- 실 LLM(`LLM_PROVIDER=anthropic`)으로 campaign을 재실행해 진짜 발화를 생성 (과금 발생), 또는
- **즉석 문답 UI**(구현 중)로 사람이 직접 발화를 타이핑 — 이 상호작용이 진짜 인간 에피소드가
  되어 검수 큐에 쌓입니다

검수 요령(때가 되면): 서로 다른 `reviewer_ref`로 각자 `chosen_intent`를 채우고 합쳐서
`--apply` — 2인 만장일치만 GOLD, 배치 kappa < 0.65면 전량 거부. `_aggregator_suggests`는
참고용이며 그대로 베끼면 검수가 아닙니다.

## 즉석 문답 "출제"의 2차 검수 — blind 플로우

즉석 문답에서 "시험 문제로 출제"를 켜면 `seeds/benchmark_candidates.yaml`에 쌓입니다.
여기엔 출제자(1차)의 라벨이 있으므로, **2차 검수자는 그 파일을 직접 보지 말고** 아래
blind 절차를 쓰세요 (1차 라벨을 보고 확인만 하면 독립 검수가 아닙니다):

1. `python scripts/run_benchmark_review.py --queue blind.yaml` — 발화만 담긴 2차용 파일 생성
2. 2차 검수자가 `blind.yaml`의 `reviewer_ref`와 각 `chosen_intent`를 **독립적으로** 채움
3. `python scripts/run_benchmark_review.py --apply blind.yaml` (dry-run 확인 후 `--write`)
   — 배치 kappa ≥ 0.65 통과 시 일치 문항만 검수 완료로 기록, 불일치는 반려 목록
4. `benchmark_candidates.yaml`의 `approved_by`를 채운 뒤
   `python scripts/ingest_expert_episodes.py --file seeds/benchmark_candidates.yaml --commit`

## 강화하기 문제(온톨로지 예시) 편집 루프 — 언제든 반복 가능

강화하기 퀴즈의 문제 문장은 `seeds/ontology_examples_draft.csv`가 원본이다 (2026-07-13 도입,
onto-1.1에서 의도당 6문장). 문장을 고치고 싶으면:

1. 시트를 엑셀로 열어 '예시 문장' 칸을 고치거나, '빼려면 X' 칸에 X (새 줄 추가도 가능)
2. `python scripts/apply_ontology_examples.py` — dry-run으로 변경 확인
3. `python scripts/apply_ontology_examples.py --write --register` — 반영(버전 minor bump)
4. 커밋·푸시 → 재배포되면 강화하기에 반영

주의: `seeds/ontology_v1.yaml`의 positive_examples를 **직접 편집하지 말 것** — 다음 시트
반영 때 시트 내용으로 덮인다. 항상 시트를 고쳐라.

## 지켜야 할 선 (변하지 않음)

- 시험지(BENCHMARK_HOLDOUT) 발화는 **사람 저작만** — 코드가 탐지 못하는 유일한 규칙
- 같은 발화를 훈련과 시험 양쪽에 넣지 않기 (자동 거부되지만, 애초에 분리해서 작성)
- GOLD는 서로 다른 2인 일치만 — 1인이 두 역할을 하면 코드가 거부
