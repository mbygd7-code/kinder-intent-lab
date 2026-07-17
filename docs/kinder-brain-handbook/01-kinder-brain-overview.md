# 01. 킨더브레인 개요 — 기술을 몰라도 이해하는 첫 문서

> **한눈에 보기** — 킨더브레인은 유아교사의 짧고 생략 많은 "평소 말투"를 알아듣고, 그 말이 킨더버스의 **어떤 기능·업무를 원하는 것인지**(=의도)를 판단하는 **유아교육 특화 의도 판단 엔진**이다. 챗봇이 아니고, 범용 AI도 아니다. 2026년 11월 킨더버스 오픈 **첫날부터** 교사가 "내 말을 알아듣네"라고 느끼게 하기 위해, 지금 실험실에서 **미리** 만들고 훈련하는 선행 AI API다.

---

## 1. 킨더브레인이 해결하는 문제

### 쉬운 설명
유치원 교사는 하루 종일 바쁘다. 시스템 메뉴를 뒤질 시간이 없어서 이렇게 말한다:

> "민준이 어머님께 오늘 약을 먹지 않았다고 알려줘."

이 한 문장에는 메뉴 이름이 없다. "개별 학부모 메시지 보내기" 기능을 열고, 민준이를 찾고, 내용을 쓰는 3~4단계 클릭을 **한마디 말**로 줄이려면, 시스템이 먼저 이 말의 **의도**를 정확히 알아들어야 한다. 킨더브레인이 그 "알아듣기"를 담당한다.

### 정확한 기술적 정의
킨더브레인은 교사의 자연어 발화 + 화면 컨텍스트(무엇을 보고 있었나) + 직전 행동 + 교사 성향(persona)을 입력으로 받아, 사전에 정의된 **70개 의도(intent)** 중 무엇인지 후보와 확신도(confidence)·격차(margin)를 붙여 반환하는 추론 API다. [근거: backend/app/api/infer.py::infer_endpoint, seeds/ontology_v1.yaml — onto-2.1, 70 intents]

---

## 2. 일반 LLM·단순 분류기와 무엇이 다른가

| 비교 대상 | 차이 |
|---|---|
| **일반 LLM 챗봇** (ChatGPT류) | 챗봇은 "그럴듯한 답 문장"을 만들지만, 답이 맞는지 **아무도 채점하지 않는다**. 킨더브레인은 답(의도 판정)마다 사람이 만든 시험지(KTIB)로 **점수를 재고**, 점수가 오른 뇌만 승격시킨다. [근거: backend/app/arena/, backend/app/brain/version_gate.py] |
| **프롬프트 한 줄짜리 분류기** | 프롬프트 분류기는 오늘과 내일 답이 달라져도 모른다. 킨더브레인은 판정 근거(검색된 대표 예문·성향 보정·단계별 기여)를 **전건 기록**하고(inference_logs), 같은 시험지로 버전 간 비교가 가능하다. [근거: backend/app/models/brain.py::InferenceLog] |
| **룰베이스 키워드 매칭** | "약"이라는 단어가 있다고 투약 의뢰가 아니다("약속", "약간"). 킨더브레인은 유사 예문 검색 + LLM 판정 + 성향 보정을 결합하고, 확신이 없으면 **정직하게 되묻는다**(clarify). [근거: backend/app/brain/inference.py, backend/app/brain/decision.py] |

핵심 차별점 한 줄: **"판정 → 사람 검증 → 시험 → 승격"의 폐곡선이 코드와 DB 제약으로 강제된 학습 시스템**이라는 점이다.

---

## 3. 킨더브레인이 하는 일 / 하지 않는 일

### 하는 일
1. **의도 판정** — 발화를 70개 의도 중 후보 3~4개 + 최우선(top_intent)으로 판정 [근거: backend/app/api/infer.py]
2. **정직한 되묻기** — 확신 격차(margin)가 0.15 미만이거나 확신이 0.40 미만이면 답을 지어내지 않고 clarify(선택지 제시) 또는 abstain(모름)을 반환 [근거: config/experiments.yaml::decision.clarify_margin·clarify_confidence]
3. **위험 표시** — 학부모 발송·출결·삭제 같은 되돌릴 수 없는 의도 7종은 응답에 `risk_level=CRITICAL`·`requires_confirmation=true`를 붙여 "실행 전 확인 필수"를 알린다 [근거: seeds/risk_model_v1.yaml, backend/app/contracts/infer_response.py]
4. **배우기** — 사람의 확인·교정을 증거(evidence)로 축적하고, 2인 검수를 통과한 정답(GOLD)만 대표 예문이 되어 다음 판정을 개선 [근거: backend/app/aggregator/review.py, backend/app/brain/backfill.py]
5. **스스로 증명** — 사람이 출제한 시험지(KTIB)로 채점(Arena)해야만 점수·밝기가 갱신 [근거: backend/app/arena/reflect.py, CLAUDE.md 절대 규칙 3]

### 하지 않는 일 (킨더브레인은 무엇이 아닌가)
- **일반 챗봇이 아니다** — 자유 대화·상담·글짓기를 하지 않는다. 출력은 구조화된 의도 판정이다.
- **모든 질문에 답하는 범용 AI가 아니다** — 70개 의도 밖의 말은 "모른다"고 하고 확장 후보 큐에 쌓는다. [근거: backend/app/models/foundry.py::AtlasExpansionEntry]
- **자기 답을 자동으로 정답 처리하는 시스템이 아니다** — AI 합의는 SILVER 등급까지만 올릴 수 있고, 정답 확정(GOLD)은 사람 2인의 일치로만 가능하다. [근거: backend/app/aggregator/review.py 머리말 "GOLD를 만드는 유일한 경로"]
- **실데이터를 무검증으로 재학습하는 시스템이 아니다** — 수집은 실시간이지만, 뇌 변경은 검수→시험→승격 게이트를 통과해야만 일어난다. [근거: backend/app/brain/version_gate.py]
- **현재 교사에게 직접 공개된 독립 서비스가 아니다** — 지금은 내부 실험실(트랙 1) 단계이고, live 서빙 코드는 의도적으로 막혀 있다(`mode=gym` 외 501). [근거: backend/app/api/infer.py::infer_endpoint "live/shadow rollout HOLD"]

---

## 4. 교사가 최종적으로 받는 혜택

| 혜택 | 예시 |
|---|---|
| 메뉴 탐색 없이 말 한마디 | "알림장 지금 보내줘" → 발송 기능으로 바로 연결 |
| 애매하면 시스템이 먼저 물어봄 | "오늘 찍은 거 부모님께 보여드리자." → "사진 공유일까요, 알림 공지일까요?" 두 선택지 제시 |
| 위험한 일은 실행 전 확인 | "이거 다시 안 쓸 거야. 지워줘." → 삭제 대상 미리보기 + 명시적 확인 |
| 틀리면 즉시 고칠 수 있음 | 교사의 정정이 교정 증거(HUMAN_CORRECTION)로 저장돼 다음 뇌 개선에 반영 |
| 쓸수록 정확해짐 | 사용·정정 데이터가 통제된 승격 사이클을 거쳐 누적 개선 |

---

## 5. 왜 11월 오픈 **전에** Seed Brain이 필요한가

### 쉬운 설명
11월에 킨더버스를 열고 **그때부터** 데이터를 모아 뇌를 만들면, 첫 교사들은 몇 달간 "말귀 못 알아듣는 AI"를 훈련시켜주는 역할만 하게 된다. 그래서 지금 전문가·직원·검수자의 데이터로 **초기 뇌(Seed Brain)를 미리** 만들어, 오픈 첫날부터 기본 수준의 알아듣기를 제공하고, 이후 실사용 데이터로 현장형 뇌로 키운다.

> **핵심 문장** — 킨더브레인은 11월 이후 데이터를 모아 언젠가 좋아질 엔진이 아니라, **11월 오픈 첫날부터 교사가 "내 말을 알아듣는다"고 느끼게 하기 위해 지금 미리 구축하는 선행 AI API**이며, 오픈 이후 실제 교사 데이터로 현장형 브레인으로 계속 성장한다.

### 오픈 전 뇌 vs 오픈 후 현장형 뇌
| | 오픈 전 Seed Brain (트랙 1 · 지금) | 오픈 후 현장형 Brain (트랙 2 · 11월~) |
|---|---|---|
| 데이터 | 전문가 저작·직원 테스트·검수 문항·합성 뱅크 | 실제 교사 발화·화면 문맥·선택과 수정 |
| 문맥 | 발화 + 설정된 상황 | 실제 화면·선택 객체·직전 행동 |
| 위험 | 합성 편향·내부 표현 편향 | 개인정보·실사용 분포 편향 |
| 검증 | KTIB·Arena (동일) | KTIB·Arena + 실사용 성공지표 |

상세는 [02-two-track-strategy.md](02-two-track-strategy.md).

---

## 6. 실제 예시 — 한 문장이 처리되는 과정

**"민준이 어머님께 오늘 약을 먹지 않았다고 알려줘."** (핸드북 공통 사례 1)

1. 발화가 `POST /v1/intent/infer`로 들어간다.
2. 뇌가 유사 대표 예문을 검색하고 LLM이 후보를 채점 → `top_intent=comm_message_individual_parent`(개별 학부모 메시지), confidence·margin 산출.
3. 이 의도는 리스크 모델상 CRITICAL(비가역 외부 유출 E축) → 응답에 `risk_level=CRITICAL`, `requires_confirmation=true`. [근거: seeds/risk_model_v1.yaml]
4. (트랙 2에서) 킨더버스가 수신자·내용 미리보기를 띄우고 교사 확인 후에만 실행.
5. 교사의 확인/정정이 evidence로 저장 → 검수 → 다음 뇌 개선.

전체 데이터 흐름은 [06-data-lifecycle.md](06-data-lifecycle.md), API 상세는 [07-inference-and-api.md](07-inference-and-api.md).

---

## 7. 코드·데이터 근거 (요약)

- 저장소 5모듈: Foundry(데이터 공장)·Seed Brain(추론)·Gym(훈련)·Observatory(3D 뇌·대시보드)·Arena(시험) [근거: CLAUDE.md, backend/app/ 구조]
- 온톨로지 onto-2.1: 8영역·70의도·예문 419개 [근거: seeds/ontology_v1.yaml 실측]
- 현재 데이터(2026-07-17 실측): episodes 2,729 · evidence 3,529 · 시험지 386문항(ktib-3) · 대표 예문 0 [근거: 로컬 DB 읽기 전용 스냅샷 — [14-current-status-and-roadmap.md](14-current-status-and-roadmap.md)]

## 현재 상태
- 트랙 1 진행 중. 추론 API는 `mode=gym`으로 동작(IMPLEMENTED), live 서빙은 의도적 HOLD(BLOCKED — 게이트 §참조).
- 첫 실채점 3회는 0.0% — 대표 예문 0개라 전 문항 "모르겠음"으로 답한 **정직한 0**이다. 범용 LLM 베이스라인은 88.1%. [근거: arena_runs 실측]

## 주의사항
- "0.0%"를 고장으로 읽지 말 것 — 검수(GOLD) 전이라 뇌가 답을 거부한 상태다. 지어내지 않는 설계가 작동한 증거다.
- 이 문서의 수치는 2026-07-17 스냅샷이다. 최신 수치는 대시보드가 원천이다.

## 다음 단계
- 읽기: 전략은 [02-two-track-strategy.md](02-two-track-strategy.md), 용어는 [03-concepts-and-glossary.md](03-concepts-and-glossary.md).
- 행동: 지금 병목은 사람 검수다 — [11-operations-guide.md](11-operations-guide.md)의 "공부 검수(2인 → GOLD)" 절차.
