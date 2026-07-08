# PHASE 1 — Foundation (2~3주)

목표: 스캐폴드 + 계약 + DB + Ontology 시드 + Foundry S1~S10 + Pilot 500.
규칙: 티켓 순서대로. AC를 pytest로 먼저 작성 후 구현. 임계값은 config만.

---

## T1.1 프로젝트 스캐폴드
- 산출: `backend/` FastAPI 앱(`/healthz`), pytest·ruff 셋업, `.env.example`, `frontend/` Vite+React+TS 빈 앱
- AC: `uvicorn` 기동 후 `GET /healthz` 200 · `pytest -q` 통과(더미 테스트 1개)

## T1.2 Config 로더
- 산출: `backend/app/core/config.py` — `config/experiments.yaml` 로드, pydantic 타입 검증, 전역 단일 접근점
- AC: 필수 키 전부 존재·타입 검증 테스트 · 없는 키 접근 시 명시적 에러
- 참조: 문서 §10-1, CLAUDE.md 절대 규칙 1

## T1.3 DB + 마이그레이션 001
- 산출: `db/migrations/001_init.sql`을 Alembic 리비전으로 반영, SQLAlchemy 모델(`app/models/`)
- AC: **`dataset_split=BENCHMARK_HOLDOUT` + `origin_channel=FOUNDRY_SYNTHETIC` INSERT가 IntegrityError로 실패하는 테스트** · `label_state=REVIEW_REQUIRED ∧ tier=GOLD` 승격 시도 차단(앱 레벨) 테스트
- 참조: §3-4, 절대 규칙 2

## T1.4 계약 모델 (schemas → pydantic)
- 산출: `app/contracts/` — `schemas/*.json` 7종에서 pydantic 모델, `scripts/validate_schemas.py`
- AC: 문서의 예시 JSON(episode·evidence·infer req/resp·pack)이 스키마 검증 통과 · `is_multi_intent=false ∧ intent_plan≠null` 거부 테스트
- 참조: §3-1·§3-2, runtime §3-0·§3-1

## T1.5 Intent Ontology v1 시드
- 산출: `seeds/ontology_v1.yaml` — 7 domain × intent 60개 이상, intent마다 {정의 1문장, positive 예시 2, negative 예시 2, 인접 혼동 intent}, 로더 + `ontology_versions` 기록
- AC: 중복 intent_id·미정의 domain·예시 누락 검출 테스트 · UNKNOWN intent 포함
- 참조: 설계 문서 §5-9, 원 설계의 Ontology 목록(PLAY~REFLECTION)

## T1.6 LLM 클라이언트 추상화
- 산출: `app/llm/client.py`(complete/embed 인터페이스), mock provider, 호출별 토큰·비용 로깅
- AC: mock으로 전체 테스트가 오프라인 실행 가능 · 재시도·타임아웃 동작 테스트

## T1.7 Foundry S1~S2 — Source Registry + Governance Gate
- 산출: `app/foundry/stages/s1_discovery.py`, `s2_governance.py`, sources CRUD
- AC: governance 미판정(PENDING) 소스는 S3+에서 읽기 불가 · **TRANSFORM_ONLY 소스의 원문 저장 시도 차단** 테스트 · DENY 소스 drop 카운터
- 참조: §1-S1·S2, 절대 규칙 7

## T1.8 Foundry S3~S5 — Extractor / Language Miner / Situation Builder
- 산출: 프롬프트 파일 3종(`app/foundry/prompts/`), situation_frames·atlas_entries·canonical_scenarios 적재
- AC: frame→scenario 변형 수 = `config.foundry.scenario_variants` · scenario의 `visual_semantics`가 vs-1.0 통제 어휘 밖 값이면 거부 · S4 패러프레이즈 유사도 > `paraphrase_max` 시 폐기
- 참조: §1-S3~S5, §2

## T1.9 Foundry S6~S10 — 에이전트 체인
- 산출: Simulator/Analyst/Skeptic/Judge/Consensus 프롬프트 계약 + 실행기, 임베딩 dedup
- AC: label_distribution 합 = 1±0.01 · UNKNOWN 라우팅 동작 · 유사도 ≥ `dedup_similarity` 발화 폐기 테스트 · Skeptic 산출이 confusion_edges(state=hypothesized)로 적재
- 참조: §1-S6~S10, §5-6

## T1.10 Label State Machine + Aggregator 뼈대
- 산출: `app/aggregator/` — 상태 전이(§3-6 그대로), 게이트(min_label_functions·confidence·conflict)
- AC: 허용되지 않는 전이(예: UNLABELED→LABELED 직행) 거부 · 신호 1개로 SILVER 승격 불가 · `adversarial=true` evidence는 집계 제외 테스트
- 참조: §3-3·§3-6, 절대 규칙 6·8

## T1.11 Pilot 500 러너
- 산출: `scripts/run_pilot.py` — S1~S11 E2E, run manifest(source→episode 계보, 토큰·비용), 게이트 리포트(consensus·reject율·kappa 입력 인터페이스)
- AC: 500 에피소드 생성 완료 · manifest에서 임의 에피소드의 원천 소스 역추적 가능 · 게이트 리포트 3지표 출력
- 참조: §1-14

**Phase 1 완료 게이트:** Pilot 리포트가 `consensus_min`·`judge_reject_max`·`pilot_kappa_min` 통과. 미통과 시 Phase 2 진입 금지 — 상류(S5/S6) 품질부터 수정.
