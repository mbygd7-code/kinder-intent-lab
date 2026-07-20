# 16. 소스 맵 — 개념→코드 색인

> **한눈에 보기** — "이 개념, 코드 어디에 있어?"에 한 줄로 답하는 색인이다. 개념마다 주요 파일·핵심 심볼·config key·DB 테이블·테스트·스크립트·해당 핸드북 문서·구현 상태를 한 행으로 묶었다. 모든 파일 경로는 2026-07-17 저장소 실물을 확인해 기입했다(존재하지 않는 경로 없음).

읽는 법:

- 경로는 저장소 루트 기준. **테스트 열의 파일명만 적힌 항목은 `backend/tests/` 아래**, `frontend/`로 시작하면 프론트 테스트다. 스크립트 열은 전부 `scripts/` 아래.
- config key는 `config/experiments.yaml`의 `섹션.키` 표기 — 숫자 임계값은 코드가 아니라 여기에만 있다(절대 규칙 1) [근거: backend/app/core/config.py 모듈 docstring].
- 상태 태그: IMPLEMENTED(구현·테스트 존재) / PARTIAL(일부만) / DESIGNED(문서·계약만) / PLANNED(예정) / BLOCKED(정책상 보류) / UNKNOWN(미확인).
- 용어 뜻이 낯설면 [03-concepts-and-glossary.md](03-concepts-and-glossary.md) 먼저.

---

## 추론·판단 (런타임)

| 개념 | 주요 파일 | 핵심 심볼·config key | DB 테이블 | 관련 테스트 | 관련 스크립트 | 핸드북 문서 | 상태 |
|---|---|---|---|---|---|---|---|
| inference (4단계 추론) | backend/app/api/infer.py · backend/app/brain/inference.py | `infer_endpoint` · `infer` · `normalize_and_rank` · `brain.retrieval_top_k` | inference_logs · exemplars · brain_nodes | test_infer_api.py · test_inference.py | — | [07](07-inference-and-api.md) | IMPLEMENTED |
| decision (clarify/abstain) | backend/app/brain/decision.py | `decide` · `DecisionOutcome` · `decision.clarify_margin`·`clarify_confidence`·`abstain_score` | — (무상태 순수 함수) | test_decision.py | — | [07](07-inference-and-api.md) | IMPLEMENTED |
| persona (prior·발견·fast update) | backend/app/brain/priors.py · backend/app/foundry/persona.py (보조: backend/app/brain/fast_update.py, backend/app/arena/persona.py) | `capped_prior_factor` · `issue_state_version` · `cluster_trainers` · `run_fast_update_batch` · `brain.persona_prior_cap` · `persona.*` · `fast_update.*` | teacher_priors · population_priors · persona_clusters · persona_state_versions | test_priors.py · test_persona.py · test_fast_update.py · test_arena_persona.py | run_persona_discovery.py · run_fast_update.py | [08](08-training-and-self-improvement.md) | PARTIAL — `brain.persona_warmup` 키를 소비하는 코드 없음 |
| LLM client (재시도·비용 로깅) | backend/app/llm/client.py (provider: backend/app/llm/anthropic_provider.py·openai_embedding_provider.py·mock.py) | `LLMClient` · `get_llm_client` · `LLMCallRecord` · `llm.max_retries`·`timeout_s` | — (구조화 로그) | test_llm.py · test_anthropic_provider.py · test_openai_embedding_provider.py | — | [07](07-inference-and-api.md) | IMPLEMENTED |

## 데이터 생산 (Foundry)

| 개념 | 주요 파일 | 핵심 심볼·config key | DB 테이블 | 관련 테스트 | 관련 스크립트 | 핸드북 문서 | 상태 |
|---|---|---|---|---|---|---|---|
| pilot (500건 게이트 검증) | backend/app/foundry/pilot.py | `run_pilot` · `foundry.consensus_min`·`judge_reject_max`·`pilot_kappa_min` | episodes · evidence · sources · situation_frames | test_pilot.py | run_pilot.py | [06](06-data-lifecycle.md) | IMPLEMENTED |
| campaign (10k~30k 증산) | backend/app/foundry/campaign.py (기반: backend/app/foundry/batch.py) | `run_campaign` · `prepare_campaign_scenarios` · `campaign.domain_weights`·`window_batches` | episodes · evidence · foundry_work_queue | test_campaign.py · test_batch.py | run_campaign.py | [06](06-data-lifecycle.md) | IMPLEMENTED — 실 LLM 가동 중(2026-07-17) |
| confusion edge (Skeptic·교정 생성 → Arena 확정) | backend/app/foundry/stages/s8_skeptic.py · backend/app/gym/live.py · backend/app/arena/runner.py | `record_confusion_edges` · `apply_confusion_edges` · `arena.confusion_confirm_min` | confusion_edges | test_foundry_s6_s10.py · test_gym_live.py · test_arena_runner.py · frontend/src/brain3d/edges.test.ts | — | [08](08-training-and-self-improvement.md) | PARTIAL — GYM_CORRECTION 배선됨(07-17), `CONSENSUS_DISAGREEMENT` 생성·`observed` 전이는 미구현 |
| atlas expansion (커버리지·확장 큐) | backend/app/foundry/atlas.py (제안 등록: backend/app/gym/live.py) | `compute_coverage` · `register_atlas_suggestion` · `atlas.map_min_similarity` | atlas_entries · atlas_expansion_queue | test_atlas.py | — | [05](05-data-catalog.md) | IMPLEMENTED — atlas_entries 0건(데이터 대기) |
| atlas 원료 주입구 (수동 원문→S1+S2+S4 채굴, 07-20 추가) | backend/app/foundry/atlas_ingest.py | `mine_text` · TRANSFORM_ONLY 가드(`foundry.paraphrase_max` — 원문은 S2 raw까지, Atlas엔 패러프레이즈만) | sources · source_documents · atlas_entries | test_atlas_pipeline.py | mine_atlas.py(`file --title --source-class --commit`) | [05](05-data-catalog.md) | IMPLEMENTED — 원료 투입 0회 |
| 화면 씨드 + LLM 확장 (S5 변형 원천, 07-20 추가) | backend/app/foundry/situation_seeds.py · backend/app/foundry/seed_expansion.py · backend/app/api/situation_seeds.py (UI: frontend/src/panels/SituationSeedPanel.tsx) | `load_situation_seeds`류 로더 · `vocabulary_violations` · `expansion_unmet` · `foundry.seed_expansion_enabled` · env `SITUATION_SEED_PIN`(→ARENA_PIN→2341) | — (파일: seeds/situation_seeds_v1.yaml — 어휘+씨드 16) | test_situation_seeds.py · test_seed_expansion.py · test_situation_seed_api.py · frontend/src/panels/SituationSeedPanel.test.tsx | — | [05](05-data-catalog.md) 5-7 · [11](11-operations-guide.md) E-7 | IMPLEMENTED |

## 검수·품질 (사람 게이트)

| 개념 | 주요 파일 | 핵심 심볼·config key | DB 테이블 | 관련 테스트 | 관련 스크립트 | 핸드북 문서 | 상태 |
|---|---|---|---|---|---|---|---|
| evidence 수집 (즉석 문답) | backend/app/gym/live.py · backend/app/api/gym.py (UI: frontend/src/panels/LiveQuizPanel.tsx) | `record_training_feedback` · `queue_benchmark_candidate` · `POST /v1/gym/live/feedback` · `gym.evidence_strength` | episodes · evidence | test_gym_live.py · test_gym_api.py · frontend/src/api/live.test.ts | — | [08](08-training-and-self-improvement.md) | IMPLEMENTED |
| human review (GOLD 유일문) | backend/app/aggregator/review.py | `apply_review_batch` · `batch_kappa` · `canonical_reviewer` · `review.min_reviewers`·`min_agreement_kappa` | episodes · governance_events | test_human_review.py | run_human_review.py · run_benchmark_review.py | [06](06-data-lifecycle.md) | IMPLEMENTED |
| 웹 공부검수 (review_votes) | backend/app/api/review.py · backend/app/models/episodes.py (UI: frontend/src/panels/GoldReviewPanel.tsx) | `/v1/review/queue`·`/vote`·`/apply`·`/status` · `ReviewVoteRow` — 승격은 `apply_review_batch` 재사용 | review_votes · episodes | test_review_api.py · frontend/src/panels/GoldReviewPanel.test.tsx | — | [11](11-operations-guide.md) | IMPLEMENTED |
| expert ingest (KTIB 유일한 입구) | backend/app/foundry/expert_ingest.py | `ingest_expert_episodes` · `NON_SYNTHETIC_CHANNELS` · `review.min_expert_agreement` | episodes · governance_events | test_expert_ingest.py · test_benchmark_isolation.py | ingest_expert_episodes.py | [06](06-data-lifecycle.md) | IMPLEMENTED |
| ktib upload 이력 (원문 보관·목록·열람) | backend/app/api/observatory.py · backend/app/models/arena.py (UI: frontend/src/panels/ExamUpload.tsx) | `POST /v1/observatory/ktib/upload` · `GET /ktib/uploads`·`/{upload_id}` · `KtibUpload` | ktib_uploads | test_observatory_api.py | — | [11](11-operations-guide.md) | IMPLEMENTED |
| 시험 문항 웹 검수 (1~5 평점 스테이징) | backend/app/api/observatory.py · backend/app/models/benchmark_candidates.py (UI: frontend/src/panels/KtibReviewModal.tsx) | `/v1/observatory/ktib/candidates`(작성→blind 2차 검수→register) · `review.min_item_rating` | benchmark_candidate_batches · benchmark_candidate_items | test_benchmark_candidates.py | — | [11](11-operations-guide.md) | IMPLEMENTED |

## 시험·평가 (Arena)

| 개념 | 주요 파일 | 핵심 심볼·config key | DB 테이블 | 관련 테스트 | 관련 스크립트 | 핸드북 문서 | 상태 |
|---|---|---|---|---|---|---|---|
| KTIB build/freeze (시험지 동결 발급) | backend/app/arena/ktib.py | `build_ktib` · `freeze_items` · `eligible_episodes` · `visual_semantics.ktib_extractor_pinned` | ktib_versions · ktib_items | test_ktib.py · test_benchmark_isolation.py | run_ktib_build.py · ktib_coverage.py | [09](09-evaluation-and-performance.md) | IMPLEMENTED — 최신 ktib-3(386문항, 의도 커버 8/70) |
| Arena run (채점) | backend/app/arena/runner.py · backend/app/api/arena_ops.py | `run_arena` · `build_outcome` · `POST /v1/observatory/arena/run`(PIN) · `arena.confusion_confirm_min` | arena_runs · confusion_edges · inference_logs | test_arena_runner.py · test_arena_metrics.py · test_arena_ops_api.py | run_arena.py | [09](09-evaluation-and-performance.md) | IMPLEMENTED |
| zero-shot baseline (범용 LLM 기준선) | backend/app/arena/baseline.py | `run_zero_shot_baseline` · `baseline_report` · `RUN_TYPE_BASELINE` · `arena.first_intent_accuracy_target` | arena_runs | test_arena_baseline.py | run_zero_shot_baseline.py | [09](09-evaluation-and-performance.md) | IMPLEMENTED — 88.1% 실측(claude-sonnet-5, ktib-2) |
| version gate (candidate 빌드) | backend/app/brain/version_gate.py | `build_candidate` · `new_gold_since_base` · `current_brain_version` · `version_gate.min_new_gold` | brain_versions | test_version_gate.py | run_version_gate.py | [08](08-training-and-self-improvement.md) | IMPLEMENTED — 미발동(TRAIN GOLD 0) |
| brightness 반영 (reflect + promote/reject) | backend/app/arena/reflect.py · backend/app/brain/promote.py · backend/app/models/guards.py | `reflect_arena_run` · `resolve_candidate` · `arena_brightness_write` · `version_gate.promote_rule` | brain_nodes(heldout_accuracy·calibration_ece·last_arena_run) | test_arena_reflect.py · test_promote.py | — | [09](09-evaluation-and-performance.md) | IMPLEMENTED |
| live-rollout 준비 게이트 (읽기 전용 4레그) | backend/app/arena/gate.py | `LiveReadiness` · `gate.cwar_max`·`cwar_miss_max`·`critical_commit_coverage_min`·`recovery_min` | arena_runs(저장된 metrics만 읽음) | test_arena_gate.py | — | [09](09-evaluation-and-performance.md) | IMPLEMENTED — 서빙은 켜지 않음(HOLD) |
| backfill (exemplar 선정·노드 부트스트랩) | backend/app/brain/backfill.py | `run_backfill` · `select_exemplars` · `bootstrap_nodes` · `brain.exemplar_min_dist` | exemplars · brain_nodes · governance_events | test_brain_backfill.py | run_backfill.py | [08](08-training-and-self-improvement.md) | IMPLEMENTED — exemplar 0건(GOLD 재료 대기) |
| ambiguity report (애매 발화 인사이트) | backend/app/api/observatory.py (UI: frontend/src/dashboard/AmbiguityCard.tsx) | `GET /v1/observatory/ambiguity-report` — `decision.clarify_margin`·`clarify_confidence` 에코 | inference_logs · evidence · atlas_expansion_queue | test_ambiguity_report.py · frontend/src/dashboard/AmbiguityCard.test.tsx | — | [02](02-two-track-strategy.md) | IMPLEMENTED |

## 관측·운영·인프라

| 개념 | 주요 파일 | 핵심 심볼·config key | DB 테이블 | 관련 테스트 | 관련 스크립트 | 핸드북 문서 | 상태 |
|---|---|---|---|---|---|---|---|
| observatory 3D/dashboard | backend/app/api/observatory.py · backend/app/api/dashboard.py · backend/app/observatory/aggregate.py (UI: frontend/src/brain3d/ · frontend/src/dashboard/) | `GET /v1/observatory/brain` · `GET /v1/observatory/dashboard` · `encodings.ts`(§7-5 바인딩) · `dashboard.run_timeline_window` | brain_nodes · confusion_edges · arena_runs · episodes | test_observatory_api.py · test_dashboard_api.py · frontend/src/brain3d/encodings.test.ts · frontend/src/dashboard/dashboard.test.tsx | ktib_coverage.py · train_coverage.py(동일 집계 thin CLI) | [11](11-operations-guide.md) | IMPLEMENTED |
| ontology admin (intent_display 표시계층·변경 제안) | backend/app/api/ontology_admin.py · backend/app/models/intent_admin.py (UI: frontend/src/panels/IntentCatalogPanel.tsx) | `GET/PUT /v1/ontology/intents*` · `POST /v1/ontology/change-requests` · `IntentDisplay` · `IntentChangeRequest` · env `ONTOLOGY_PIN`(기본 2341) | intent_display · intent_change_requests · governance_events | test_ontology_admin.py · frontend/src/panels/intentRecommend.test.ts | apply_ontology_examples.py(의미 계층 편집 문) | [04](04-ontology-and-intents.md) · [11](11-operations-guide.md) | IMPLEMENTED |
| risk model (rm-1.0 위험 등급) | backend/app/core/risk_model.py · seeds/risk_model_v1.yaml | `get_risk_model` · `tier_of` · `arena.critical_intents`(시드와 정합 강제) | governance_events(RISK_MODEL_UPDATE) | test_risk_model.py | apply_risk_model.py | [10](10-safety-and-governance.md) | IMPLEMENTED |
| config 로더 (임계값 단일 원천) | backend/app/core/config.py · config/experiments.yaml | `get_config` · `ExperimentsConfig`(strict·frozen·extra=forbid) | — | test_config.py | — | [10](10-safety-and-governance.md) | IMPLEMENTED |
| 스키마 검증 (계약 왕복 + 정합) | scripts/validate_schemas.py · schemas/*.json · backend/app/contracts/ | `check_risk_model_coherence` — draft-07 검증 + examples 왕복 + critical_intents 정합 | — | test_contracts.py | validate_schemas.py | [10](10-safety-and-governance.md) | IMPLEMENTED |
| Supabase 동기화 (2대 운영 append-only) | scripts/sync_to_supabase.py | `NODE_SYNC_COLS`(pending_evaluation·evidence_stats·exemplar_stats만 UPDATE) · `BRIGHTNESS_COLS` 제외(절대 규칙 3) | 전 public 테이블(PK 신규 행 추가만) | 전용 테스트 없음 | sync_to_supabase.py(pre-push 훅 호출) | [11](11-operations-guide.md) | IMPLEMENTED — 역방향(sync_from_supabase)은 저장소 미포함 |

---

## 현재 상태
- 표의 파일 경로·심볼·config key는 전부 2026-07-17 저장소에서 실존 확인했다(팩트팩 구조 목록 + 코드 직접 열람). 상태가 PARTIAL인 행은 부족한 부분을 상태 칸에 그대로 적었다.
- live rollout(Suggest/Assist/Auto) 서빙 코드는 이 표에 **없다** — 정책상 작성 금지(BLOCKED, PARTIAL HOLD)라서다 [근거: CLAUDE.md], [근거: backend/app/api/infer.py — mode≠gym이면 501].

## 주의사항
- `backend/app/api/observatory.py`는 한 파일에 여러 개념(3D·시험지 업로드·문항 스테이징·애매 리포트)이 산다 — 행마다 엔드포인트 경로로 구분해 두었다.
- 테스트 열은 대표 테스트만 적었다 — 전체 회귀는 `cd backend && pytest -q` + `python scripts/validate_schemas.py`가 완료 기준이다 [근거: CLAUDE.md 작업 방식 4].

## 다음 단계
- 각 행의 개념 설명이 필요하면 [03-concepts-and-glossary.md](03-concepts-and-glossary.md).
- 행들이 어떤 순서로 연결돼 데이터가 흐르는지는 [06-data-lifecycle.md](06-data-lifecycle.md), API 계약 상세는 [07-inference-and-api.md](07-inference-and-api.md).
- 이 표와 실제 코드가 어긋나는 지점(정직한 갭 목록)은 [17-open-questions-and-gaps.md](17-open-questions-and-gaps.md).
