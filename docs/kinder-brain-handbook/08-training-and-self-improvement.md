# 08. 훈련과 자가 강화 — 자동으로 성장하되, 자기 답을 정답으로 확정하지 않는다

> **한눈에 보기** — 킨더브레인의 성장 루프는 대부분 자동이다(약점 진단→증산→혼동 가설→측정→조건부 승격). 그러나 단 한 지점 — **"이 답이 정답이다"라는 최종 확정** — 만은 사람 2인의 몫으로 남겨 두었고, 코드·DB 제약이 이를 물리적으로 강제한다. 이 분리가 "자가 채점 오염"(AI가 자기 답을 정답 삼아 자기 점수를 올리는 붕괴)을 막는 이 시스템의 핵심 설계다.

---

## 1. 쉬운 설명 — 왜 "자동 강화"와 "자가 채점"을 구분하나

학생이 문제도 만들고, 풀고, **채점까지 스스로** 하면 성적은 무조건 100점이 된다 — 실력과 무관하게. AI도 같다. 자기 판정을 자기 학습 정답으로 쓰면 오류가 눈덩이처럼 증폭된다(가짜 확신 강화).

그래서 킨더브레인은:
- **문제 만들기·풀기·의심하기·재기**는 자동으로 돌리고,
- **정답 도장(GOLD)과 시험 출제(KTIB)**만 사람에게 남겼다.

> **핵심 문장** — "킨더브레인은 자동으로 성장하지만, 자기 답을 스스로 정답으로 확정하지 않는다."
> 의미: AI 합의는 후보 라벨(상한 SILVER)까지만 만들 수 있고, LABELED·GOLD로의 전이는 인간 2인 일치라는 문 하나로만 통과한다. 그 문 밖의 어떤 코드도 GOLD를 쓸 수 없다. [근거: backend/app/aggregator/aggregator.py::recommend_tier "GOLD은 절대 반환하지 않는다", backend/app/aggregator/review.py 머리말 "GOLD를 만드는 유일한 경로"]

---

## 2. 완전 자동 영역 (사람 개입 없음)

| 자동 기능 | 무엇을 하나 | 근거 |
|---|---|---|
| 약점 진단 | 노드별 4축(애매 언어·화면 커버리지·성향 다양성·GOLD 부족) 계산 | [근거: backend/app/brain/diagnosis.py] |
| 증산(campaign) | 약점 도메인 배분으로 합성 발화 대량 생성, 품질 윈도 악화 시 자동 중단 | [근거: backend/app/foundry/campaign.py, scripts/run_campaign.py] |
| 합성 후보 생성 | 여러 AI 교차 검토(생성→분석→회의→합의)를 통과한 것만 저장 | [근거: backend/app/foundry/episode_builder.py] |
| Skeptic 혼동 가설 | "이 의도, 저것과 헷갈리지 않나?" 가설 edge 자동 발굴(현재 629개 전부 hypothesized) | [근거: backend/app/foundry/stages/s8_skeptic.py, DB 실측] |
| Arena 측정 | 동결 시험지로 채점, 혼동 가설을 실측으로 확정/기각 | [근거: backend/app/arena/runner.py, backend/app/arena/reflect.py] |
| candidate 비교·조건부 승격 | new GOLD ≥ 200 → 후보 뇌 빌드 → 같은 시험지 비교 → 조건 통과 시에만 promote | [근거: scripts/run_version_gate.py, backend/app/arena/gate.py] |

## 3. 인간이 반드시 필요한 영역 (설계된 게이트)

| 인간 게이트 | 왜 사람인가 | 강제 장치 |
|---|---|---|
| 정답 최종 승인(GOLD) | 자가 채점 차단의 핵심 | 유일문 apply_review_batch — 2인 만장일치 ∧ 배치 kappa≥0.65 [근거: backend/app/aggregator/review.py] |
| KTIB 문항 저작 | 시험 발화를 LLM이 쓰면 시험이 합성 분포가 됨(코드로 탐지 불가 — 운영 원칙) | 비합성 채널만 + authored_by 필수 + 거버넌스 기록 [근거: backend/app/foundry/expert_ingest.py] |
| 2인 독립(blind) 검수 | 앵커링(서로 답 베끼기) 방지 | 웹 큐가 타인 표·집계 제안을 비노출 [근거: backend/app/api/review.py::review_queue] |
| 신규 의도(노드) 승인 | 온톨로지 무결성 — 자동 INSERT 금지 | atlas 큐 → 승인 플로우 + governance_events [근거: CLAUDE.md 절대 규칙 4, backend/app/api/ontology_admin.py] |
| 중요 정책 변경 | 임계값·목표 변경은 문서 Change Log + 승인 | config 단일 원천 + 설계문서 이력 [근거: config/experiments.yaml, docs/01-foundry/... Change Log] |

---

## 4. S1~S10 Foundry 파이프라인 (전부 실존 — IMPLEMENTED)

| 단계 | 파일 | 목적 | 입력 → 출력 | 실행 조건 |
|---|---|---|---|---|
| S1 Discovery | stages/s1_discovery.py | 소스 후보 등록 | 소스 메타 → sources 행 | pilot/campaign 시작 시 |
| S2 Governance | stages/s2_governance.py | 소스 사용 판정(ALLOW/TRANSFORM_ONLY/DENY) + 원문 보관 정책 | 소스 → governance_status·source_documents | S1 직후 |
| S3 Extractor | stages/s3_extractor.py | 상황 프레임 추출 | 문서 → situation_frames | ALLOW/TRANSFORM_ONLY 소스 |
| S4 Language Miner | stages/s4_language_miner.py | 교사 말투 패턴 채굴(패러프레이즈 유사도 가드) | 프레임 → 표현 재료 | S3 후 |
| S5 Situation Builder | stages/s5_situation_builder.py | 정본 시나리오 생성(visual_semantics 통제 어휘) | 프레임 → canonical_scenarios | S4 후 |
| S6 Simulator | stages/s6_simulator.py | 시나리오+성향으로 발화 생성 | 시나리오·persona → 발화 | 에피소드 생성 시 |
| S7 Analyst | stages/s7_analyst.py | 발화의 의도 후보 분석 | 발화 → 후보+activation | S6 후 |
| S8 Skeptic | stages/s8_skeptic.py | 적대적 반문 — 혼동쌍 가설 | 후보 → confusion_edges(hypothesized) | S7 후 |
| S9 Judge | stages/s9_judge.py | 품질 심판(반려 판정) | 후보 → 채택/반려 | S8 후 |
| S10 Consensus | stages/s10_consensus.py | 다판정 합의 점수 | 판정들 → consensus·SYNTHETIC_CONSENSUS evidence | S9 후 |

- 오케스트레이션: pilot(소량)·campaign(대량) [근거: backend/app/foundry/pilot.py::run_pilot, backend/app/foundry/campaign.py::run_campaign]
- S11·S12: 설계문서의 후속 단계 번호와 코드 파일의 1:1 대응은 UNKNOWN(스테이지 파일은 S10까지). S13(backfill)은 별도 모듈로 실존 [근거: scripts/run_backfill.py 머리말 "S13"].
- 실전 교훈(2026-07-17): 실 LLM이 계약 밖 키를 덧붙여 크래시 → 교정 재시도 1회 + 에피소드 단위 실패 허용으로 보강. mock에선 절대 안 드러나는 sim-to-real 간극이었다. [근거: backend/app/foundry/agents/runner.py::run_json_agent]

---

## 5. Backfill — 무엇을 만들고, 무엇을 만들면 안 되는가

**만드는 것** (전부 멱등): ① 노드 부트스트랩(온톨로지 기준 — 승인된 거버넌스 경로) ② **대표 예문 선정** — GOLD∧LABELED 에피소드에서, 기존 예문과 임베딩 거리 ≥ 0.15만 채택 ③ 노드 evidence 통계 집계. [근거: backend/app/brain/backfill.py::run_backfill·select_exemplars, config::brain.exemplar_min_dist]

**만들면 안 되는 것** (테스트로 고정):
- brightness(heldout_accuracy) — Arena 전용. backfill이 건드리면 가드가 폭발한다. [근거: backend/app/models/guards.py, CLAUDE.md 절대 규칙 3]
- BENCHMARK_HOLDOUT 예문 — 시험 문항이 교과서에 실리면 암기 측정. [근거: §8-2 격리 테스트]
- 새 발화 — backfill은 **선정**이지 생성이 아니다. "Backfill 합성 데이터"라는 표현은 오용(합성 생성은 campaign 소관).

**합성 데이터의 한계와 위치**:
- 상한 SILVER — 아무리 합의 점수가 높아도 GOLD가 될 수 없다... 는 아니다. 정확히는: 합성도 **사람 2인 검수를 통과하면** GOLD·대표 예문이 될 수 있다(그 노동이 게이트다). 단 **시험지(BENCHMARK)에는 절대 못 들어간다** — DB CHECK가 origin부터 차단. [근거: backend/app/aggregator/review.py 머리말, benchmark_integrity CHECK]
- 실측 교훈: mock 시절 자리표시자 합성 2,002건은 검수 불능이라 전량 REJECTED 처리했다(가짜 GOLD 오염 방지). [근거: scripts/cleanup_mock_bank.py, governance MOCK_BANK_CLEANUP]
- 인간 데이터와의 차이: 합성은 분포를 넓히는 **연습문제**, 인간 확인·교정은 정답 방향을 잡는 **선생님의 빨간펜**, 전문가 저작은 실력을 재는 **시험지** — 셋의 역할이 섞이지 않게 provenance 4필드가 붙는다.

## 현재 상태
- 자동 영역: 전부 IMPLEMENTED (campaign은 지금도 백그라운드 증산 중).
- 인간 게이트: 장치 IMPLEMENTED · 데이터 BLOCKED — TRAIN GOLD 0, 검수 대기 91+. 승격 루프(§6-6)는 첫 GOLD 200을 기다린다.

## 주의사항
- "자동으로 좋아진다"고 말할 때는 반드시 "정답 확정은 사람"을 함께 말할 것 — 이 구분이 무너지면 시스템 신뢰의 근거가 사라진다.
- 증산은 과금 작업이다(실측 $0.071/건) — 실행은 운영자 트리거만.

## 다음 단계
- 성장 루프의 채점·승격 조건 상세: [09-evaluation-and-performance.md](09-evaluation-and-performance.md)
- 검수 실무: [11-operations-guide.md](11-operations-guide.md)
