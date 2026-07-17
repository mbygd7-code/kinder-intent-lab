# 12. 킨더버스 연동 — 11월에 무엇을 어떻게 붙이는가

> **한눈에 보기** — 킨더브레인은 "판단"을 반환하고, 킨더버스는 "문맥 제공 + 실행 + 교사 확인 UI"를 담당한다. 연결은 전역 스위치가 아니라 **의도별 단계**(Shadow → Suggest → Assist, CRITICAL은 항상 Confirm)로 켠다. 현재 코드는 이 연결에 필요한 **계약(응답 필드·위험 신호·문맥 슬롯)까지 구현**돼 있고, 서빙 자체는 게이트 전 의도적 HOLD다. [근거: docs/06-runtime-integration/two-track-launch-plan-v0.1.md, backend/app/api/infer.py]

---

## 1. 책임 분리 — 누가 무엇을 하나

### 킨더브레인이 반환하는 것 (계약 ir-0.2 — IMPLEMENTED)
| 필드 | 의미 |
|---|---|
| top_intent · intent_candidates(≤5) | 판단 결과와 후보(각 후보에 risk_tier·requires_confirmation 포함) |
| confidence · margin | 확신·격차 — 킨더버스가 UI 강도를 정할 근거 |
| decision | execute/suggest/clarify/abstain — 정책 엔진의 판정 |
| clarification | 되물을 질문 + top-2 선택지 |
| risk_level | top_intent의 위험 등급(CRITICAL/HIGH/LOW — 리스크 모델 파생) |
| required_slots | **예약 필드(항상 null)** — 슬롯 추출은 트랙 2 구현 전까지 지어내지 않음 |
| context_used | 실제 소비한 문맥 에코(감사·디버그) |
| request_id · model_version · ontology_version | 재현·감사 축 |
[근거: backend/app/contracts/infer_response.py::InferResponse, schemas/infer_response.schema.json]

### 킨더버스가 제공해야 하는 것
| 문맥 | 배치 | 상태 |
|---|---|---|
| 현재 화면·선택 객체(아이/자료) | Core `workspace_context` | 계약 IMPLEMENTED |
| 직전 교사 행동 | Core `recent_actions` | 계약 IMPLEMENTED |
| 직전 대화 | Core `session.conversation_history` | 계약 IMPLEMENTED |
| 교사 식별·성향 참조 | Core `teacher_context` | 계약 IMPLEMENTED |
| 사용자 권한 / 현재 반·기관 | `runtime_extension` (Core 밖 — 추론 점수 미개입, 실행 정책용) | DESIGNED [근거: two-track-launch-plan §3] |

### 킨더버스가 담당하는 것 (전부 트랙 2 — DESIGNED)
실제 기능 실행 시스템 · 교사 확인 UI(미리보기/선택지) · 실행 결과의 피드백 회수(선택·수정 → 교정 evidence 전송) · 수집 데이터의 검수 경로 연결(PRODUCTION_SHADOW 채널).

---

## 2. 연결 단계 (전역이 아니라 의도별)

| 단계 | 내용 | 시작 조건(제안 기준) |
|---|---|---|
| **Shadow 0a** | 추론 없이 발화·문맥 로깅만 | 거버넌스 7항목(목적·법적 근거·PII·최소수집·보존·옵트아웃·스키마) 통과 [근거: runtime README §2] |
| **Shadow 0b** | 몰래 추론, 비노출 — 실제 선택과 비교 | 0a 안정 + Seed Brain 유효 점수 존재 |
| **Suggest** | 후보 제시 → 교사 선택 → 선택이 교정 evidence | 해당 의도 측정치 ≥ suggest 하한 |
| **Assist** | 가역 액션(열기·초안·검색) 바로 연결 | 측정치 ≥ assist 하한 ∧ STANDARD 위험 |
| **Confirm 필수** | 미리보기 + 명시 확인 후 실행 | **CRITICAL 7은 성적 무관 항상 여기까지만** |
| **HOLD** | 내부 추론만(비노출) | 측정 null 또는 GOLD 앵커 미달 |

의도별 시작 단계 판단 예:
- 화면 이동·검색·문항 열람 → Assist 후보
- 초안 생성(알림장 쓰기 등) → Suggest→Assist
- 학부모 발송·출결 변경·자료 삭제·동의 요청·예약 발송 → **Confirm 필수** (CRITICAL 7 [근거: seeds/risk_model_v1.yaml])
- 현재 시험 문항 0인 62개 의도 → 측정 전이므로 HOLD에서 시작

등급은 사람이 정하는 값이 아니라 **Arena 실측 × 리스크 등급 × 데이터 규모에서 파생되는 읽기 전용 VIEW**로 설계됐다(임계값은 구현 시 config에만). [근거: two-track-launch-plan §2 — DESIGNED, 코드 미구현]

---

## 3. 세 층의 분리 — Intent / Slot / Action Plan

| 층 | 질문 | 현재 코드 상태 |
|---|---|---|
| **Intent** | 무엇을 하려는가 | **IMPLEMENTED** — 70의도 판정·후보·확신·위험 신호까지 |
| **Slot·Entity** | 누구에게·무엇을·언제 | **PLANNED** — 계약에 `required_slots` 예약(항상 null). 추출 로직 없음. "민준이", "오늘 약" 같은 값 추출은 트랙 2 범위 [근거: backend/app/contracts/infer_response.py 주석] |
| **Action Plan** | 실제 어떤 작업을 실행 | **PARTIAL(계약만)** — 후보에 `proposed_action`(action_type·target_objects·preview_available·undoable) 필드가 정의돼 있으나 현재 추론이 채우지 않는다 [근거: backend/app/contracts/infer_response.py::ProposedAction — infer.py에서 미설정] |

즉 사례 1("민준이 어머님께 오늘 약을 먹지 않았다고 알려줘.")에서:
- 지금: `comm_message_individual_parent` + CRITICAL + 확인 필요 — **여기까지 킨더브레인**.
- 트랙 2: "민준이(아동)·어머님(수신자)·약 미복용(내용)" 슬롯 채움과 발송 액션 조립은 킨더버스+슬롯 추출이 담당.

---

## 4. 연결 준비 체크리스트 (트랙 1과 병행)

1. 계약 동결 — ir-0.2 응답/요청 + runtime_extension 필드 확정 【계약 IMPLEMENTED / 확장 DESIGNED】
2. Shadow 0a 거버넌스 7항목 문서·절차 통과 【GAP — [10장](10-safety-and-governance.md) §3】
3. 크로스워크(킨더버스 표면 ↔ 70의도 매핑) 확정 【DESIGNED [근거: docs/06-runtime-integration/kinderverse-intent-sync-strategy-v0.1.md]】
4. 스테이징 mode=shadow 왕복 리허설(계약·지연·재현성) 【PLANNED】
5. 오픈 게이트 판정 — 최소 기준 9항목 + "KTIB 80%+안전 지표" 【장치 대부분 IMPLEMENTED, 데이터 대기 — internal-alignment §2】

## 현재 상태
- 반환 계약·위험 신호·감사 축: IMPLEMENTED. 서빙(live/shadow)·등급 산정 코드·슬롯 추출: HOLD/DESIGNED/PLANNED — **의도된 순서**다(게이트 전 구현 금지).

## 주의사항
- 킨더버스 쪽에서 "왜 바로 실행 안 되냐"는 질문이 나오면: CRITICAL 7은 성능과 무관하게 Confirm이 설계 원칙임을 안내(오발률 2% 상한과 별개의 이중 안전).
- required_slots가 null이라고 오류가 아니다 — 예약 필드다.

## 다음 단계
- 전략 원문: [02-two-track-strategy.md](02-two-track-strategy.md) · 등급 규칙 상세: docs/06-runtime-integration/two-track-launch-plan-v0.1.md
