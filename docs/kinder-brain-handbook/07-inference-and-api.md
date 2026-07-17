# 07. 추론과 API — 엔드포인트 전수 · infer 계약 · E2E 사례

> **한눈에 보기** — 백엔드(FastAPI, `backend/app/main.py`)는 라우터 7개 + `/healthz`, **총 33개 경로**를 서빙한다. 킨더버스(실서비스)가 장차 쓸 핵심은 `POST /v1/intent/infer` 단 하나이며, **현재는 mode=gym만 서빙**하고 live/shadow는 501로 막는다(PARTIAL HOLD). 나머지는 ② 훈련 도구(gym 세션·즉석 문답, 공부 검수 4종, 의도 목록 6종, 시험지 업로드·이력, 1~5 평점 출제 4종, 채점 트리거 2종)와 ③ 조회(3D 뇌·페르소나 오버레이·혼동 edge·노드 진단·애매 발화 리포트·대시보드)다. decision 판정 수치(clarify_margin 0.15, clarify_confidence 0.40, abstain_score 0.25)는 `config/experiments.yaml`의 `decision` 절이 유일한 원천이다(절대 규칙 1).

**이 문서의 JSON 예시에 대하여** — 필드 구성(형식)은 `schemas/*.json`·pydantic 계약의 실측이고, **값(숫자·id·문자열)은 전부 예시다.** 이 문서는 서버를 실행하지 않고 코드·스키마·검증 팩트팩만으로 작성했다.

상태 태그: `IMPLEMENTED`(구현·테스트 존재) / `PARTIAL`(일부만) / `DESIGNED`(계약·문서만) / `BLOCKED`(의도적 봉인) / `UNKNOWN`(미확인).

---

## 0. 공통 규약

- **베이스 URL**: 로컬 개발은 `http://localhost:8000` (`.claude/launch.json`의 `backend-dev`가 `node dev-backend.mjs`로 8000 포트에 기동). 프론트는 동일출처 프록시(`/v1`)로 호출한다. 교차 출처 배포 시에만 `CORS_ALLOW_ORIGINS` 설정 [근거: backend/app/main.py::app (CORS 미들웨어 조건부)].
- **인증**: 대부분 무인증(분리된 실험실 내부 도구). PIN 게이트는 딱 두 군데 —
  - 채점 트리거 `POST /v1/observatory/arena/run`: `ARENA_PIN`(기본 `2341`) [근거: backend/app/api/arena_ops.py::_pin]
  - 온톨로지 쓰기 3종(display 수정·bulk·제안 판정): `ONTOLOGY_PIN` → 없으면 `ARENA_PIN` → 없으면 `2341` [근거: backend/app/api/ontology_admin.py::_pin]
  - PIN은 **보안장치가 아니라 오클릭 방지 자물쇠**다(코드 주석 원문).
- **오류 형식**: FastAPI 표준 `{"detail": "<문구>"}`. 이 문서의 오류 문구는 코드에서 그대로 인용했다.
- **라우터 prefix**: `/v1/intent`(infer) · `/v1/gym` · `/v1/review` · `/v1/ontology` · `/v1/observatory`(observatory + dashboard + arena_ops 3개 라우터가 같은 prefix 공유) [근거: backend/app/api/*.py::router].

---

## 1. 엔드포인트 지도 (전수 — 누락 없음)

| 그룹 | METHOD 경로 | 목적 한 줄 | PIN | DB write | 상태 |
|---|---|---|---|---|---|
| ① 핵심 | POST `/v1/intent/infer` | 발화+컨텍스트 → 의도 추론 (mode=gym만 서빙) | — | ○ (inference_logs) | PARTIAL |
| ② 훈련 | POST `/v1/gym/pack` | 노드 진단 → Challenge Pack 생성(A형은 Foundry 작업주문) | — | ○ | IMPLEMENTED |
| ② 훈련 | POST `/v1/gym/session` | 강화하기 세션 열기(pack+items) | — | ○ | IMPLEMENTED |
| ② 훈련 | POST `/v1/gym/session/{session_id}/submit` | 트레이너 응답 → 에피소드+evidence 적재 | — | ○ | IMPLEMENTED |
| ② 훈련 | POST `/v1/gym/live/feedback` | 즉석 문답 사람 판정(확인/교정/출제/새 의도) | — | ○ | IMPLEMENTED |
| ② 검수 | GET `/v1/review/queue` | 공부 검수 blind 대기열 | — | × | IMPLEMENTED |
| ② 검수 | POST `/v1/review/vote` | 검수 표 제출(1인 1표, 재제출=갱신) | — | ○ | IMPLEMENTED |
| ② 검수 | POST `/v1/review/apply` | 2인 일치분 GOLD 확정 + backfill 자동 체인 | — | ○ | IMPLEMENTED |
| ② 검수 | GET `/v1/review/status` | 검수 진행 현황(표 수·ready 수) | — | × | IMPLEMENTED |
| ② 온톨로지 | GET `/v1/ontology/intents` | 의도 70종 카탈로그(표시 오버레이 병합) | — | × | IMPLEMENTED |
| ② 온톨로지 | PUT `/v1/ontology/intents/{intent_id}/display` | 한글 이름·설명 즉시 수정(표시 계층만) | ○ | ○ | IMPLEMENTED |
| ② 온톨로지 | POST `/v1/ontology/intents/display/bulk` | CSV 일괄 이름·설명 수정 | ○ | ○ | IMPLEMENTED |
| ② 온톨로지 | POST `/v1/ontology/change-requests` | 의미·구조 변경 제안 접수 | — | ○ | IMPLEMENTED |
| ② 온톨로지 | GET `/v1/ontology/change-requests` | 제안 목록(status 필터) | — | × | IMPLEMENTED |
| ② 온톨로지 | POST `/v1/ontology/change-requests/{request_id}/decide` | 제안 승인/반려(반영 예약 표시) | ○ | ○ | IMPLEMENTED |
| ② 시험지 | POST `/v1/observatory/ktib/upload` | 시험지 등록(YAML/구조화, dry-run→commit) + KTIB 동결 | — | ○(commit 시) | IMPLEMENTED |
| ② 시험지 | GET `/v1/observatory/ktib/uploads` | 업로드 이력 목록(등록분만) | — | × | IMPLEMENTED |
| ② 시험지 | GET `/v1/observatory/ktib/uploads/{upload_id}` | 업로드 상세(올린 원문 열람) | — | × | IMPLEMENTED |
| ② 시험지 | POST `/v1/observatory/ktib/candidates` | 1~5 평점 시험지 배치 작성(A) | — | ○ | IMPLEMENTED |
| ② 시험지 | GET `/v1/observatory/ktib/candidates` | 검수 대기(blind)+내 제출 목록 | — | × | IMPLEMENTED |
| ② 시험지 | POST `/v1/observatory/ktib/candidates/{batch_id}/review` | 2차 blind 1~5 평점 → 가중 kappa | — | ○ | IMPLEMENTED |
| ② 시험지 | POST `/v1/observatory/ktib/candidates/{batch_id}/register` | 합격 문항 KTIB 등록·동결 | — | ○(commit 시) | IMPLEMENTED |
| ② 채점 | POST `/v1/observatory/arena/run` | 채점(Arena) 백그라운드 시작 | ○ | ○(배경 잡) | IMPLEMENTED |
| ② 채점 | GET `/v1/observatory/arena/status` | 채점 진행·최근 결과·사전판정 | — | × | IMPLEMENTED |
| ③ 조회 | GET `/v1/observatory/brain` | 3D 뇌 렌더 상태(노드·region·stage) | — | × | IMPLEMENTED |
| ③ 조회 | GET `/v1/observatory/persona-overlay` | 클러스터별 persona prior 오버레이 | — | × | IMPLEMENTED |
| ③ 조회 | GET `/v1/observatory/node/{intent_id}/diagnosis` | WHY-WEAK 4축 진단 | — | × | IMPLEMENTED |
| ③ 조회 | GET `/v1/observatory/node/{intent_id}/confusions` | 노드 방향성 혼동쌍 | — | × | IMPLEMENTED |
| ③ 조회 | GET `/v1/observatory/confusion-edges` | 전 노드 혼동 edge(3D edge 레이어 원천) | — | × | IMPLEMENTED |
| ③ 조회 | GET `/v1/observatory/version-gate` | 후보 뇌 빌드 조건 상태(읽기 전용) | — | × | IMPLEMENTED |
| ③ 조회 | GET `/v1/observatory/ambiguity-report` | 애매 발화 인사이트(분포·교정·분류불능) | — | × | IMPLEMENTED |
| ③ 조회 | GET `/v1/observatory/dashboard` | 브레인 운영실 단일 집계 | — | × | IMPLEMENTED |
| — | GET `/healthz` | 생존 확인 `{"status":"ok"}` | — | × | IMPLEMENTED |

[근거: backend/app/main.py::include_router 7종, 팩트팩 "API 라우트 전수(grep @router)" 28행 + healthz — 본 표와 1:1 대조 완료]

---

## 2. ① 킨더버스 연결 핵심 — POST /v1/intent/infer

**상태: PARTIAL** — 계약(ir-0.2)은 3모드(live/shadow/gym)를 모두 통과시키지만 **서빙은 mode=gym뿐**. live/shadow는 `501 {"detail": "mode=gym만 서빙 (live/shadow rollout HOLD)"}` [근거: backend/app/api/infer.py::infer_endpoint]. live rollout(Suggest/Assist/Auto) 코드는 작성하지 않는다(CLAUDE.md PARTIAL HOLD).

### 2-1. 요청 계약 (infer_request, Core + extension 분리)

필수 필드 8개: `request_id`, `schema_version`, `mode`, `session`, `prompt`, `workspace_context`, `recent_actions`, `teacher_context` [근거: schemas/infer_request.schema.json::required]. 선택: `runtime_extension`, `gym_extension`, `shadow_extension`.

- `mode`: `"live" | "shadow" | "gym"` (enum).
- `prompt.text`: 최소 1자, `prompt.lang` 필수 [근거: backend/app/contracts/infer_request.py::PromptInfo].
- `session.conversation_history` 최대 6턴, `workspace_context.objects` 최대 50개, `recent_actions` 최대 10개.
- **절대 규칙 5(Core/extension 분리)**: `mode=live/shadow`에서 `gym_extension` 키가 존재하면(null 포함) 계약 거부 → HTTP **400** [근거: backend/app/contracts/infer_request.py::InferRequest._core_extension_separation]. `mode=gym`이어도 gym_extension(scenario_id·target_confusion 등 훈련 메타)은 **scorer의 Core 입력에 절대 섞이지 않는다** [근거: backend/app/brain/inference.py::core_signals — CoreSignals에 gym_extension 없음].
- 계약 위반·잘못된 JSON은 기본 422가 아니라 **400**으로 응답한다(상세는 서버 로그만, 응답은 일반 문구): `"잘못된 JSON 본문"` / `"유효하지 않은 infer 요청"` [근거: backend/app/api/infer.py::parse_infer_request].
- `schema_version`은 문자열 에코 필드다 — 서버가 특정 값(예: `ir-0.2`)을 강제 검증하지는 않는다 [근거: backend/app/contracts/infer_request.py::InferRequest].

### 2-2. 추론 파이프라인 (참고)

[1] RETRIEVAL(발화 임베딩 ↔ 노드 exemplar + Atlas 매치, `retrieval_top_k` 20) → [2] LLM SCORER(Core 신호만, 후보별 activation) → [3] PRIOR 재정렬(activation × persona/domain prior, `persona_prior_cap` 0.20 — LLM 밖에서 곱) → [4] 정규화(confidence·margin=top1−top2). 4단계 기여는 `inference_logs.stages`(JSONB)에 분리 기록 [근거: backend/app/brain/inference.py 모듈 docstring, config/experiments.yaml::brain].

### 2-3. 응답 계약 ir-0.2 — 필드 전수

[근거: backend/app/contracts/infer_response.py::InferResponse, schemas/infer_response.schema.json]

| 필드 | 타입 | 현재 서버 동작 |
|---|---|---|
| `request_id` | string | 요청 에코 |
| `schema_version` | string | 요청 에코 |
| `model_version` | string | 최신 promote된 brain_version, 없으면 `"seed-v0"` [근거: backend/app/api/infer.py::_model_version] |
| `ontology_version` | string | 현행 온톨로지(실측 `onto-2.1`) |
| `latency_ms` | int | 서버 측정 |
| `intent_candidates` | array ≤5 | 각 항목: `intent_id`, `domain`(8영역 enum), `score`(0~1), `risk_tier`(`LOW/MED/HIGH/CRITICAL`), `requires_confirmation`(bool), (`evidence`, `proposed_action`은 계약상 존재하나 현재 미기입 — 예약) |
| `top_intent` | string | 후보 1위, 후보 없으면 `"UNKNOWN"` |
| `confidence` | 0~1 | 정규화 확신도 |
| `margin` | 0~1 | top1−top2 |
| `is_multi_intent` | bool | **v1은 항상 false**(단일 의도) — true ⇔ `intent_plan` 필수라는 왕복 validator 존재 |
| `intent_plan` | object\|null | 항상 null(다중 의도는 후속) |
| `decision` | enum | `execute/suggest/clarify/abstain` — 현 엔진은 `suggest/clarify/abstain`만 방출(execute는 Stage 3 전용 어휘) [근거: backend/app/brain/decision.py::Decision] |
| `clarification` | object\|null | clarify일 때만 — `question` + `options`(정확히 2개, `{label, intent_id}`) |
| `abstain_reason` | enum\|null | `LOW_CONFIDENCE/OOD/DEADLINE_RISK` — 현재 방출은 앞 2개(DEADLINE_RISK는 live 예산 개념, 미방출) |
| `compute_elapsed_ms`, `remaining_budget_ms` | int\|null | 현재 미기입(예약) |
| `persona_state_version` | string | prior 미적용이면 `"ps-none"` |
| `persona_snapshot_hash` | string\|null | 현재 미기입(예약) |
| `fallback_used` | bool\|null | scorer 폴백 여부 |
| `risk_level` | enum\|null | **투트랙 채택 D 필드** — top 후보의 risk_tier와 일치해야 함(validator 강제), 후보 없으면 null [근거: backend/app/contracts/infer_response.py::_risk_level_consistency] |
| `required_slots` | array\|null | **예약 — 항상 null**(슬롯 추출은 트랙2 소관, 구현 전까지 지어내지 않음) |
| `context_used` | array\|null | 실제 소비한 문맥 블록 에코: `utterance` / `workspace_context` / `recent_actions` / `teacher_context` / `persona_prior` — 빈 블록은 넣지 않음(정직성) [근거: backend/app/api/infer.py::infer_endpoint] |

**직렬화 주의**: 라우터가 `response_model_exclude_none=True`라 **null인 필드는 응답 JSON에서 키 자체가 생략**된다(예: `required_slots`는 항상 null → 실제 응답엔 키가 안 보임) [근거: backend/app/api/infer.py::router.post("/infer", ..., response_model_exclude_none=True)].

**risk_tier 사상**: 리스크 모델(rm-1.0) `CRITICAL→CRITICAL`, `ELEVATED→HIGH`, `STANDARD→LOW`. `MED`는 대응 티어가 없어 현재 비어 있다(지어내지 않음). `requires_confirmation=true`는 **CRITICAL만** [근거: backend/app/api/infer.py::_RISK_TIER_MAP].

### 2-4. decision 정책 수치 (config 유일 원천)

[근거: config/experiments.yaml::decision, backend/app/brain/decision.py::decide]

| 키 | 값 | 의미 |
|---|---|---|
| `clarify_margin` | 0.15 | margin < 0.15 → 모호 |
| `clarify_confidence` | 0.40 | confidence < 0.40 → 모호 |
| `abstain_score` | 0.25 | **top_activation**(절대 강도) < 0.25 → abstain(LOW_CONFIDENCE) |
| `execute_confidence` / `execute_margin` | 0.75 / 0.25 | Stage 3 전용 — **현 단계 미사용** |
| `clarify_per_utterance_max` | 1 | 발화당 clarify 상한 |
| `clarify_per_session_max` | 3 | 세션당 clarify 상한(현재 라우터는 prior_clarify_count=0 고정 — 세션 상태 적재는 후속 과제) |

판정 사다리(약→강): ① 후보 0개 → `abstain(OOD)` ② top_activation < 0.25 → `abstain(LOW_CONFIDENCE)` ③ (margin<0.15 ∨ confidence<0.40) ∧ 후보≥2 → `clarify`(top-2 양자택일, 질문 `"어느 쪽에 가깝나요?"`) ④ 그 외 → `suggest`. abstain이 정규화 confidence가 아니라 절대 강도를 보는 이유: 단일 후보는 정규화상 confidence=1.0이 되어 약한 후보를 오판할 수 있다 [근거: backend/app/brain/decision.py 모듈 docstring].

### 2-5. 오류 전수

| HTTP | detail(원문) | 조건 |
|---|---|---|
| 400 | `잘못된 JSON 본문` | 본문 JSON 파싱 실패 |
| 400 | `유효하지 않은 infer 요청` | 계약 위반(절대 규칙 5 포함 — live/shadow의 gym_extension) |
| 501 | `mode=gym만 서빙 (live/shadow rollout HOLD)` | mode ≠ gym |

DB write: 성공 시 `inference_logs`에 mode·stages·confidence·margin 기록(팩트팩 실측: gym 8건·arena 756건). 관련 테스트: `backend/tests/test_infer_api.py`(400/501/clarify/abstain/risk 배선/required_slots 예약·context 에코 — 응답의 스키마 왕복 검증 포함), `backend/tests/test_inference.py`, `backend/tests/test_decision.py`.

---

## 3. ② 훈련 도구

### 3-1. Gym — `/v1/gym` [근거: backend/app/api/gym.py]

**POST `/v1/gym/pack`** — 노드 진단→강화 Challenge Pack 생성(§6-1·6-3·6-4). A형(데이터 부족)은 사람 세션 없이 Foundry 작업주문 발행. 요청: `{node_intent(필수), trigger(observatory_click|scheduled|version_gate_campaign)}`. 응답: `pack`(challenge_pack.schema.json 형태)·`diagnosis_codes`·`strategy`·`needs_human`·`node_priority`·`work_orders[]`. 오류: 404 `알 수 없는 intent`. DB write ○(작업주문·pack). 테스트: `backend/tests/test_challenge_pack.py`, `backend/tests/test_gym_api.py`. IMPLEMENTED

**POST `/v1/gym/session`** — 강화하기 세션 열기. 요청: `{trainer_ref, mode(guess_my_intent|choose_right_meaning|correction_drill), origin{node, region?, diagnosis?, target_confusion?}}`. 응답: `session_id`·`pack_id`·`mode`·`items[]`(item_id/utterance/candidate_intents/brain_guess). 오류: 422 `이 노드로 만들 훈련 아이템이 없습니다`. DB write ○(gym_sessions — 서버가 아이템을 보관해 발화·정답 위조 방지). 테스트: `backend/tests/test_gym_api.py`, `backend/tests/test_gym.py`. IMPLEMENTED

**POST `/v1/gym/session/{session_id}/submit`** — 트레이너 응답 제출 → GYM_HUMAN 에피소드 + HUMAN evidence + aggregator 전이 + 노드 size/density + pending 링(§6-7 [5][6]). 요청: `{results:[{item_id, chosen_intent, brain_guess?, recovery_turns≥0}]}`. 응답: `episodes_created`·`evidence_created`·`by_type`·`node_intent`·`episodes_aggregated`·`label_states`·`pending_set`. 오류: 404 `세션 없음`, 409 `이미 제출된 세션입니다`(멱등 가드 — 더블클릭·재시도가 노드 size를 이중 계상하는 것 차단). brightness는 절대 건드리지 않음(절대 규칙 3). 테스트: `backend/tests/test_gym_api.py`, `backend/tests/test_click_to_train_e2e.py`. IMPLEMENTED

**POST `/v1/gym/live/feedback`** — 즉석 문답의 **사람 판정**만 받는다(추론 자체는 클라이언트가 먼저 `/v1/intent/infer` 호출 — 정답이 추론 입력에 들어갈 길이 없음, 절대 규칙 5). 요청: `{feedback_id(6~64자 `[A-Za-z0-9_-]`), trainer_ref, utterance, chosen_intent?, brain_top_intent?, intent_candidates[], inference_request_id?, suggest_new_intent(bool), purpose(training|benchmark)}`. 응답: `kind(confirmation|correction|benchmark_queued|atlas_queued)` + 적재 리포트. 분기:
- 확인/교정(purpose=training): HUMAN_CONFIRMATION 또는 HUMAN_CORRECTION evidence 적재.
- 출제(purpose=benchmark): 학습에 쓰지 않고 출제 대기열(`seeds/benchmark_candidates.yaml`)로만 [근거: backend/app/gym/live.py::BENCHMARK_QUEUE_PATH].
- 새 의도 제안(suggest_new_intent=true): `atlas_expansion_queue` 등록(`AX_` id), 노드 자동 생성 없음(절대 규칙 4).

오류: 422 `새 의도 제안과 기존 의도 선택은 동시에 할 수 없습니다` / 422 `chosen_intent가 필요합니다` / 422 `온톨로지에 없는 intent: <id>` / 409(학습·시험 오염 — TrainBenchmarkContamination 문구 그대로) / 409 `이미 출제 대기 중인 발화입니다: <발화>` / 409 `이미 반영된 문답입니다`(feedback_id 멱등). 테스트: `backend/tests/test_gym_live.py`. IMPLEMENTED

### 3-2. 공부 검수 — `/v1/review` [근거: backend/app/api/review.py]

GOLD를 만드는 웹 경로. 승격 규칙은 재구현하지 않고 `aggregator.review.apply_review_batch`(GOLD 유일문)에 그대로 위임 — 우회 없음(§3-3).

**GET `/v1/review/queue?reviewer=&limit=50`** — blind 대기열(발화·언어·채널만 — 다른 검수자의 표·집계 제안 절대 미포함, 앵커링 방지). 응답: `reviewer`(정규화 신원)·`total_reviewable`·`my_done`·`items[]`. 오류: 422 `검수자 이름을 입력해주세요`. DB write ×. IMPLEMENTED

**POST `/v1/review/vote`** — `{reviewer, episode_id, chosen_intent|null}`(null=폐기 표). 한 사람 한 표(재제출=갱신, `updated:true`). 오류: 404 `에피소드를 찾을 수 없어요`, 409 `이미 확정됐거나 검수 대상이 아니에요`, 422 `온톨로지에 없는 의도예요 — 목록에서 골라주세요`. DB write ○(review_votes). IMPLEMENTED

**POST `/v1/review/apply`** — `{approved_by}`. 서로 다른 검수자 `min_reviewers`(2) 미만이면 409: `` 검수자 2인 이상의 표가 필요해요 — 지금은 N인이에요 (1인 확정 금지 §3-3) ``. 배치 kappa < `min_agreement_kappa`(0.65)면 **전량 거부**(부분 승격 금지) — 409로 문구 그대로 반환. 성공 시 GOLD가 생겼으면 `run_backfill`(대표 예문) **자동 체인**(멱등 — 실패해도 확정은 유지, 다음 적용에서 따라잡음). 응답: `labeled/rejected/unchanged/kappa/exemplars_added/message`. 그 밖의 오류: 422 `승인자 이름을 입력해주세요`, 409 `적용할 검수 표가 없어요`. DB write ○(episodes 상태 전이·exemplars). 테스트: `backend/tests/test_review_api.py`, `backend/tests/test_human_review.py`. IMPLEMENTED

**GET `/v1/review/status`** — `reviewable_total`·`ready_total`(2인 이상 표가 모인 에피소드 수)·`reviewers[]`(이름·표 수). DB write ×. IMPLEMENTED

### 3-3. 의도 목록·표시 수정·변경 제안 — `/v1/ontology` [근거: backend/app/api/ontology_admin.py]

계층 분리: **표시 계층**(한글 이름·설명 = intent_display 오버레이, PIN 후 즉시 수정) vs **의미·구조**(YAML — 제안 대기열로만, 승인은 '반영 예약'일 뿐 실반영은 §5-9 거버넌스 경로). intent_id는 어디서도 수정 불가. 모든 쓰기는 governance_events 기록.

| 엔드포인트 | 요점 | 오류(원문) |
|---|---|---|
| GET `/intents` | 카탈로그(ontology_version·total·items[intent_id/domain/definition/example_count/name_ko/description_ko]) — write × | — |
| PUT `/intents/{intent_id}/display` | `{pin, edited_by, name_ko?, description_ko?}` → 즉시 반영 + GOV 이벤트 | 401 `비밀번호가 달라요` / 422 `수정자 이름을 입력해주세요` / 404 `온톨로지에 없는 의도예요` / 422 `바꿀 내용(이름 또는 설명)을 입력해주세요` |
| POST `/intents/display/bulk` | CSV행 일괄 `{pin, edited_by, rows[]}` — 목록에 없는 id는 건너뜀(구조 변경 CSV 우회 불가). 응답 `applied/skipped/message` | 401 / 422 (동일 문구) |
| POST `/change-requests` | `{kind(DEFINITION\|ADD\|MOVE\|DELETE\|OTHER), proposal, proposed_by, intent_id?}` 접수 | 422 `제안 내용과 제안자 이름을 입력해주세요` / 404 `온톨로지에 없는 의도예요` |
| GET `/change-requests?status=` | 제안 목록 — write × | — |
| POST `/change-requests/{request_id}/decide` | `{pin, decision(approve\|reject), decided_by}` — 승인 메시지: "승인 완료 — 의미·구조 반영은 버전 규칙에 따라 운영 경로로 진행돼요(반영 예약)." | 401 / 422 `판정자 이름을 입력해주세요` / 404 `제안을 찾을 수 없어요` / 409 `이미 판정된 제안이에요 (STATUS)` |

테스트: `backend/tests/test_ontology_admin.py`. IMPLEMENTED (단, 승인된 제안의 **실반영 자동화는 없음** — DESIGNED, 운영 경로 수동)

### 3-4. 시험지(KTIB) 업로드·이력 — `/v1/observatory/ktib/upload*` [근거: backend/app/api/observatory.py::ktib_upload]

**POST `/ktib/upload`** — 전문가 저작 시험 문항 등록의 웹 진입점. 입력 2방식: A) `yaml_text` 원문 B) 구조화 `{episodes[{teacher_prompt, intent, episode_id?, lang, reviewers[], agreement_kappa?, agreement_rate?}], authored_by, approved_by}`. `commit:false`=검증만(dry-run, savepoint 롤백 — DB 불변), `true`=적재 + BENCHMARK_HOLDOUT이면 KTIB 동결 + 업로드 이력 1행(원문 보관). §3-3 인증은 **kappa ≥ 0.65 OR 관측 일치율 ≥ 0.80(O/X 승인, v1.6)** [근거: backend/app/foundry/expert_ingest.py, config/experiments.yaml::review]. 거부(합성 채널·검수 미달·학습 오염·미지 intent·빈 KTIB)는 HTTP 200 + `{ok:false, message:"거부: <사유>"}`. 형식 오류는 400: `YAML 형식 오류: …` / `'<key>' 항목을 채워주세요` / `episodes(문항)가 비어 있습니다` / `문항이 비어 있습니다` / `작성자를 입력해주세요`·`승인자를 입력해주세요` / `N번째 행의 발화/의도를 채워주세요`. **채점은 여기서 하지 않는다**(운영자 별도 — 과금·장시간). 테스트: `backend/tests/test_observatory_api.py`, `backend/tests/test_expert_ingest.py`, `backend/tests/test_ktib.py`. IMPLEMENTED

**GET `/ktib/uploads`** — 이력 목록(최근순, 등록분만·경량). **GET `/ktib/uploads/{upload_id}`** — 상세(+`source_document` 원문). 404 `업로드 기록을 찾을 수 없어요`. write ×. IMPLEMENTED

### 3-5. 시험지 후보 1~5 평점(2인 blind) — `/v1/observatory/ktib/candidates*` [근거: backend/app/api/observatory.py]

흐름: A가 문항+1~5 제출(create) → `AWAITING_SECOND` → 다른 사람 B가 blind 1~5(review, rating_a 절대 미노출 — anti-anchoring) → 가중 kappa ≥ 0.65 ∧ 양쪽 모두 `min_item_rating`(4)↑ 문항 존재 → register(dry-run→commit)로 KTIB 동결. 스테이징은 episodes가 아닌 별도 표 — 등록만 `ingest_expert_episodes` 경유, `benchmark_integrity` CHECK가 최종 방어(절대 규칙 2).

| 엔드포인트 | 오류(원문) |
|---|---|
| POST `/ktib/candidates` `{reviewer, items[{intent, teacher_prompt, rating}]}` | 400 `검수자 이름을 입력해주세요` / 400 `문항이 비어 있습니다` / 400 `N번째 문항의 질문/의도를 채워주세요` / 422 `온톨로지에 없는 의도입니다: <id>` / 422 `N번째 문항 점수는 1~5여야 합니다` / 409 `배치 안에 같은 질문이 중복됩니다: <발화>` / 409 `이미 학습 문항에 있는 질문입니다: <발화>`(오염 가드) |
| GET `/ktib/candidates?reviewer=` (pending=남의 대기 blind + mine=내 배치 상태) | — |
| POST `/ktib/candidates/{batch_id}/review` `{reviewer, ratings[]}` | 404 `검수 대상을 찾을 수 없습니다` / 400 `검수자 이름을 입력해주세요` / 409 `1차 검수자와 다른 사람이어야 해요 (같은 이름·대소문자만 다른 건 한 사람)` / 409 `이미 2차 검수가 끝난 시험지입니다` / 400 `모든 문항을 평가해주세요` / 422 `점수는 1~5여야 합니다` |
| POST `/ktib/candidates/{batch_id}/register` `{reviewer, commit}` | 404 `등록 대상을 찾을 수 없습니다` / 409 `이미 등록된 시험지입니다` / 409 `아직 2차 검수가 끝나지 않았습니다` / 409 `서로 다른 두 검수자가 필요합니다` / 409 `검수 일치도가 기준에 못 미쳐 등록할 수 없습니다 (2차 검수를 다시 확인해주세요)` / 409 `두 검수자가 모두 높게 평가한 문항이 없어 등록할 수 없습니다` |

테스트: `backend/tests/test_benchmark_candidates.py`. IMPLEMENTED

### 3-6. 채점 트리거 — `/v1/observatory/arena/*` [근거: backend/app/api/arena_ops.py]

**POST `/arena/run`** `{pin}` → **202** `{started:true, message:"채점을 시작했어요 — 문항 수에 따라 몇 분 걸려요. 끝나면 점수가 바로 반영돼요."}`. 백그라운드에서 `scripts/run_arena.py` base 경로와 동일 체인(latest_ktib → run_arena → reflect_arena_run(promoted=False) → commit) 실행. brightness는 reflect(Arena 반영 경로)만 접근 — 절대 규칙 3 우회 없음. 오류: 401 `비밀번호가 달라요` / 409 사전판정 4조건 문구(아래 §11 운영 가이드 E 참조 — mock provider·시험지 없음·대표 예문 0·새 유입 없음) / 409 `이미 채점이 실행 중이에요`(동시 실행 1개, 모듈 락).

**GET `/arena/status`** — `{running, started_at, error, last_run{run_id, accuracy, item_count, created_at}, runnable, blocked_reason}`. 사전판정과 409 가드가 **같은 문구**를 공유(버튼 회색 안내). write ×. 테스트: `backend/tests/test_arena_ops_api.py`. IMPLEMENTED

---

## 4. ③ 조회 (Observatory·Dashboard)

모두 GET·무인증·DB write ×. [근거: backend/app/api/observatory.py, backend/app/api/dashboard.py]

- **GET `/v1/observatory/brain`** — 3D 뇌 상태: `brain_version`·`ontology_version`·`ktib_global`(최신 run_type='brain' arena run만 — zero-shot 베이스라인은 3D에 새지 않음)·`brain_stage`·`regions[]`(reliability=비null heldout 평균·stage)·`nodes[]`(evidence_total/diversity(버킷 섀넌 엔트로피)/gold_count/exemplar_count/heldout_accuracy(Arena 전용 컬럼 통과)/calibration_ece/pending_evaluation/evidence_buckets). 어떤 값도 지어내지 않음 — 측정 전은 null. 테스트: `backend/tests/test_observatory_api.py`. IMPLEMENTED
- **GET `/v1/observatory/persona-overlay`** — 클러스터별 **prior 배수만** 노출(측정 지표 아님 — Lift/Harm은 arena metrics에 동결). 클러스터 없으면 빈 목록. `prior_cap`(0.20) 동봉. 테스트: `backend/tests/test_observatory_api.py`. IMPLEMENTED
- **GET `/v1/observatory/node/{intent_id}/diagnosis`** — WHY-WEAK 4축(ambiguous_language / screen_context_coverage / persona_diversity / gold_data), 각 `{value, level(HIGH|MED|LOW)}` — 데이터 없으면 null. 404 `알 수 없는 intent`. 테스트: `backend/tests/test_diagnosis.py`. IMPLEMENTED
- **GET `/v1/observatory/node/{intent_id}/confusions`** — 방향성 혼동쌍(from_true=이 노드). `confusion_rate`는 Arena 측정 전 null(가설 edge — mock 아님). 404 `알 수 없는 intent`. IMPLEMENTED
- **GET `/v1/observatory/confusion-edges`** — 전 edge(`total`·`measured_count`·대표 정렬: 측정→rate→state(confirmed>observed>hypothesized)→이름). 실측: 629 edge 전부 hypothesized/SKEPTIC. IMPLEMENTED
- **GET `/v1/observatory/version-gate`** — `{base_version, new_gold, min_new_gold(200), condition_met, pending_candidate}` — 읽기 전용(후보 빌드는 `scripts/run_version_gate.py`). 테스트: `backend/tests/test_version_gate.py`. IMPLEMENTED
- **GET `/v1/observatory/ambiguity-report`** — 애매 발화 인사이트(투트랙 B′): `thresholds`(config 에코 — clarify_margin/clarify_confidence), `sources[]`(mode별 total/ambiguous/의도 분포 — margin·confidence가 null이거나 임계 미만이면 애매로 집계), `corrections[]`(HUMAN_CORRECTION 최근 50 — 발화/사람 정답/뇌 추측), `unclassified[]`(atlas 큐 최근 50). 읽기 전용. 테스트: `backend/tests/test_ambiguity_report.py`. IMPLEMENTED
- **GET `/v1/observatory/dashboard`** — 운영실 단일 집계: `config`(기준선 4종 에코 — 프론트 하드코딩 금지), `scoreboard`(시험지 등록·대기, critical 충족, TRAIN/GOLD, 채널, 사람 evidence, 검수 대기 배치), `inflow`(4스트림 7일), `performance`(run 타임라인·delta_pp — 첫 run은 null, 0.0 위장 금지), `expansion`(의도 수·atlas 큐), `review_inbox`, `intents[]`(의도별 행 — critical 하한 갭 포함). ktib_global·stage는 의도적으로 **없음**(/brain이 단일 원천). 테스트: `backend/tests/test_dashboard_api.py`. IMPLEMENTED
- **GET `/healthz`** — `{"status":"ok"}`. 테스트: `backend/tests/test_healthz.py`. IMPLEMENTED

---

## 5. E2E 사례 6개 (문서 전체 공통 고정 사례)

공통 요청 스켈레톤 — **형식은 스키마 실측, 값은 예시**(이하 모든 사례 동일. `mode`는 항상 `"gym"` — 다른 모드는 501):

```json
{
  "request_id": "REQ_ex001",
  "schema_version": "ir-0.2",
  "mode": "gym",
  "session": {"session_id": "S_demo", "surface_type": "workspace", "conversation_history": []},
  "prompt": {"text": "<발화>", "lang": "ko"},
  "workspace_context": {"objects": [], "selection": []},
  "recent_actions": [],
  "teacher_context": {"teacher_ref": "T_kim"}
}
```

### 사례 ① CRITICAL 전송 — "민준이 어머님께 오늘 약을 먹지 않았다고 알려줘."

응답(예시 값):

```json
{
  "request_id": "REQ_ex001",
  "schema_version": "ir-0.2",
  "model_version": "seed-v0",
  "ontology_version": "onto-2.1",
  "latency_ms": 840,
  "intent_candidates": [
    {"intent_id": "comm_message_individual_parent", "domain": "COMMUNICATION",
     "score": 0.81, "risk_tier": "CRITICAL", "requires_confirmation": true},
    {"intent_id": "op_notice_send", "domain": "OPERATION",
     "score": 0.24, "risk_tier": "CRITICAL", "requires_confirmation": true}
  ],
  "top_intent": "comm_message_individual_parent",
  "confidence": 0.77, "margin": 0.57,
  "is_multi_intent": false,
  "decision": "suggest",
  "persona_state_version": "ps-none",
  "fallback_used": false,
  "risk_level": "CRITICAL",
  "context_used": ["utterance"]
}
```

흐름: 개별 학부모 전송은 리스크 모델 rm-1.0의 CRITICAL 7종 — `requires_confirmation=true`가 항상 켜지고 `risk_level`도 CRITICAL로 에코된다. 여기서 `decision:"suggest"`는 **브레인의 판정 라벨이지 실서비스 자동 실행이 아니다**(PARTIAL HOLD) — 킨더버스 연결 시에도 CRITICAL은 실행 전 사람 확인 게이트가 전제다(CWAR 게이트 대상) [근거: seeds/risk_model_v1.yaml — rm-1.0, backend/tests/test_infer_api.py::test_critical_top_intent_wires_risk_model].

### 사례 ② 애매 — "오늘 찍은 거 부모님께 보여드리자."

사진 공유(comm_share_media_with_parents)와 알림 발송(op_notice_send)이 경합 → margin < 0.15 → `clarify`(top-2 양자택일):

```json
{
  "top_intent": "comm_share_media_with_parents",
  "confidence": 0.46, "margin": 0.06,
  "intent_candidates": [
    {"intent_id": "comm_share_media_with_parents", "domain": "COMMUNICATION",
     "score": 0.52, "risk_tier": "CRITICAL", "requires_confirmation": true},
    {"intent_id": "op_notice_send", "domain": "OPERATION",
     "score": 0.46, "risk_tier": "CRITICAL", "requires_confirmation": true}
  ],
  "decision": "clarify",
  "clarification": {
    "question": "어느 쪽에 가깝나요?",
    "options": [
      {"label": "comm_share_media_with_parents", "intent_id": "comm_share_media_with_parents"},
      {"label": "op_notice_send", "intent_id": "op_notice_send"}
    ]
  },
  "risk_level": "CRITICAL", "context_used": ["utterance"]
}
```

(축약 — 공통 필드 생략. `options.label`은 서버가 intent_id를 넣고 UI가 친화 명칭으로 매핑한다 [근거: backend/app/brain/decision.py::_clarification].) 이 clarify 로그가 곧 애매 발화 리포트(`/ambiguity-report`)의 원자료가 된다.

### 사례 ③ 후보엔 있으나 top이 틀림 → 즉석 문답에서 사람이 교정

infer 응답(예시): 발화 "지금 이 장면 남겨줘" → top이 `obs_record_moment`(score 0.55)로 나왔지만 정답은 후보 2위 `obs_capture_scene`. 훈련자가 즉석 문답 화면에서 정답을 고르면 클라이언트가 다음을 보낸다:

```json
POST /v1/gym/live/feedback
{
  "feedback_id": "FB_20260717_0001",
  "trainer_ref": "T_kim",
  "utterance": "지금 이 장면 남겨줘",
  "chosen_intent": "obs_capture_scene",
  "brain_top_intent": "obs_record_moment",
  "intent_candidates": ["obs_record_moment", "obs_capture_scene", "doc_observation_record"],
  "inference_request_id": "REQ_ex003",
  "purpose": "training"
}
```

응답(예시): `{"kind": "correction", "episode_id": "EP_a1b2c3", "evidence_created": 1, "episodes_aggregated": 1, "label_states": {"EVIDENCE_ACCUMULATING": 1}, "pending_set": true, "node_intent": "obs_capture_scene"}` — **HUMAN_CORRECTION evidence**(가장 강한 인간 신호)가 적재되고 노드는 pending 링만 켜진다(밝기는 다음 Arena까지 불변, 절대 규칙 3).

### 사례 ④ 온톨로지에 없는 발화 → abstain(OOD) → 새 의도 제안

발화 "교실 화분에 물 준 기록 좀 정리해줘" — retrieval이 후보를 못 찾으면:

```json
{
  "top_intent": "UNKNOWN",
  "intent_candidates": [],
  "confidence": 0.0, "margin": 0.0,
  "decision": "abstain",
  "abstain_reason": "OOD",
  "persona_state_version": "ps-none",
  "context_used": ["utterance"]
}
```

(축약. 후보가 없으므로 `risk_level`은 null → 키 생략.) 이어서 훈련자가 "딱 맞는 의도가 없어요 — 새 의도로 제안하기"를 누르면 `POST /v1/gym/live/feedback`에 `{"suggest_new_intent": true, "chosen_intent": null, ...}` → 응답 `{"kind": "atlas_queued", "atlas_queue_id": "AX_9f8e7d6c5b4a"}` — **atlas_expansion_queue**에 쌓이고, 노드 생성은 승인 플로우(거버넌스)로만 진행된다(절대 규칙 4).

### 사례 ⑤ 비가역 삭제 — "이거 다시 안 쓸 거야. 지워줘."

`workspace_context.selection: ["obj_12"]`을 채워 보내면 응답(예시)은 `top_intent: "op_workspace_delete"`(D: 비가역 데이터 파괴, CRITICAL) — `requires_confirmation: true`, `risk_level: "CRITICAL"`, `decision: "suggest"`, `context_used: ["utterance", "workspace_context"]`. 실행 전 확인이 계약 수준에서 강제 표기된다 — 킨더버스가 이 플래그를 무시하면 안 되는 것이 연동 규약의 핵심.

### 사례 ⑥ 전반적으로 약함 → abstain(LOW_CONFIDENCE)

발화 "그거 있잖아, 그거 좀…" — 후보는 있으나 top_activation < `abstain_score`(0.25):

```json
{
  "top_intent": "play_expand",
  "intent_candidates": [
    {"intent_id": "play_expand", "domain": "PLAY", "score": 0.18,
     "risk_tier": "LOW", "requires_confirmation": false}
  ],
  "confidence": 1.0, "margin": 0.18,
  "decision": "abstain",
  "abstain_reason": "LOW_CONFIDENCE",
  "risk_level": "LOW",
  "context_used": ["utterance"]
}
```

(축약.) 단일 후보라 정규화 confidence는 1.0으로 나올 수 있어도 **절대 강도(top_activation)가 임계 미만이면 abstain** — 이것이 abstain 판정이 confidence가 아니라 top_activation을 보는 이유다 [근거: backend/app/brain/decision.py::decide, backend/tests/test_infer_api.py::test_weak_top_abstains]. UI는 "브레인이 아직 이 말을 몰라요 — 정답을 알려주시면 배웁니다"로 안내하고 사례 ③의 교정 경로로 이어진다.

---

## 현재 상태

- 33개 경로 전부 구현·라우팅 완료(IMPLEMENTED), 단 `POST /v1/intent/infer`는 **PARTIAL** — mode=gym만 서빙, live/shadow 501(PARTIAL HOLD). `decision=execute`·`DEADLINE_RISK`·`intent_plan`·`required_slots`·`evidence/proposed_action`·`compute_elapsed_ms/remaining_budget_ms/persona_snapshot_hash`는 계약 어휘만 존재하는 예약(DESIGNED).
- 서빙 뇌 버전: brain_versions에 promote가 없어 `model_version="seed-v0"` (팩트팩 실측: brain_versions 0건).
- inference_logs 실측: arena 756 · gym 8. confusion_edges 629 전부 hypothesized(SKEPTIC) — 3D edge는 정직하게 "가설"로 표시된다.
- 시험지: ktib-3(386문항, 의도 커버 8/70 — CRITICAL 7 + doc_observation_record). 채점 이력: brain run 0.0% 2회(exemplar 0 — 정직한 0), zero-shot 베이스라인 88.1%(claude-sonnet-5, ktib-2).

## 주의사항

- **infer의 계약 위반은 422가 아니라 400이다**(단, pydantic 검증을 쓰는 다른 라우터 — gym·review 등 — 는 FastAPI 기본 422). 클라이언트 오류 처리를 나눠 짜야 한다.
- `response_model_exclude_none=True` — infer(및 live/feedback) 응답에서 null 필드는 **키가 생략**된다. "필드가 없음"과 "null"을 같은 뜻으로 다뤄야 한다.
- `risk_level`은 편의 필드 — 최상위 후보 `risk_tier`와 어긋나면 서버가 계약 위반으로 터뜨린다(클라이언트는 어느 쪽을 읽어도 같아야 정상).
- KTIB 업로드·등록의 "거부"는 HTTP 200 + `ok:false`다(형식 오류만 400) — 상태코드만 보고 성공 처리하면 안 된다.
- 채점(arena/run)은 요청이 202로 즉시 돌아오고 실제 작업은 백그라운드 — 완료·실패는 `/arena/status` 폴링으로만 알 수 있다(에러도 status의 `error` 필드로 정직하게 노출).
- 훈련 메타데이터(ground truth·scenario_id 등)는 mode=gym이어도 추론 Core에 절대 넣지 않는다(절대 규칙 5) — 즉석 문답의 정답은 항상 **추론이 끝난 뒤** `/v1/gym/live/feedback`으로 도착한다.

## 다음 단계

- 킨더버스 연결(트랙2) 시: live/shadow 서빙 해제는 문서 §10-2 게이트(CWAR·Recovery·지연 목표) 충족 + 사용자 승인 후에만. `required_slots` 슬롯 추출 구현도 트랙2 소관.
- decision의 세션별 clarify 이력(prior_clarify_count) 적재 — 현재 라우터가 0 고정이라 `clarify_per_session_max`(3)가 실질 미작동(후속 과제로 코드 주석에 명시됨).
- 다중 의도(is_multi_intent/intent_plan) 및 IntentCandidate.evidence/proposed_action 채우기 — 계약은 준비돼 있고 서버 기입만 남음.
- 애매 발화 리포트는 mode 축(gym → live/shadow)으로 오픈 후에도 같은 화면이 이어지도록 설계돼 있다 — 연결 후 재검증만 하면 된다.
