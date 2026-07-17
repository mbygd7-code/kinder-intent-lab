# 05. 데이터 카탈로그 — 킨더브레인이 만지는 모든 데이터의 전수 지도

> **한눈에 보기**
>
> - 데이터 유입 문은 셋이다: **Foundry 합성**(FOUNDRY_SYNTHETIC 2,310건), **사람 훈련**(GYM_HUMAN 33건), **전문가 저작**(EXPERT_AUTHORED 386건 — 전부 시험지). 나머지는 전부 이 셋의 **파생물**(라벨 신호·뇌·시험지 스냅샷·감사 기록)이다. [근거: 팩트팩 DB 스냅샷, 2026-07-17 13:16 수집]
> - 벤치마크 오염은 규칙이 아니라 **DB CHECK가 물리적으로 막는다**: `BENCHMARK_HOLDOUT ⇒ GOLD ∧ LABELED ∧ 비합성`(§5-3 원문 인용). `IMPLEMENTED` [근거: backend/app/models/episodes.py::Episode(benchmark_integrity)]
> - **GOLD를 만드는 경로는 인간 검수 2인 일치 단 하나**다(aggregator는 SILVER까지만). 현재 GOLD 386건은 전부 시험지(BENCHMARK) — **TRAIN GOLD 0건**이고, 그래서 exemplars 0건, seed-v0 채점 0.0%(전부 abstain)가 나온 것이다. `PARTIAL` [근거: backend/app/aggregator/review.py 모듈 docstring, 팩트팩 세션노트]
> - 생성 주체는 절대 역추론하지 않는다 — **provenance 4필드**(origin_channel / episode_creator_type / primary_subject_type / evidence.actor_type)에 태어날 때 명시 기록된다(§5-2). [근거: CLAUDE.md 절대 규칙 9]
> - 이 장의 모든 건수는 **2026-07-17 13:16 읽기 전용 스냅샷**(핸드북 팩트팩)이다. 증산 캠페인 가동 중이라 실시간 수치는 더 클 수 있다. 의도 정의는 [04-ontology-and-intents.md](04-ontology-and-intents.md), 용어는 [03-concepts-and-glossary.md](03-concepts-and-glossary.md).

---

## 5-1. 큰 그림 — 세 유입 계보와 파생물

```text
[Foundry 합성]  sources → source_documents → situation_frames → canonical_scenarios
                  └→ episodes(FOUNDRY_SYNTHETIC) + evidence(SYNTHETIC_CONSENSUS·DOMAIN_RULE)
[사람 훈련]     Gym 세션/즉석 문답 → episodes(GYM_HUMAN) + evidence(HUMAN_CONFIRMATION·HUMAN_CORRECTION)
[전문가 저작]   시험지 CSV/YAML → (스테이징: benchmark_candidate_*) → ingest_expert_episodes
                  └→ episodes(EXPERT_AUTHORED, BENCHMARK_HOLDOUT·GOLD·LABELED)

파생: exemplars(GOLD에서만) · brain_nodes(승인 플로우로만) · confusion_edges ·
     ktib_versions/items(동결 스냅샷) · arena_runs(채점) · brain_versions(승격 판정) ·
     inference_logs(추론 로그) · governance_events(감사 흔적)
```

훈련(TRAIN)과 시험(BENCHMARK)은 **같은 테이블(episodes)의 다른 split**이며, 경계는 CHECK 제약과 dedup 가드가 지킨다(§5-3, §5-5-C).

## 5-2. provenance 4필드 — 무엇이고 왜 필요한가

"이 데이터를 누가 만들었나"를 **신호 패턴에서 추측(역추론)하는 것을 금지**하고, 태어나는 순간 4개 필드에 명시 기록한다(CLAUDE.md 절대 규칙 9). 값 목록은 전부 DB CHECK로 고정돼 있다. [근거: backend/app/models/episodes.py::Episode/Evidence CheckConstraint]

| 필드 | 어디에 | 물음 | 가능한 값(CHECK 고정) |
|---|---|---|---|
| origin_channel | episodes | 어느 유입 문으로 태어났나 | FOUNDRY_SYNTHETIC · FOUNDRY_AUGMENTED · GYM_HUMAN · EXPERT_AUTHORED · PRODUCTION_SHADOW · OFFICIAL_CORPUS · COMMUNITY_DERIVED |
| episode_creator_type | episodes | 레코드를 만든 주체는 | FOUNDRY_PIPELINE · GYM_SESSION · SHADOW_CONVERTER · HUMAN_ANNOTATOR |
| primary_subject_type | episodes | 발화의 주인이 실제 교사인가 | TEACHER · SIMULATED_TEACHER |
| actor_type | evidence | 이 라벨 신호를 누가 만들었나 | LLM_ANALYST · DOMAIN_EXPERT · TEACHER_TRAINER · STAFF_TRAINER · BEHAVIOR_SIGNAL · RULE_ENGINE |

왜 4개나 필요한가: 축이 서로 독립이기 때문이다. 예컨대 전문가가 저작한 발화(EXPERT_AUTHORED)도 레코드는 HUMAN_ANNOTATOR가 만들고 주어는 TEACHER다. 합성 에피소드(FOUNDRY_SYNTHETIC)는 SIMULATED_TEACHER가 주어이며, 거기 붙은 신호는 LLM_ANALYST(합의)일 수도 RULE_ENGINE(규칙)일 수도 있다. 만약 "evidence가 SYNTHETIC_CONSENSUS니까 에피소드도 합성이겠지"처럼 역추론을 허용하면, 사람 데이터에 합성 신호가 붙는 순간(실제로 GYM_HUMAN 에피소드에 DOMAIN_RULE 신호가 붙는다) 분류가 무너지고, 벤치마크 격리(§5-3)가 걸린 origin_channel 판정까지 오염된다.

## 5-3. 벤치마크 무결성 CHECK — 원문

episodes 테이블에 걸린 `benchmark_integrity` CHECK(마이그레이션 0001, 모델과 동기) 원문: [근거: backend/app/models/episodes.py::Episode.__table_args__]

```python
# 절대 규칙 2: 벤치마크에 합성 데이터·미검증 라벨 진입 금지 (§3-4)
CheckConstraint(
    "dataset_split <> 'BENCHMARK_HOLDOUT' "
    "OR (reliability_tier = 'GOLD' AND label_state = 'LABELED' "
    "AND origin_channel NOT IN ('FOUNDRY_SYNTHETIC','FOUNDRY_AUGMENTED'))",
    name="benchmark_integrity",
),
```

백스톱이 하나 더 있다(마이그레이션 0002): GOLD면 반드시 확정 라벨이어야 한다.

```python
CheckConstraint(
    "reliability_tier <> 'GOLD' OR label_state = 'LABELED'",
    name="gold_requires_labeled",
),
```

이 둘 덕분에 "합성 뱅크에서 승격시켜 시험지를 만든다"는 경로가 코드 실수로도 **물리적으로 존재하지 않는다**. 우회 코드를 쓰는 것 자체가 절대 규칙 2 위반이다.

## 5-4. 등급(tier)과 상태(label_state) 사전

두 축을 혼용하지 않는다(절대 규칙 8): **label_state는 워크플로 어디까지 왔나**, **reliability_tier는 얼마나 믿을 만한가**다.

| 축 | 가능한 값(CHECK 고정) | 의미 |
|---|---|---|
| label_state | UNLABELED → EVIDENCE_ACCUMULATING → AGGREGATION_READY → LABEL_CANDIDATE → REVIEW_REQUIRED → LABELED / REJECTED | 신호 축적→집계→후보→검수→확정(또는 폐기)의 상태 기계(§3-6). 전이는 `advance_label_state`로만 |
| reliability_tier | UNVERIFIED → BRONZE → SILVER → GOLD | 품질 신뢰 등급. **aggregator(`recommend_tier`)는 SILVER까지만 올린다** — GOLD는 검수의 문(아래) 단 하나 |

**GOLD 승격 조건(§3-3)** — "인간 검수, 정규화된 서로 다른 2인 이상, 같은 intent 일치, 일치도 기록": 배치 kappa ≥ `review.min_agreement_kappa`(0.65, 독립 라벨링) **또는** 관측 일치율 ≥ `review.min_expert_agreement`(0.80, O/X 승인 검수 — kappa가 base-rate 역설로 퇴화하는 경우의 대체 척도, §3-3 v1.6). 경로는 `scripts/run_human_review.py`(배치)와 `/v1/review`(웹 검수, `aggregator.review.apply_review_batch` GOLD 유일문 재사용), 그리고 전문가 시험지 유입(`ingest_expert_episodes` — 같은 §3-3 기준을 그대로 요구) 셋뿐이며 셋 다 같은 검증 규칙을 쓴다. [근거: backend/app/aggregator/review.py, backend/app/foundry/expert_ingest.py::_assert_benchmark_reviewed, config/experiments.yaml::review]

## 5-5. 카탈로그

각 절은 표 2개로 나눈다: **표①** 정체·생성 경로·관련 도구, **표②** provenance·등급·용도·위험.

### A. 발화·에피소드 계열

표 A-①

| 항목(테이블) | 쉬운 의미 | 생성 주체·경로 | 관련 API·script |
|---|---|---|---|
| raw utterance(발화 원문) | 교사가 실제로 입력/저작한 문장. 독립 테이블이 아니라 여러 표의 컬럼으로 존재: `episodes.teacher_prompt`(원본), `ktib_items.teacher_prompt`(동결 사본), `benchmark_candidate_items.teacher_prompt`(스테이징), `atlas_expansion_queue.utterance`(미매핑 큐) | 사람 입력(Gym·검수·전문가 저작) 또는 Foundry S6 생성 | `/v1/intent/infer`(요청 처리에만 사용), `/v1/gym/*` |
| episodes | 발화 1건 = 에피소드 1행. 라벨 상태·등급·분할(split)·provenance를 모두 이 행이 짊어진다 | 합성: Foundry 배치(S6~S10, run_pilot/run_campaign) · 사람: Gym 즉석 문답/세션 · 전문가: `ingest_expert_episodes` | `scripts/run_pilot.py`, `scripts/run_campaign.py`, `scripts/ingest_expert_episodes.py`, `scripts/run_human_review.py`, `/v1/review/apply`, `scripts/cleanup_mock_bank.py` |
| inference_logs | 추론 1회 = 1행 전건 로그. 4단계(retrieval/scorer/prior/normalize) 기여를 stages(JSONB)에 분리 기록, mode(arena/gym)는 관측 라벨 | `infer_core`가 매 추론마다 자동 기록 — `/v1/intent/infer`와 Arena 러너가 **같은 파이프라인**을 쓴다 | `/v1/intent/infer`, `scripts/run_arena.py`, `/v1/observatory/ambiguity-report`(애매 발화 리포트가 소비) |

표 A-②

| 항목 | provenance 관련값 | label_state·tier 가능값 | TRAIN 사용 | BENCHMARK 사용 | GOLD 승격 조건 | 오염·개인정보 위험 |
|---|---|---|---|---|---|---|
| raw utterance | 소속 행(episodes 등)의 4필드를 따른다 | 소속 행을 따른다 | episodes(TRAIN)를 통해 | ktib_items 동결 사본으로 | — | **개인정보 최상위 위험 지점**: 원문이 그대로 저장되므로 실아동 이름·식별 정보가 입력되면 남는다. inference_logs에는 발화 원문 컬럼이 없다(stages는 intent별 점수·rationale만 — 단 rationale 자유 텍스트에 발화 일부가 인용될 수 있음) [근거: backend/app/brain/inference.py::infer_core stages 구성] |
| episodes | origin_channel·episode_creator_type·primary_subject_type 전부 필수(NOT NULL) | state 7종 · tier 4종 (§5-4) | TRAIN split이 훈련·집계 대상(REJECTED 제외). exemplar 선정은 그중 GOLD만 | BENCHMARK_HOLDOUT split만, CHECK 통과분만 | §3-3 2인 검수 (§5-4) | 발화 원문+`prompt_embedding` 저장. 오염 가드: `dedup_hash`는 발화+intent만(split 미포함 — 같은 발화가 TRAIN·BENCHMARK 양쪽에 못 산다), 전문가 유입 시 TRAIN 원문 대조 거부 [근거: backend/app/foundry/expert_ingest.py::_dedup_hash/_assert_no_train_contamination] |
| inference_logs | — (mode·persona_state_version만) | — | 자연 분포 학습에 미사용(관측 로그) | 미사용 | — | 원문 없음. top_intent·confidence·margin 등 행동 통계만. 애매 발화 리포트의 원료 |

### B. 라벨 신호 계열

표 B-①

| 항목(테이블) | 쉬운 의미 | 생성 주체·경로 | 관련 API·script |
|---|---|---|---|
| evidence | "에피소드 X는 intent Y다/아니다"라는 신호 1건. polarity(supports/refutes)·strength(0~1)·adversarial 플래그 | 6종 유형별로 다르다(아래 표②) — 합성 합의(S10), 규칙 엔진, Gym 사람 판정, 행동 신호, 전문가 검토 | `/v1/gym/live/feedback`, `/v1/gym/session/{id}/submit`, Foundry 배치 러너 |
| adversarial evidence | evidence 중 `adversarial=true` — Break the Brain(함정 문제) 세션에서 나온 신호. 자연 분포 학습·집계에서 **분리**된다(절대 규칙 6) | Gym 함정 모드(§8-1) | 현재 생성 경로 미가동 — **0건** `DESIGNED` |
| review_votes | 공부(TRAIN) 데이터 웹 검수의 개별 투표. blind, 검수자 신원 정규화(`reviewer_canonical` — 별칭 두 개로 2인 위장 불가), `chosen_intent` NULL = 폐기 표 | 웹 검수 화면에서 사람이 투표 | `/v1/review/queue`, `/v1/review/vote`, `/v1/review/apply`(적용 시 GOLD 유일문 `apply_review_batch` 경유), `/v1/review/status` |

표 B-② — evidence 6종의 실측과 의미

| evidence_type | 쉬운 의미 | 전형적 actor_type | 건수(스냅샷) | TRAIN 사용 | BENCHMARK 사용 |
|---|---|---|---:|---|---|
| SYNTHETIC_CONSENSUS | Foundry S10 다중 에이전트 합의 | LLM_ANALYST | 2,310 | 집계 입력 | 진입 불가(신호는 KTIB에 안 들어감) |
| DOMAIN_RULE | 도메인 규칙 엔진 판정 | RULE_ENGINE | 1,156 | 집계 입력 | 〃 |
| HUMAN_CONFIRMATION | 사람이 "맞다" 확인(Gym) | TEACHER_TRAINER·STAFF_TRAINER | 50 | 집계 입력(강한 신호, gym.evidence_strength 0.9) | 〃 |
| HUMAN_CORRECTION | 사람이 "아니다, 이거다" 교정(Gym) | TEACHER_TRAINER·STAFF_TRAINER | 13 | 집계 입력 + confusion edge(GYM_CORRECTION) 원료 | 〃 |
| WEAK_BEHAVIORAL | 채택·무시 같은 약한 행동 신호 | BEHAVIOR_SIGNAL | 0 | (설계) 집계 입력 | 〃 |
| EXPERT_REVIEW | 도메인 전문가 검토 | DOMAIN_EXPERT | 0 | (설계) 집계 입력 | 〃 |

- 유형 간 **가중치 고정 서열 금지**(절대 규칙 10) — 가중치는 `config/experiments.yaml::label_aggregator.evidence_type_weights`(현재 `empirical`, 실측 신뢰도로 갱신)가 원천이다.
- adversarial 분리: 현재 3,529건 전부 `adversarial=false` — 분리 가드는 구현돼 있으나 실데이터 0. [근거: 팩트팩 DB 스냅샷, backend/app/models/episodes.py::Evidence.adversarial]
- GOLD 승격 조건 열이 없는 이유: evidence·votes는 승격의 **재료**이지 승격 대상이 아니다. review_votes가 모여 §5-4의 GOLD 문을 통과시킨다.
- 개인정보: evidence 자체는 발화 원문을 들고 있지 않다(episode_id 참조). review_votes는 검수자 신원(입력 원문 `reviewer_ref`)을 보관한다.

### C. 시험지(KTIB) 계열 — 학습이 만질 수 없는 격리 구역

표 C-①

| 항목(테이블) | 쉬운 의미 | 생성 주체·경로 | 관련 API·script |
|---|---|---|---|
| benchmark_candidate_batches / items | 시험 문항 후보의 **스테이징**(episodes 밖 — 반쯤 만든 후보가 벤치마크를 오염시키지 않게). 교사 A가 문항+1~5 평점 제출 → 교사 B가 blind 2차 평점. 배치 상태: AWAITING_SECOND→SECOND_DONE→REGISTERED | 사람(교사 2인) | `POST/GET /v1/observatory/ktib/candidates`, `POST .../candidates/{batch_id}/review`, `POST .../candidates/{batch_id}/register` |
| ktib_versions / ktib_items | 발급된 시험지 버전과 **동결 문항 스냅샷**(채택 시점의 발화·gold intent·workspace 고정 — 원본 에피소드가 나중에 바뀌어도 시험지는 불변). content_hash 유일, extractor 바뀌면 새 버전 강제 | `run_ktib_build`가 자격 있는 에피소드(BENCHMARK_HOLDOUT ∧ GOLD ∧ LABELED)에서 발급 | `scripts/run_ktib_build.py`, `scripts/ktib_coverage.py`, `scripts/run_arena.py` |
| ktib_uploads | 시험지 업로드 **이력**: 등록마다 1행 + 올린 원문(CSV/YAML) 보관 — 목록·열람·회수용 감사 표. 채점 축과 무관(지워도 시험지 불변) | 업로드 등록 시 자동 | `POST /v1/observatory/ktib/upload`, `GET /v1/observatory/ktib/uploads`, `GET .../uploads/{upload_id}` |

표 C-②

| 항목 | provenance 관련값 | label_state·tier | TRAIN 사용 | BENCHMARK 사용 | GOLD 승격 조건 | 오염·개인정보 위험 |
|---|---|---|---|---|---|---|
| benchmark_candidate_* | 스테이징엔 provenance·tier·GOLD **어떤 것도 없다** — 등록 시 부여 | rating_a/rating_b(1~5)만 | 불가 | 등록 전 대기만 | 등록 조건: 서로 다른 2인 ∧ 두 평점 모두 ≥ `review.min_item_rating`(4) ∧ 배치 일치도 통과 → **등록은 오직 ingest_expert_episodes 경유** | 문항 원문 보관. LLM이 쓴 발화를 여기로 넣으면 안 된다(아래 공통 경고) |
| ktib_versions/items | 원본 에피소드가 비합성임을 CHECK가 보장 | gold_intent는 동결 사본(라벨 아님) | **접근 금지**(격리) — 학습 파이프라인이 읽지 않는다 | 시험지 그 자체. ktib-1(1)→ktib-2(185)→ktib-3(386), items 총 572 | — | 재추출 금지(`visual_semantics.ktib_extractor_pinned: true`) — extractor가 바뀌면 content_hash가 바뀌어 새 버전 강제, 신·구 점수를 같은 축에 그리지 않는다 [근거: backend/app/models/arena.py 모듈 docstring] |
| ktib_uploads | authored_by·approved_by·reviewers 기록 | agreement_rate·agreement_kappa 병기(§3-3 v1.6) | 불가 | 이력만(채점 무관) | — | `source_document`에 **원문 그대로 보관 — 전문가 저작이라 허용**(TRANSFORM_ONLY 금지 대상인 §1-S2와 다른 축) [근거: backend/app/models/arena.py::KtibUpload 주석] |

공통 경고(구조적 한계): **LLM이 생성한 발화를 사람이 `EXPERT_AUTHORED`로 찍어 넣으면 코드는 탐지할 수 없다.** 그 순간 KTIB는 합성 분포가 되고 Arena 점수는 암기의 측정치가 된다 — 그래서 `authored_by`가 필수이고 거버넌스 이벤트에 남는다. [근거: backend/app/foundry/expert_ingest.py 모듈 docstring]

### D. 뇌(Brain) 계열 — 전부 파생물

표 D-①

| 항목(테이블) | 쉬운 의미 | 생성 주체·경로 | 관련 API·script |
|---|---|---|---|
| brain_nodes | 3D 뇌의 노드 1개 = intent 1개(70행). 밝기 계열(heldout_accuracy·calibration_ece·last_arena_run)과 크기·밀도 통계 보유 | **자동 INSERT 금지(절대 규칙 4)** — `created_by_event` 필수, 승인 플로우(S13 backfill·bootstrap)로만 생성 | `scripts/run_backfill.py`, `GET /v1/observatory/brain`, `GET /v1/observatory/node/{intent_id}/diagnosis` |
| exemplars | 노드별 대표 발화 임베딩(추론 retrieval의 재료). **GOLD 확정 라벨에서만 선정**, 중복 채택 방지, 최소 거리 `brain.exemplar_min_dist`(0.15) | S13 backfill / fast update | `scripts/run_backfill.py`, `scripts/run_fast_update.py` |
| embedding(임베딩 컬럼) | 문장의 수치 표현. 세 곳: `episodes.prompt_embedding` · `exemplars.embedding` · `atlas_entries.embedding` — 전부 Vector(1536), exemplars는 hnsw 인덱스 | EMBEDDING_PROVIDER(env)로 주입 — 기본 mock, 실운영 예: text-embedding-3-small(1536) | `.env.example`, `backend/app/llm/openai_embedding_provider.py` |
| confusion_edges | "정답 A가 B로 오인된다"는 방향성 edge. state: hypothesized→observed→confirmed, origin: SKEPTIC·CONSENSUS_DISAGREEMENT·GYM_CORRECTION·ARENA_MATRIX | SKEPTIC(S8) 가설 / Gym 교정 / Arena 오답 관측(`confusion_confirm_min` 3회↑ confirmed) | `GET /v1/observatory/confusion-edges`, `GET /v1/observatory/node/{intent_id}/confusions` |
| brain_versions | 뇌 버전 승격 판정 기록. decision: candidate/promote/reject | Version Gate(§6-6) — new_gold ≥ `version_gate.min_new_gold`(200) 충족 시 | `scripts/run_version_gate.py`, `GET /v1/observatory/version-gate` |
| arena_runs | 채점 1회 = 1행. replay 무결성 4종(model/ontology/persona_state/extractor_versions) + ktib_version 고정. run_type: brain / zero_shot_baseline | Arena 러너(주간 schedule) 또는 웹 채점 버튼(PIN) | `scripts/run_arena.py`, `scripts/run_zero_shot_baseline.py`, `POST /v1/observatory/arena/run`, `GET /v1/observatory/arena/status` |

표 D-②

| 항목 | TRAIN 사용 | BENCHMARK 사용 | 갱신 권한·무결성 | 오염·개인정보 위험 |
|---|---|---|---|---|
| brain_nodes | size/density/pending_evaluation은 훈련·집계가 갱신 | — | **brightness 계열은 Arena 러너만 갱신(절대 규칙 3)** — 훈련·교정 코드는 접근 불가. run_type=brain만 밝기 원천(baseline은 3D에 새지 않음) | 발화 없음. 위험은 "훈련이 밝기를 만지는 코드"가 생기는 것 — 그 순간 뇌가 자기 채점을 하게 된다 |
| exemplars | 추론 retrieval 재료(TRAIN GOLD에서만). **현재 0건 — TRAIN GOLD 0의 직접 결과**이며 seed-v0 0.0%(전부 abstain)의 원인 | 불가 | GOLD 아닌 라벨에서 선정 금지 | 발화 임베딩 보관(원문은 episode 참조) |
| confusion_edges | Gym C형(혼동쌍) 훈련의 타깃 선정에 사용 | Arena 혼동 행렬이 관측 원천 | 629건 전부 hypothesized·SKEPTIC(관측 0) `PARTIAL` | — |
| brain_versions | — | promote 판정에 Arena 결과 사용 | **0행** — min_new_gold 200 미충족으로 미발동 `PARTIAL` | — |
| arena_runs | 불가(채점 기록) | 채점 그 자체. 실측 4행: zero_shot 0.8811(ktib-2, 07-14) · brain seed-v0 0.0 ×2(ktib-2, 07-14) · brain seed-v0 0.0(ktib-3, 07-16) | created_at은 clock_timestamp()(같은 트랜잭션 다중 run 정렬 결정성) | — |

### E. Foundry 계보 계열 — 합성 에피소드의 족보

표 E-①

| 항목(테이블) | 쉬운 의미 | 생성 주체·경로 | 관련 API·script |
|---|---|---|---|
| sources | 수집 후보 소스 등록부. source_class: AUTHORITY/PRACTICE/TEACHER_LANGUAGE, governance_status: PENDING/ALLOW/TRANSFORM_ONLY/DENY | S1 Discovery + S2 거버넌스 판정(사람 승인 — SOURCE_DECISION 이벤트 32건) | Foundry S1~S2 |
| source_documents | 소스 **원문** 저장소 — **ALLOW 소스만 저장 가능**(절대 규칙 7). 앱 가드(store_raw_document)+DB 트리거(0003) 이중 강제, ALLOW에서 강등 시 원문 퍼지(0004_purge_raw_on_downgrade) | S2 통과 소스의 수집 | Foundry S2~S3 |
| situation_frames | S3가 원문에서 추출한 상황 프레임(참여자·재료·교사 고민). `extraction_confidence < foundry.extract_min`(0.60)이면 사람 검토 | S3 Extractor(LLM) | Foundry S3 |
| canonical_scenarios | S5가 frame을 워크스페이스 상태(visual_semantics vs-1.0 포함)로 구체화한 정경 시나리오. episodes.scenario_id가 참조 | S5 Situation Builder | Foundry S5 |
| atlas_entries | 표현 지도 — 애매 발화 표면형과 후보 intent·해소 신호. embedding 보유(retrieval [1]단계 원료) | S4 Language Miner | `/v1/intent/infer`의 retrieval이 소비 |
| atlas_expansion_queue | 어떤 pattern_cluster에도 매핑 안 된 발화의 큐(PENDING/CLUSTERED/DISMISSED) — 주간 클러스터링으로 신규 cluster 후보 | 추론 중 미매핑 발화 적재 | §2-4 확장 루프 |
| foundry_work_queue | A형(커버리지) 강화 주문 — 사람 세션 없이 Foundry에 시나리오 생성 지시(order_type=SCENARIO_COVERAGE, PENDING→IN_PROGRESS→DONE/DISMISSED) | Observatory 클릭 진단(COVERAGE_LOW)이 발행 | Challenge Pack → Foundry S5~S10 |
| failed_episodes | 배치 실패 격리 큐 — 한 에피소드 실패가 배치를 중단시키지 않게 | 배치 러너 자동 | `scripts/run_campaign.py` 등 |

표 E-②

| 항목 | TRAIN 사용 | BENCHMARK 사용 | 오염·개인정보 위험 |
|---|---|---|---|
| sources / source_documents | 합성 생성의 원천 | 불가 | **TRANSFORM_ONLY 소스의 원문 저장 금지**(절대 규칙 7) — 패러프레이즈 유사도 가드(`foundry.paraphrase_max` 0.90) 테스트 유지. 원문엔 저작권·실교사 언어가 들어 있을 수 있다 |
| situation_frames / canonical_scenarios | 에피소드 계보(§3 참조 무결성) | 불가 | **훈련 메타데이터(scenario_id·ground truth 등)는 Brain 추론 Core 입력에 절대 넣지 않는다**(절대 규칙 5) — 계보는 저장하되 추론에는 새지 않게 |
| atlas_entries / expansion_queue | retrieval 원료 / 확장 후보 | 불가 | **둘 다 현재 0건** `PARTIAL` — atlas 미적재 상태에서 retrieval은 exemplar 축만 동작. expansion_queue의 utterance는 원문 보관(PII 유의) |
| foundry_work_queue / failed_episodes | 생산 지시/실패 기록 | 불가 | failed_episodes.error에 프롬프트 파편이 남을 수 있다 |

### F. 사람·운영 계열

표 F-①

| 항목(테이블) | 쉬운 의미 | 생성 주체·경로 | 관련 API·script |
|---|---|---|---|
| persona_clusters / population_priors / teacher_priors / persona_state_versions | 교사 성향: 클러스터(HDBSCAN, §4-1) · 클러스터별 intent 사전확률 · 트레이너 개인 prior(fast update가 미세조정, cap `brain.persona_prior_cap` 0.20) · prior 스냅샷 버전(replay 축) | `run_persona_discovery`(클러스터링), `run_fast_update`(개인 prior + 주간 decay) | `scripts/run_persona_discovery.py`, `scripts/run_fast_update.py`, `GET /v1/observatory/persona-overlay` |
| challenge_packs / gym_sessions | 훈련 팩(전략·타깃 edge·아이템 수)과 훈련 세션(트레이너·모드·결과) | Observatory 진단 → pack 생성, 사람이 세션 플레이 | `POST /v1/gym/pack`, `POST /v1/gym/session`, `POST /v1/gym/session/{id}/submit` |
| intent_display / intent_change_requests | 의도 표시 오버레이(한글 이름·설명 — 즉시) / 의미·구조 변경 제안 대기열(PENDING/APPROVED/REJECTED — 승인은 "반영 예약"일 뿐) | 운영자 PIN 수정 / 누구나 제안 + PIN 판정 | `/v1/ontology/*` — 절차는 [04-ontology-and-intents.md](04-ontology-and-intents.md) §4-7 |
| governance_events | 모든 승인 흔적의 단일 저장소 — 소스 판정·전문가 유입·노드 생성/이동·표시 수정·리스크 개정·mock 정리 | 각 거버넌스 경로가 필수로 남김 | (조회 전용) |
| ontology_versions | 온톨로지 버전 레지스트리(change_type minor/major, migration_map) | 온톨로지 개정 거버넌스 | `scripts/apply_ontology_examples.py --register` |
| alembic_version | 마이그레이션 포인터(도메인 데이터 아님) | alembic | `alembic upgrade head` |

표 F-②

| 항목 | TRAIN 사용 | BENCHMARK 사용 | 오염·개인정보 위험 |
|---|---|---|---|
| persona 4테이블 | 추론 [3]단계 prior 재정렬(LLM 밖, cap 20%) | persona_state_version이 replay 축으로 고정(미발급 시 sentinel `none`) | trainer_ref로 개인 식별 가능 — 트레이너 신원 데이터. 개인 prior 분기는 최소 상호작용 `persona.min_interactions`(10) 뒤에만 |
| challenge_packs / gym_sessions | 세션 결과가 evidence로 수용(§8-1) | 불가 | **훈련 메타(ground truth·target_confusion)는 mode=gym이어도 Core 입력 금지**(절대 규칙 5). 즉석 문답이 쌓은 시험 후보는 blind 2차 검수(`run_benchmark_review.py`)를 거쳐야 벤치마크행 |
| intent_display / change_requests | — | — | 표시 계층은 YAML·버전 불변(우회 불가) — CSV 일괄 수정도 이름·설명만 |
| governance_events | — | — | 없음(감사 목적) — 오히려 이 표가 비어 가는 것이 위험 신호 |

## 5-6. 현재 건수 스냅샷 — 2026-07-17 13:16 수집 (읽기 전용)

[근거: 팩트팩 "DB 스냅샷" 절 — 아래 수치는 그대로 옮김]

| 테이블 | 총건수 | 내역 |
|---|---:|---|
| episodes | 2,729 | split: TRAIN 2,343 · BENCHMARK_HOLDOUT 386 |
| 〃 state별 | | REJECTED 2,229 · LABELED 386 · LABEL_CANDIDATE 91 · EVIDENCE_ACCUMULATING 23 (REJECTED에는 07-17 mock 자리표시자 정리 2,002건 포함) |
| 〃 tier별 | | SILVER 1,166 · BRONZE 1,154 · GOLD 386 · UNVERIFIED 23 — **GOLD 386은 전부 BENCHMARK, TRAIN GOLD 0** |
| 〃 origin별 | | FOUNDRY_SYNTHETIC 2,310 · EXPERT_AUTHORED 386 · GYM_HUMAN 33 |
| evidence | 3,529 | SYNTHETIC_CONSENSUS 2,310 · DOMAIN_RULE 1,156 · HUMAN_CONFIRMATION 50 · HUMAN_CORRECTION 13 · (WEAK_BEHAVIORAL 0 · EXPERT_REVIEW 0) · adversarial=true **0** |
| exemplars | 0 | TRAIN GOLD 0의 결과 |
| brain_nodes | 70 | COMMUNICATION 9 · DOCUMENT 9 · OBSERVATION 9 · OPERATION 9 · PLAY 9 · REFLECTION 10 · STUDIO 8 · VISUAL 7 |
| confusion_edges | 629 | 전부 state=hypothesized · origin=SKEPTIC |
| ktib_versions / ktib_items | 3 / 572 | ktib-1(1) · ktib-2(185) · ktib-3(386) |
| arena_runs | 4 | zero_shot_baseline 0.8811(claude-sonnet-5, ktib-2, 07-14) · brain seed-v0 0.0 ×2(ktib-2, 07-14) · brain seed-v0 0.0(ktib-3, 07-16) |
| brain_versions | 0 | version gate 미발동 |
| inference_logs | 764 | mode: arena 756 · gym 8 |
| review_votes | 10 | 웹 검수 진행 중 |
| intent_display / intent_change_requests | 1 / 0 | 표시 오버레이 1건 |
| ktib_uploads | 1 | 시험지 업로드 이력 |
| atlas_entries / atlas_expansion_queue | 0 / 0 | S4 적재 전 |
| governance_events | 43 | SOURCE_DECISION 32 · EXPERT_EPISODE_INGEST 3 · NODE_REGION_MOVE 2 · INTENT_DISPLAY_BULK_EDIT 2 · NODE_BOOTSTRAP 2 · MOCK_BANK_CLEANUP 1 · RISK_MODEL_UPDATE 1 |
| sources · source_documents · situation_frames · canonical_scenarios · challenge_packs · gym_sessions · failed_episodes · persona_* 4종 · foundry_work_queue · benchmark_candidate_* · ontology_versions | 미수집 | 팩트팩 스냅샷에 건수 없음 `UNKNOWN` |

---

## 현재 상태

- 스키마·무결성 가드(CHECK 2종, provenance 4필드, dedup, 원문 저장 가드): `IMPLEMENTED`
- 합성 계보(S1~S10)·전문가 유입·웹 검수·시험지 스테이징: `IMPLEMENTED` — 증산 캠페인 실 LLM 가동 중(검수 대기 91+ 증가 중)
- TRAIN 쪽 GOLD·exemplar·atlas: `PARTIAL` — 전부 0건이라 추론이 abstain만 하는 정직한 0 상태
- adversarial evidence·WEAK_BEHAVIORAL·EXPERT_REVIEW: `DESIGNED` — enum·분리 가드는 있으나 실데이터 0
- brain_versions(버전 승격): `PARTIAL` — 코드는 있으나 min_new_gold 200 미충족으로 이력 0
- live rollout(Suggest/Assist/Auto) 관련 데이터 경로: `BLOCKED`(PARTIAL HOLD) — mode=gym만 서빙

## 주의사항

- **수치는 2026-07-17 13:16 스냅샷 고정값**이다. 캠페인이 돌고 있어 episodes·evidence는 이미 늘었을 수 있다 — 문서를 수치의 원천으로 쓰지 말고 재수집하라.
- DB에 직접 INSERT/UPDATE 금지: GOLD는 검수의 문으로만, brain_nodes는 승인 플로우로만, brightness는 Arena만(절대 규칙 3·4). `label_state`(워크플로)와 `reliability_tier`(품질)를 절대 혼용하지 말 것(절대 규칙 8).
- 발화 원문이 사는 곳(episodes·ktib_items·candidate_items·expansion_queue·ktib_uploads.source_document)이 개인정보 관리 대상의 전부다 — 실아동 식별 정보를 입력하지 않는 운영 습관이 유일한 방어선이다(코드는 이름의 실존 여부를 모른다).
- 시험지에 넣을 발화를 LLM으로 생성하는 것은 코드가 못 막는다 — `authored_by` 기록과 사람의 규율이 마지막 가드다.

## 다음 단계

1. **TRAIN GOLD 0 탈출** — 검수 대기(91+)를 웹 검수(/v1/review)로 GOLD 승격 → `run_backfill`로 exemplar 생성 → seed-v0 0.0% 탈출의 선행 조건.
2. **atlas 적재(S4)** — retrieval의 두 번째 축(atlas_entries 0건) 채우기와 미매핑 큐 가동.
3. **adversarial·행동 신호 경로 가동** — Break the Brain 세션과 WEAK_BEHAVIORAL 수용(현재 enum만 존재).
4. **미수집 테이블 건수 계측 추가** — sources~persona 계열을 팩트팩 수집 스크립트에 포함해 다음 스냅샷부터 공백 제거.
