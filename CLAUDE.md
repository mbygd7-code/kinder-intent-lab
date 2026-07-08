# Kinder Intent Lab — Claude Code 프로젝트 지침

## 이 프로젝트가 무엇인가

유아교사의 짧고 애매한 발화 + 화면 컨텍스트 + 직전 행동 + 성향(Persona)으로 **의도를 추론하는 Kinder Intent Brain**을, 킨더버스(실서비스)와 분리된 실험실에서 만든다. 핵심 UX는 데이터 테이블이 아니라 **3D 뇌를 돌려 어두운(약한) 노드를 클릭해 진단하고 훈련시키는 것**이다.

5개 모듈: **Foundry**(데이터 공장, S1~S13) / **Seed Brain**(추론 엔진) / **Gym**(훈련장) / **Observatory**(3D 뇌) / **Arena**(KTIB 벤치마크). 목표: KTIB First Intent Accuracy 80%.

**설계 문서가 진실의 원천이다. 구현이 문서와 충돌하면 문서가 이긴다:**

- `docs/01-foundry/kinder-intent-foundry-growth-system-v1.0.md` (v1.1) — 제1 설계 문서. 모든 티켓이 이 문서의 §를 참조한다
- `docs/06-runtime-integration/` — Runtime Spec v0.2, **PARTIAL HOLD**. Shadow 0a/0b·infer 계약 참조용. **live rollout(Suggest/Assist/Auto) 코드는 작성하지 않는다**

## 기술 스택 (확정)

- Backend: Python 3.11+, FastAPI, SQLAlchemy 2 + Alembic, PostgreSQL 15+ (+pgvector), pytest, ruff
- LLM: `backend/app/llm/client.py`의 추상 인터페이스만 사용. provider는 env(`LLM_PROVIDER`)로 주입 — 특정 벤더 하드코딩 금지. 모든 호출은 토큰·비용 로깅
- Frontend: Vite + React + TypeScript, React Three Fiber(+drei), Zustand
- 계약: `schemas/*.json`(JSON Schema draft-07)이 원천. pydantic 모델·TS 타입은 여기서 파생하고 왕복 테스트로 고정

## 절대 규칙 (Non-negotiables) — 위반 시 어떤 티켓도 완료가 아니다

1. **숫자 임계값은 `config/experiments.yaml`에만 존재한다.** 코드에 리터럴 금지 (문서 §0-3 원칙 7)
2. **DB constraint:** `dataset_split=BENCHMARK_HOLDOUT ⇒ reliability_tier=GOLD ∧ label_state=LABELED ∧ origin_channel ∉ {FOUNDRY_SYNTHETIC, FOUNDRY_AUGMENTED}` — 마이그레이션 001의 CHECK. 우회 코드 금지 (§3-4)
3. **노드 brightness는 Arena 결과만 갱신한다.** 훈련·교정 코드는 brightness에 접근 불가 — size/density/pending_evaluation만 (§6-5, 원칙 8)
4. **brain_nodes 자동 INSERT 금지.** 노드 생성은 governance_events를 남기는 승인 플로우로만 (§5-8, 원칙 9)
5. **훈련 메타데이터(ground truth·scenario_id·target_confusion 등)는 Brain 추론 입력(Core)에 절대 넣지 않는다.** Core+extension 분리는 runtime 문서 §3-0 (mode=gym이어도 동일)
6. **`adversarial=true` evidence는 자연 분포 학습·집계에서 분리** (§8-1 Break the Brain)
7. **TRANSFORM_ONLY 소스의 원문 저장 금지.** 패러프레이즈 유사도 가드 테스트 유지 (§1-S2·S4)
8. **`label_state`(워크플로 상태)와 `reliability_tier`(품질)를 혼용하지 않는다** (§3-6)
9. **provenance 4필드**(origin_channel / episode_creator_type / primary_subject_type / evidence.actor_type) — 생성 주체를 evidence에서 역추론 금지 (§3-2)
10. **evidence_type 고정 서열 금지** — 가중치는 `label_aggregator.evidence_type_weights` config (§3-1)

## 저장소 구조 (구현하며 이 구조를 만든다)

```text
backend/
  app/
    api/          # FastAPI 라우터: infer, gym, observatory, arena
    core/         # config 로더(experiments.yaml 단일 접근점), DB 세션
    models/       # SQLAlchemy (db/migrations와 동기)
    contracts/    # pydantic — schemas/에서 파생
    llm/          # provider 추상화 + mock provider
    foundry/      # stages/(S1~S13), agents/, prompts/(파일로 관리)
    brain/        # retrieval / scorer / priors / version_gate
    gym/          # challenge_pack, session, evidence 수용
    aggregator/   # label state machine + label aggregator
    arena/        # KTIB 러너, 리포트
  tests/
frontend/
  src/
    brain3d/      # R3F: nodes(instanced), edges, encodings(size/brightness/density/pulse/ring)
    panels/       # region/node 패널, WHY-WEAK 진단, pack 브리핑
    api/
schemas/          # 계약 원천 (수정 시 backend/contracts 재생성 + 왕복 테스트)
config/experiments.yaml
db/migrations/
tasks/            # PHASE-1 ~ PHASE-5 백로그 (이 순서대로만 진행)
scripts/          # validate_schemas.py, run_pilot.py 등
docs/             # 설계 문서 — 수정 시 상단 Change Log 항목 필수
```

## 작업 방식 (Claude Code 세션 규칙)

1. `tasks/PHASE-N-*.md`를 **순서대로**. 티켓 하나 = 브랜치/커밋 단위. 티켓 건너뛰기 금지
2. 티켓 시작 전, 티켓에 적힌 문서 §를 먼저 읽는다
3. **AC(Acceptance Criteria)를 pytest 테스트로 먼저 작성**한 뒤 구현한다
4. 완료 조건: 해당 테스트 + 전체 `pytest -q` + `python scripts/validate_schemas.py` 통과
5. 설계와 충돌을 발견하면: 코드를 설계에 맞춘다. 불가능하면 docs Change Log 항목을 **제안만** 하고 사용자 승인 후 진행 (임의 설계 변경 금지)
6. 시각 인코딩 관련 작업은 §7-5 표를 코드 주석으로 복사해 두고 바인딩을 지킨다
7. 전체 시스템의 나침반: **§6-7 End-to-End Trace [0]~[9]** — Phase 4~5의 최종 통합 테스트가 이 체인이다

## 자주 쓰는 명령

```bash
cd backend && pytest -q                      # 테스트
cd backend && alembic upgrade head           # 마이그레이션
python scripts/validate_schemas.py           # 스키마·예시 왕복 검증
cd frontend && npm run dev                   # 3D Brain 개발 서버
```

## 환경 변수

`DATABASE_URL`, `LLM_PROVIDER`, `LLM_API_KEY`, `EMBEDDING_PROVIDER` — `.env.example` 유지, 실키 커밋 금지.
