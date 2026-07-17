# 10. 안전과 거버넌스 — 불변 원칙과 그것을 강제하는 장치

> **한눈에 보기** — 킨더브레인의 안전은 "조심하겠다"는 다짐이 아니라 **DB CHECK·가드 코드·유일문 함수·테스트**로 물리화돼 있다. 이 장은 원칙 하나하나에 "무엇이 강제하는가"를 붙이고, 코드로 강제되지 않는 것(개인정보·보존 정책 등)은 숨기지 않고 GAP으로 표시한다.

---

## 1. 쉬운 설명 — 왜 "장치"가 필요한가

규칙은 바쁘면 잊힌다. 그래서 이 시스템은 중요한 규칙을 **어기려는 코드가 실행되면 그 자리에서 실패**하게 만들었다. 예: 시험 문항을 합성 데이터로 채우려는 INSERT는 사람이 아무리 승인해도 DB가 거부한다.

---

## 2. 불변 원칙 × 강제 장치 표

| # | 원칙 | 강제 장치 | 상태 |
|---|---|---|---|
| 1 | 숫자 임계값은 config 단일 원천(코드 리터럴 금지) | 전 모듈이 `get_config()` 경유, 목표·게이트 테스트가 config 상대값으로 작성 | IMPLEMENTED(관례+테스트) [근거: backend/app/core/config.py, config/experiments.yaml] |
| 2 | 시험지 무결성: BENCHMARK_HOLDOUT ⇒ GOLD ∧ LABELED ∧ 비합성 | **DB CHECK `benchmark_integrity`** — 코드 우회 불가 | IMPLEMENTED [근거: backend/app/models/episodes.py CHECK, CLAUDE.md 규칙 2] |
| 3 | brightness(점수·밝기)는 Arena만 갱신 | 가드 컨텍스트 밖 쓰기 시 예외 `BrightnessWriteBlocked` + 테스트 | IMPLEMENTED [근거: backend/app/models/guards.py, backend/tests/test_observatory_api.py::test_training_changes_size_not_brightness] |
| 4 | 노드·의도 자동 생성 금지 | 생성은 governance_events 남기는 부트스트랩·승인 플로우만, 신규 후보는 큐 대기 | IMPLEMENTED [근거: backend/app/brain/backfill.py::bootstrap_nodes, backend/app/models/foundry.py::AtlasExpansionEntry, backend/app/api/ontology_admin.py] |
| 5 | 훈련 메타데이터의 추론 입력(Core) 침범 금지 | 계약 검증 — live/shadow에 gym_extension 실리면 400 | IMPLEMENTED [근거: backend/app/contracts/infer_request.py, backend/tests/test_infer_api.py] |
| 6 | adversarial 데이터는 자연 분포 집계에서 분리 | 집계 함수가 adversarial=true 제외 | IMPLEMENTED(현재 데이터 0건) [근거: backend/app/aggregator/aggregator.py] |
| 7 | TRAIN ↔ BENCHMARK 상호 오염 금지 | dedup_hash(split 미포함) + 유입 시 원문 대조 거부 + exemplar에서 HOLDOUT 제외 | IMPLEMENTED [근거: backend/app/foundry/expert_ingest.py::_assert_no_train_contamination, backend/app/brain/backfill.py] |
| 8 | label_state와 reliability_tier 혼용 금지 + GOLD⇒LABELED | 상태기계(합법 전이만) + DB CHECK gold_requires_labeled | IMPLEMENTED [근거: backend/app/aggregator/state_machine.py, db/migrations 0002] |
| 9 | provenance 4필드 필수(생성 주체 역추론 금지) | episodes·evidence CHECK로 허용값 강제 | IMPLEMENTED [근거: backend/app/models/episodes.py CHECK 목록] |
| 10 | GOLD는 인간 2인 일치로만 | **유일문** apply_review_batch — 2인·만장일치·배치 kappa≥0.65(또는 O/X 경로 일치율≥0.80) 미달 시 전량 거부 | IMPLEMENTED [근거: backend/app/aggregator/review.py, backend/app/foundry/expert_ingest.py] |
| 11 | 시험 발화는 사람이 작성(LLM 생성 금지) | **코드로 탐지 불가** — authored_by 필수 + 거버넌스 기록 + 운영 원칙 | PARTIAL(정책+감사) [근거: backend/app/foundry/expert_ingest.py 머리말] |
| 12 | 위험 의도 실행 전 확인 | 응답 계약: CRITICAL 7 → requires_confirmation=true(리스크 모델 파생, top-level risk_level과 일치 validator) | 계약 IMPLEMENTED · 실행 UI는 트랙 2 DESIGNED [근거: backend/app/api/infer.py::_RISK_TIER_MAP, backend/app/contracts/infer_response.py::_risk_level_consistency] |
| 13 | 리스크 등급 ↔ config 정합 | validate_schemas가 rm-1.0 CRITICAL 집합과 config.arena.critical_intents 불일치 시 loud-fail | IMPLEMENTED [근거: scripts/validate_schemas.py, backend/app/core/risk_model.py::assert_config_coherence] |
| 14 | 롤백 가능 | 서빙=최신 promote → 문제 버전 reject 기록만으로 직전 복귀(데이터 무삭제) + 런북 | IMPLEMENTED(구조)·런북 문서화 [근거: backend/app/api/infer.py::_model_version, docs/09-teacher-guide/internal-alignment.md §5] |
| 15 | 감사 추적(audit) | governance_events(승인 이력) + inference_logs(판정 전건) + ktib_uploads(원문 보관) + 의도 수정·판정 기록 + evidence의 inference_request_id 연결 | IMPLEMENTED [근거: backend/app/models/governance.py, gym/live.py context] |
| 16 | 외부 노출 차단 | public 전 테이블 RLS ON(무정책=전부 거부) + 새 테이블 누락 시 테스트 실패 | IMPLEMENTED [근거: db/migrations/versions/0016_enable_rls_public.py, backend/tests/test_rls.py] |
| 17 | 오클릭 방지 잠금 | 채점·의도 수정에 PIN(기본 2341) — **보안장치가 아니라 실수 방지**임을 명시 | IMPLEMENTED [근거: backend/app/api/arena_ops.py::_pin, backend/app/api/ontology_admin.py] |

---

## 3. 코드로 강제되지 않는 영역 — 정직한 GAP

| 항목 | 현재 상태 | 표시 |
|---|---|---|
| 개인정보 비식별화 파이프라인 | Shadow 0a 진입 게이트로 "PII 게이트·최소 수집" **문서 요건**만 존재, 코드 없음 | DESIGNED / **GAP** [근거: docs/06-runtime-integration/README.md §2] |
| 실제 교사 데이터 사용 동의(옵트아웃 포함) | 거버넌스 7항목 문서 요건 — 절차·문안 미작성 | **GAP** (11월 전 필수 — [14장](14-current-status-and-roadmap.md)) |
| 데이터 보존·삭제 정책 | 명문 정책 없음(REJECTED 데이터·로그 보존 기한 미정) | **GAP** |
| 아동 이름 등 발화 내 식별정보 | 현재 훈련 발화는 내부 작성분 — 실데이터 유입 전 마스킹 정책 필요 | **GAP** |
| 시험 발화의 LLM 생성 탐지 | 원리적으로 코드 탐지 불가 — 운영 통제만 | 상시 PARTIAL |

이 GAP들은 [17-open-questions-and-gaps.md](17-open-questions-and-gaps.md)에 중요도·권장 조치와 함께 재수록돼 있다.

## 현재 상태
- 데이터 무결성·승격 게이트·감사: 코드 강제 IMPLEMENTED가 다수.
- 개인정보 계열: 트랙 2 진입 전 반드시 채워야 할 GAP — 지금은 실교사 데이터가 없어 위험이 잠재 상태일 뿐이다.

## 주의사항
- "PIN이 있으니 안전하다"고 말하지 말 것 — PIN은 오클릭 방지다. 외부 노출 차단은 RLS·비공개 배포가 담당한다.
- 정책 변경(임계값·목표)은 반드시 설계문서 Change Log + 승인 절차를 남길 것 — 전례: 80%→96%(v1.4), kappa OR 일치율(v1.6).

## 다음 단계
- 역할별 실행 규칙: [11-operations-guide.md](11-operations-guide.md) · GAP 목록 전체: [17-open-questions-and-gaps.md](17-open-questions-and-gaps.md)
