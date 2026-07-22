# 11. 운영 가이드 — 역할별 실전 매뉴얼

> **한눈에 보기** — 이 문서는 **실존하는 스크립트·옵션·버튼만** 다룬다(창작 금지 — `scripts/` 20개 파일·웹 버튼 라벨을 코드와 대조해 작성). 역할 5개: **A. 훈련자**(즉석 문답으로 뇌를 가르친다) / **B. 검수자**(2인 일치로 GOLD·시험 문항을 확정한다) / **C. 데이터 담당자**(CLI 배치 — 검수 적용·유입·증산·시험지 동결) / **D. 개발자**(서버·테스트·마이그레이션) / **E. 운영자**(채점 PIN·의도 목록·동기화·승격/반려). 공통 원칙: 모든 배치는 **기본 dry-run, `--commit`일 때만 반영**이고, GOLD는 §3-3(2인 일치), 밝기는 Arena(절대 규칙 3), 노드 생성은 거버넌스(절대 규칙 4)만 만든다.

이 문서의 수치(임계값·실측치)는 `config/experiments.yaml`과 검증 팩트팩(2026-07-17 수집) 원천이다. 상태 태그: IMPLEMENTED / PARTIAL / DESIGNED / BLOCKED / UNKNOWN.

---

## 0. 공통 준비

- **CLI 실행 위치**: 저장소 루트에서 `python scripts/<이름>.py …`. 모든 스크립트가 루트 `.env`를 자동 로드한다(`load_dotenv`) [근거: scripts/run_human_review.py 등 공통 부트스트랩].
- **웹 진입**: 3D 뇌 화면 톱바의 **📋 TODO** 버튼 하나로 통합(2026-07-17 사용자 결정) — 5단계 안내(① 시험지 만들기(실력을 재는 자) → ② 공부 재료 모으기(검수할 발화) → ③ 공부 검수 — 두 사람이 정답 확정(GOLD) → ④ 채점 실행 — 첫 진짜 점수 → ⑤ 반복해서 올리기)에서 각 화면(시험지 업로드·공부 검수·즉석 문답)으로 이동한다 [근거: frontend/src/panels/todoSteps.ts, frontend/src/panels/TodoPanel.tsx].
- **PIN**: 채점·의도 수정의 PIN은 기본 `2341`(env `ARENA_PIN` / `ONTOLOGY_PIN`으로 교체) — **보안장치가 아니라 오클릭 방지 자물쇠** [근거: backend/app/api/arena_ops.py::_pin, backend/app/api/ontology_admin.py::_pin].

---

## A. 훈련자(직원) — 즉석 문답으로 뇌 가르치기

**목적**: 자유 발화를 브레인에 던져 추론을 보고, 사람 정답으로 확인/교정 evidence를 쌓는다(§6-7 [4]~[6]). IMPLEMENTED

**실행 방법(버튼 경로)**: 톱바 📋 TODO → "공부 재료 모으기" 단계 → 즉석 문답 패널(LiveQuizPanel). 흐름:

1. 발화 입력 → 브레인이 후보 3~4개(계약상 최대 5)와 판정을 보여준다(내부적으로 `POST /v1/intent/infer` mode=gym → `POST /v1/gym/live/feedback`).
2. 정답 판정 —
   - 후보 중 정답 클릭(top이 맞으면 확인=HUMAN_CONFIRMATION, 다른 후보면 교정=HUMAN_CORRECTION).
   - 후보에 없으면 **[목록에 없어요 — 직접 찾기]**(전체 의도 검색·라벨 자동완성)에서 정답 기록 — 교정은 가장 강한 인간 신호다.
   - 브레인이 모른다고 하면(abstain) 화면 문구: "브레인이 아직 이 말을 몰라요 — 정답을 알려주시면 배웁니다" → **[정답 의도 찾기]**.
   - 진짜 새로운 의도면 **[딱 맞는 의도가 없어요 — 새 의도로 제안하기]** → atlas 확장 큐 제안(노드 자동 생성 없음 — 절대 규칙 4). 접수 문구: "새 의도 후보로 접수했어요. 검토를 거쳐 승인되면 새 노드가 생겨요."
3. **[시험 문제로 출제 (학습에 쓰지 않고 2차 검수 후 시험지로)]** 토글 — 켜면 이 문답은 훈련에 쓰지 않고 blind 2차 검수 대기열(`seeds/benchmark_candidates.yaml`)로만 간다. 완료 문구: "문항이 시험 출제 대기열에 있어요."

**훈련용 vs 출제용 구분(중요)**: 같은 발화는 학습(TRAIN)과 시험(BENCHMARK) 양쪽에 못 간다 — 서버가 오염을 409로 차단한다(§8-2 학습/시험 분리) [근거: backend/app/api/gym.py::live_feedback (TrainBenchmarkContamination→409)].

**입력·출력**: 입력 = 발화 + 정답 선택(또는 출제/새 의도). 출력 = 반영 결과(확인/교정/출제 대기/새 의도 접수) + 노드 pending 링.
**DB 변경**: 훈련 = episodes(GYM_HUMAN)+evidence(+aggregator 전이). 출제 = 파일 대기열(DB 아님). 새 의도 = atlas_expansion_queue 1행.
**실패 시**: "이미 반영된 문답입니다"(같은 문답 중복 제출 — 새로 입력하면 됨) / "이미 출제 대기 중인 발화입니다" / "온톨로지에 없는 intent"(검색 목록에서 골라야 함). 밝기는 절대 변하지 않는다 — 훈련은 크기(size)·pending만 바꾸고 점수는 채점(Arena)에서만 오른다(절대 규칙 3).
**실행 전 확인**: 없음(항상 안전 — 잘못 고른 정답은 검수·재문답으로 상쇄).

---

## B. 검수자 — 2인 일치 확정

### B-①. 공부 검수 웹 (🔍 2인 → GOLD) — IMPLEMENTED

**목적**: 검수 대기 발화에 서로 다른 두 사람이 독립적으로 정답을 붙여, 일치분만 GOLD로 확정한다(GOLD를 만드는 유일한 규칙 §3-3).
**실행 방법**: 톱바 📋 TODO → "공부 검수" → 패널 "🔍 공부 검수 — 두 사람이 맞으면 정답(GOLD)".

1. **이름 입력** — 표는 이 이름(정규화)으로 쌓인다. 별칭·대소문자 위장 불가.
2. **blind 발화 목록** — 다른 검수자의 표·집계 제안은 절대 보이지 않는다(앵커링 방지) [근거: backend/app/api/review.py 모듈 docstring].
3. 발화마다: **추천/검색으로 의도 선택** 또는 **[🗑 못 쓰는 발화 (폐기 표)]** 또는 **[건너뛰기]**. (07-20 UX: 발화가 나온 **화면 상황이 함께 표시**되고, 목록은 **판단 쉬운 순**으로 정렬되며, 똑같은 문장은 **같은 문장 배지**로 묶여 보인다. 추천 의도는 스크롤 끝에서 자동으로 이어 나온다 — 커밋 98757a3·c5de42a.)
4. 두 사람 표가 모이면 **[✓ 일치분 GOLD 확정 (대표 예문 자동 생성)]**.

**게이트(전부 서버 강제, 우회 없음)**: 서로 다른 검수자 2인 미만 → "검수자 2인 이상의 표가 필요해요 …(1인 확정 금지 §3-3)". 배치 kappa < `review.min_agreement_kappa`(0.65) → **전량 반려(부분 승격 없음)**. 에피소드별 만장일치 아니면 보류. 확정 성공 시 **backfill(대표 예문) 자동 체인** — 사람은 검수만 하면 된다 [근거: backend/app/api/review.py::apply_votes].
**입력·출력**: 입력 = 이름+표. 출력 = "확정 N건(GOLD) · 폐기 N건 · 보류 N건 · 대표 예문 +N".
**DB 변경**: review_votes(표) → episodes 상태 전이(LABELED/REJECTED)+GOLD 승격 → exemplars.
**실패 시·복구**: kappa 반려 메시지가 그대로 뜬다 — 불일치 항목을 두 사람이 다시 보고 표를 갱신(재제출=갱신) 후 다시 확정. backfill이 실패해도 확정은 유지되고 다음 확정에서 따라잡는다(멱등).
**실행 전 확인**: 두 사람이 **각자 독립적으로** 판단했는가(화면도 서로의 표를 숨긴다).

### B-②. 시험지 검수 (문항 → KTIB) — IMPLEMENTED

시험지(KTIB)에 문항을 넣는 웹 경로는 둘 다 "2인 일치" 인증을 거친다: **kappa ≥ 0.65(독립 라벨) OR 관측 일치율 ≥ 0.80(O/X 승인, `review.min_expert_agreement` — §3-3 v1.6: 판정이 쏠려 kappa가 base-rate 역설로 퇴화하는 경우의 대체 척도)** [근거: backend/app/foundry/expert_ingest.py, config/experiments.yaml::review].

**(a) 웹 1~5 평점 플로우** — 모달 "시험지 작성·검수 (1~5 평점)" (2대 컴퓨터 흐름):
- 탭 **① 문항 작성**: 영역별 질문 작성 + 작성자(A)가 각 문항 1~5 평가 → **[제출 (2차 검수 요청) · 작성 N문항]** → "검수 대기"로 이동.
- 탭 **② 검수 대기**: **다른 사람(B)** 이 blind로 1~5 평가(작성자 점수는 절대 안 보임 — anti-anchoring) → 제출하면 서버가 가중 kappa 계산.
- 탭 **③ 내 제출**: 상태 확인(2차 검수 대기중/검수 완료/등록됨). 일치도 통과 + 두 검수자 모두 `min_item_rating`(4)↑ 문항이 있으면 **[📥 시험지로 등록]**(dry-run 검증) → **[✓ 등록 확정]**.
- 실패 문구 예: "1차 검수자와 다른 사람이어야 해요", "검수 일치도가 기준에 못 미쳐 등록할 수 없습니다", "두 검수자가 모두 높게 평가한 문항이 없어 등록할 수 없습니다" [근거: backend/app/api/observatory.py::register_candidate_batch].

**(b) CSV 업로드(O/X 검수)** — 화면 "시험지 업로드"(톱바 TODO ① 또는 도움말 경유):
- 쉬운 양식(엑셀·구글시트 — `seeds/ktib_exam_template.csv`, critical 집중은 `seeds/ktib_critical7_template.csv`)에 **질문을 쓰고 검수자 두 분이 O/X만 체크** → **[⬆ 작성한 양식 올리기 (엑셀·CSV)]** → 일치율(kappa 포함)은 **자동 계산** → 검증(dry-run) 표에서 "✅ 두 분 모두 O (등록 대상) N개" 확인 → **[✓ 등록 확정]**.
- 한국어 Windows 엑셀 기본 "CSV(쉼표로 분리)"(CP949)도 자동 인식; 이상 파일이면 "CSV UTF-8(쉼표로 분리)로 저장한 뒤 올려주세요" 안내.
- 실패 문구: "두 검수자가 모두 O로 통과시킨 질문이 아직 없어요 — 등록할 문항이 없어요." / 서버 거부는 `거부: <사유>` 그대로 표시(합성 채널·검수 미달·학습 오염·미지 intent).
**DB 변경**: 등록 확정 시에만 episodes(BENCHMARK_HOLDOUT·GOLD) + ktib_versions 동결 + 업로드 이력 1행(원문 보관). dry-run은 DB 불변(savepoint 롤백).
**실행 전 확인**: 문항 발화가 **사람이 쓴 비합성**인가(LLM 생성 문장을 시험지에 넣으면 벤치마크가 무의미해진다 — 코드가 탐지 못 하므로 사람이 지켜야 하는 규칙). 등록 후 채점은 자동 실행되지 않는다 — 운영자가 별도로 돌린다.

### B-③. 출제 대기열 blind 2차 검수 (CLI) — IMPLEMENTED

**목적**: 즉석 문답의 "시험 문제로 출제"가 쌓은 후보를 독립 검증한다(§3-3·§8-2).
**실행 방법**:

```bash
python scripts/run_benchmark_review.py --queue blind.yaml        # ① 2차 검수용 blind 파일 생성
# ② 2차 검수자가 blind.yaml에 독립적으로 라벨 기입 (파일에는 발화만 — 1차 라벨·뇌 추측·후보 없음)
python scripts/run_benchmark_review.py --apply blind.yaml        # ③ 대조 리포트 (dry-run)
python scripts/run_benchmark_review.py --apply blind.yaml --write  # ④ 대기열 파일 확정 갱신
# --candidates <path> : 대기열 경로 변경 (기본 seeds/benchmark_candidates.yaml)
```

**입력·출력**: 파일에서 파일로만 — **DB 접근 없음**. 통과 항목만 reviewers 2인+kappa가 기록되어 `ingest_expert_episodes` 자격을 갖추고, 불일치는 rejected 목록으로 정직하게 남는다.
**실패 시**: 대기 항목이 없으면 exit 2("2차 검수 대기 항목이 없다 — 즉석 문답의 '출제'가 먼저 쌓여야 한다"). 배치 kappa 미달이면 아무것도 확정하지 않는다.
**실행 전 확인**: 2차 검수자가 1차와 **다른 사람**인가, blind 파일을 채우는 동안 1차 라벨을 보지 않았는가.

---

## C. 데이터 담당자 — CLI 배치

공통: 전부 **기본 dry-run(롤백), `--commit`일 때만 DB 반영**. 실 LLM/임베딩 provider면 과금됨.

| 스크립트 | 목적 | 옵션(실존 전수) |
|---|---|---|
| `run_human_review.py` | 검수 표 배치 적용 — GOLD를 만드는 유일한 경로(웹 검수와 동일 규칙) | `--queue` `--limit` `--out` `--apply <yaml>` `--commit` |
| `ingest_expert_episodes.py` | 전문가 저작 에피소드 유입 — KTIB에 데이터를 넣는 유일한 경로 | `--template <path>` `--file <path>` `--commit` |
| `run_backfill.py` | S13 backfill — 노드·exemplar·evidence_stats 적재 | `--commit` `--approved-by` |
| `run_ktib_build.py` | KTIB 스냅샷 발급·동결 | `--commit` `--notes` |
| `run_campaign.py` | 10k~30k 합성 증산 캠페인 | `--n`(기본 1000) `--baseline-n`(기본 200) `--commit` |
| `run_zero_shot_baseline.py` | 범용 LLM zero-shot 기준 측정(제안서만 — 목표 자동 변경 없음) | `--commit` `--model` `--write-report` |
| `cleanup_mock_bank.py` | mock 자리표시자 에피소드 REJECTED 정리(일회성 위생) | `--commit` |
| `train_coverage.py` | 의도·도메인별 훈련량 표(읽기 전용) | `--json` |
| `ktib_coverage.py` | 의도별 시험 문항 수 vs 게이트 하한(읽기 전용) | `--json` |
| `mine_atlas.py` | 수동 원문(실제 교사 언어 발췌 등) → Atlas 채굴 주입구(S1+S2+S4 일괄, 줄당 LLM 1회 — 07-20 추가) | `file` `--title`(필수) `--source-class`(기본 TEACHER_LANGUAGE) `--commit` |

[근거: 각 scripts/*.py docstring·argparse — 팩트팩 "scripts 각각의 첫 docstring + argparse 옵션" 절과 대조]

### C-1. `run_human_review.py` — 검수 적용 (IMPLEMENTED)

```bash
python scripts/run_human_review.py --queue --limit 20      # 검수 대기 목록을 파일로 추출
python scripts/run_human_review.py --apply reviews.yaml            # dry-run
python scripts/run_human_review.py --apply reviews.yaml --commit   # 확정
```

이 스크립트는 검수하지 않는다 — **사람이 채운 판정 파일을 적용할 뿐**. `--queue`가 뽑은 파일을 서로 다른 검수자 2인 이상이 각자 채운 뒤 합쳐 `--apply`. 판정 파일 형식(원문 예시): `votes: [{episode_id, reviewer_ref, chosen_intent|null}]` + `approved_by`. 배치 kappa 미달·계산 불가면 아무것도 확정 안 됨. **`--commit` 성공 시 run_backfill 자동 체인**(dry-run에서는 임베딩 과금 방지를 위해 예고만). 주의: 합성 에피소드도 GOLD가 될 수 있으나(그건 exemplar·new_gold용) `benchmark_integrity` CHECK 때문에 KTIB에는 영원히 못 들어간다(절대 규칙 2).

### C-2. `ingest_expert_episodes.py` — 시험 데이터 유입 (IMPLEMENTED)

```bash
python scripts/ingest_expert_episodes.py --template ktib_seed.yaml   # 빈 양식 생성
python scripts/ingest_expert_episodes.py --file ktib_seed.yaml       # dry-run
python scripts/ingest_expert_episodes.py --file ktib_seed.yaml --commit
```

**★ 발화를 생성하지 않는다** — 입력은 사람이 쓰거나 사람이 수집·검수한 비합성 발화여야 한다. `authored_by` 필수(거버넌스 이벤트 기록). 인증: 2인 reviewers ∧ (kappa ≥ 0.65 ∨ 일치율 ≥ 0.80). 실패 시 `BenchmarkNeedsReview` 등 사유가 그대로 출력 — 검수부터 다시.

### C-3. `run_backfill.py` — 대표 예문·노드 적재 (IMPLEMENTED)

```bash
python scripts/run_backfill.py                    # dry-run
python scripts/run_backfill.py --commit           # 실제 적재 (--approved-by 지정)
EMBEDDING_PROVIDER=openai python scripts/run_backfill.py --commit   # 실 임베딩
```

노드 부트스트랩은 governance_events를 남기는 승인 플로우(절대 규칙 4 — `--approved-by` 필수). brightness는 건드리지 않는다 — 새 노드는 Observatory에 null(Dormant)로 보인다. 멱등 — 여러 번 돌려도 안전.

### C-4. `run_ktib_build.py` — 시험지 동결 (IMPLEMENTED)

자격: `BENCHMARK_HOLDOUT ∧ GOLD ∧ LABELED ∧ 비합성`(DB CHECK가 물리 강제). 같은 내용이면 기존 버전 재사용, extractor가 바뀌면 새 버전 강제. **자격 0건이면 EmptyKtib로 실패** — 빈 벤치마크를 0%로 보고하지 않는다. 웹 업로드 경로(B-②)가 내부적으로 같은 `build_ktib`를 호출하므로 평소엔 웹으로 충분하다.

### C-5. `run_campaign.py` — 합성 증산 (IMPLEMENTED)

```bash
python scripts/run_campaign.py                        # dry-run (n=1000)
python scripts/run_campaign.py --n 10000 --commit     # 실제 적재 (재시작 멱등)
python scripts/run_campaign.py --baseline-n 500       # 기준선 Pilot 규모 조정
```

먼저 기준선 Pilot(`--baseline-n`, 기본 200)을 돌리고, 품질 윈도(배치 `campaign.window_batches`=4개)마다 게이트 평가 — **합의도 −0.15 초과 하락 / reject율 +0.15 초과 상승 / 단가 +25% 초과 상승이면 자동 중단, exit 2**. 체크포인트: `foundry.batch_size`=50건마다 commit — 중단돼도 그때까지 적재분은 보존되고 재시작은 멱등. 실측(2026-07-17, 실 LLM): 에피소드당 약 $0.071, 약 49초/건 — 10k면 상당한 과금·시간이므로 규모·예산을 먼저 합의할 것. 산출물은 TRAIN 후보(검수 대기) — GOLD·시험지가 아니다.

**화면 변형의 원천(07-20)**: 시나리오의 workspace 변형은 하드코딩 템플릿이 아니라 **씨드 파일**(`seeds/situation_seeds_v1.yaml`)에서 나온다 — 자격 갖춘 씨드만 LLM 확장(`foundry.seed_expansion_enabled: true`, 끄면 씨드 원본만 사용·확장 비용 0), 확장 실패는 증산을 죽이지 않고 씨드 원본으로 폴백. 씨드 편집은 E-7 씨드 스튜디오.

### C-6. `run_zero_shot_baseline.py` — 기준선 측정 (IMPLEMENTED)

`run_type='zero_shot_baseline'`로 기록되어 **3D 밝기·ktib_global에 절대 반영되지 않는다**(§8-2 베이스라인 규칙). 측정하고 제안서(`--write-report` 시 docs/05-arena)를 쓸 뿐 config·문서 수치를 자동 변경하지 않는다 — 확정은 사람 승인. KTIB 없으면 exit 2. 실측 이력: claude-sonnet-5, ktib-2(185문항)에서 88.1% → 목표 96% 상향의 근거(2026-07-14).

### C-7. `cleanup_mock_bank.py` — mock 뱅크 위생 (IMPLEMENTED, 일회성)

발화가 자리표시자 패턴(`"… (변형 N)"`) ∧ 검수 대기 상태인 에피소드를 합법 전이(state_machine)로 REJECTED 처리 — 임의 UPDATE 아님, 거버넌스 벌크 이벤트 1건 기록, tier·evidence·시험지 불변. 2026-07-17 실행 완료(2,002건 정리). 재실행해도 대상이 없으면 0건으로 끝난다.

### C-8. 커버리지 추적 2종 (IMPLEMENTED, 읽기 전용)

`train_coverage.py [--json]`(의도·도메인별 훈련량 — 아무것도 생성하지 않음), `ktib_coverage.py [--json]`(의도별 시험 문항 vs 게이트 하한). 집계 로직은 대시보드와 공유(`app/observatory/aggregate.py`) — 웹 대시보드와 수치가 다르면 버그다.

---

## D. 개발자

- **서버 기동**: `.claude/launch.json` 사용 — `backend-dev`(= `cd backend && node dev-backend.mjs`, 포트 8000), `frontend-dev`(= `cd frontend && npm run dev`, 포트 5173) [근거: .claude/launch.json]. 수동은 `cd backend && uvicorn app.main:app --reload` [근거: backend/app/main.py docstring]. 프론트 미리보기는 백엔드가 늦게 떠도 자가 재연결한다(커밋 b5dd1f9).
- **테스트**: `cd backend && pytest -q`. 테스트 DB는 **`TEST_DATABASE_URL` 우선, 없으면 `DATABASE_URL`**(PostgreSQL 15+ · pgvector 필요, `[YOUR-PASSWORD]` 자리표시자가 남아 있으면 즉시 실패) [근거: backend/tests/conftest.py]. 프론트는 `cd frontend && npx vitest run`(테스트 파일 27개 · 196 테스트, 07-20 실측).
- **★ 테스트는 반드시 격리 DB로(07-20 확립)**: KTIB 뱅크가 생긴 뒤로 **활성 DB(Supabase)로 스위트를 돌리면 깨진다** — 여러 테스트의 cleanup(`DELETE FROM episodes`)이 `ktib_items` FK에 막힌다(5f+14e). 해법은 데이터 삭제가 아니라 `.env`에 `TEST_DATABASE_URL`(**프로덕션과 분리된 빈 pgvector DB** — 별도 무료 Supabase 프로젝트면 충분)을 두는 것: conftest가 자동으로 `alembic upgrade head`(pgvector 포함)까지 적용한다 [근거: .env.example 주석]. 시드 의존 테스트 5건은 2026-07-22 자가 시드로 수정됨([17장](17-open-questions-and-gaps.md) C3 해소) — 격리 DB에서 완전 녹색이 정상이다.
- **스키마 검증**: `python scripts/validate_schemas.py` — schemas/*.json + 예시 왕복 + risk model 정합(비우면 게이트가 조용히 무력화되는 `arena.critical_intents` 검사 포함) + **온톨로지↔한글 라벨(INTENT_LABEL_KO) 정합**(07-20 커밋 00db144 추가).
- **마이그레이션**: `cd backend && alembic upgrade head` (현행 최신 `0020_intent_admin`). Supabase 적용 완료(2026-07-20) — 당시 `alembic_version`에 행 2개(0017·0015)가 남아 "overlaps" 에러가 났고 `alembic stamp --purge 0017` 후 진행으로 해소(같은 증상이면 같은 처방).
- **.env 키(값 비공개)**: `DATABASE_URL` / `LLM_PROVIDER`(기본 mock) / `LLM_API_KEY` / `LLM_MODEL` / `LLM_MAX_TOKENS` / `EMBEDDING_PROVIDER`(기본 mock) / `EMBEDDING_API_KEY` / `EMBEDDING_MODEL` / `EMBEDDING_DIM`(DB vector(1536)와 일치) / `ARENA_PIN` / `CORS_ALLOW_ORIGINS` [근거: .env.example]. `ONTOLOGY_PIN`은 .env.example에 없지만 코드가 읽는다(미설정 시 ARENA_PIN→2341 폴백).
- **완료 조건(CLAUDE.md)**: 해당 티켓 테스트 + 전체 `pytest -q` + `validate_schemas.py` 통과. 숫자 임계값은 코드에 리터럴 금지 — `config/experiments.yaml`에만.

---

## E. 운영자

### E-1. 채점 실행 버튼 (Arena) — IMPLEMENTED

**목적**: 동결 시험지로 현행 뇌를 채점 — 점수(ktib_global)·노드 밝기의 유일한 갱신 경로.
**실행 방법**: 대시보드 PERFORMANCE 헤더 또는 시험지 검수 모달의 **[🎯 채점 실행]**(단일 공유 진입점) → PIN 입력(기본 `2341`, env `ARENA_PIN`) → 202 시작 → 4초 간격 상태 폴링 → 완료 시 "채점 완료 · NN.N%" + 뇌·대시보드 자동 갱신. 다른 곳에서 시작된 채점도 이어서 보인다.
**사전판정 4조건** — 하나라도 걸리면 버튼이 회색이 되고, 우회 호출도 같은 문구의 409로 막힌다 [근거: backend/app/api/arena_ops.py::_blocked_reason]:

1. mock 금지: "LLM_PROVIDER가 mock이라 채점하지 않아요 — 가짜 응답으로 매긴 점수는 무의미해서 기록을 오염시켜요. 서버 .env에 실 provider를 설정하세요."
2. 동결 시험지 존재: "동결된 시험지가 아직 없어요 — 시험지 검수에서 문항을 등록하면 채점할 수 있어요."
3. 대표 예문 > 0(0% 예정 차단): "아직 대표 예문이 0개라 지금 채점하면 전부 '모르겠음'(0%)이 나와요 — 공부 검수(2인 → GOLD)를 거치면 대표 예문이 생기고 버튼이 켜져요." (2026-07-14 실측: 2회 연속 0.0%의 재발 방지)
4. 새 유입 존재(같은 시험지·같은 뇌 재채점 방지): "지난 채점 이후 새로 배운 것이 없어요 — 점수가 그대로라 다시 잴 이유가 없어요. …"

**DB 변경**: arena_runs + reflect 경로의 노드 갱신(밝기는 이 경로만 — 절대 규칙 3). **실패 시**: 상태 폴링의 `error`로 정직 노출("채점 실패 — …") — 원인 해소 후 재실행(락은 자동 해제). 동시 실행 시 409 "이미 채점이 실행 중이에요".
**실행 전 확인**: 실 LLM 과금·수 분 소요. 시험지 버전과 문항 수(현행 ktib-3 · 386문항)를 확인.

### E-2. INSIGHT 애매 발화 카드 — IMPLEMENTED

대시보드 카드 "INSIGHT · 애매 발화 — 뇌가 헷갈린 말이 곧 현장 인사이트". 어떤 의도가 자주 애매한가(clarify권 분포, gym/live/shadow 출처 분리), 사람이 무엇을 고쳤나(교정 최근 50), 무엇이 분류 불능인가(atlas 큐). **[⬇ CSV 내려받기]** → `ambiguity_report.csv`(분포/교정/분류불능 3섹션 — 직원 공유용). 읽기 전용 — 어떤 테이블에도 쓰지 않는다. [근거: frontend/src/dashboard/AmbiguityCard.tsx, backend/app/api/observatory.py::ambiguity_report]

### E-3. 의도 목록 (카탈로그·PIN 수정·제안 승인) — IMPLEMENTED

의도 목록 패널(IntentCatalogPanel, 70개 의도):

- **이름·화면 설명 수정(표시 계층)**: 🔒 관리자 비밀번호 + 수정자 이름 입력 → 즉시 반영(governance_events 기록). 온톨로지 YAML(의미)·ontology_version은 불변.
- **일괄 수정**: **[⬇ CSV 받기]** → 엑셀에서 "이름(수정 가능)"·"화면 설명(수정 가능)"만 고침 → **[⬆ CSV로 일괄 변경]**. 목록에 없는 id는 건너뜀 — **구조 변경은 CSV로 우회 불가**.
- **새 의도·정의·이동·삭제**: **[＋ 새 의도 추가]**/제안 접수 → 대기열 → PIN으로 승인/반려. 승인 문구 그대로: "승인 완료 — 의미·구조 반영은 버전 규칙에 따라 운영 경로로 진행돼요(반영 예약)." — 승인이 곧 반영이 아니다(실반영은 §5-9 거버넌스·버전 경로, 예: `scripts/apply_ontology_examples.py --write/--register`).
- **intent_id는 어디서도 수정 불가**(시험 정답이 참조).

### E-4. 업로드 이력 열람 — IMPLEMENTED

시험지 업로드 화면 하단 **"📋 업로드 이력 (N건)"** — 등록(commit)된 것만 남는다. 항목을 펼치면 언제·누가(작성/승인/검수자)·몇 문항·어떤 시험지 버전 + **올린 원문 그대로**(CSV/YAML) 열람·회수. 원문 미보관 항목 문구: "이 업로드는 원문이 보관되지 않았어요."

### E-5. Supabase 동기화 (2대 운영) — IMPLEMENTED

`git push` 때 `.githooks/pre-push` 훅(`core.hooksPath=.githooks` 설정 확인됨)이 `scripts/sync_to_supabase.py`를 자동 실행한다(수동 실행도 가능: `python scripts/sync_to_supabase.py`, 옵션 없음). 안전 규칙 [근거: scripts/sync_to_supabase.py docstring]:

- **추가만 한다**(append-only): Supabase에 없는 PK 행만 INSERT(ON CONFLICT DO NOTHING). 원격 행 삭제 절대 없음.
- **brightness 계열(heldout_accuracy·calibration_ece·last_arena_run)은 만지지 않는다**(절대 규칙 3). 노드는 pending_evaluation·evidence_stats·exemplar_stats만 UPDATE.
- **건너뜀 규칙**: 활성 `DATABASE_URL`이 이미 Supabase면(로컬 분리 안 됨) 아무것도 하지 않고 종료. Supabase가 로컬보다 앞선 테이블은 경고만 하고 건드리지 않는다.
- URL 원천: `.env`의 `DATABASE_URL`(활성=로컬) / `#SUPABASE_DATABASE_URL`(주석으로 보존된 원격).
- 역방향(Supabase→로컬)은 `scratchpad/sync_from_supabase.py`(미커밋)로 수행해 왔다 — **저장소에 없어 본 문서에서 검증 불가(UNKNOWN)**.

### E-6. 뇌 버전 승격·반려(롤백) — PARTIAL

- **서빙 규칙**: infer의 `model_version` = brain_versions 중 **최신 promote**(없으면 `seed-v0`) [근거: backend/app/api/infer.py::_model_version]. 현재 brain_versions 0건 → seed-v0 서빙.
- **후보 빌드**: `python scripts/run_version_gate.py --commit` — 조건(new_gold ≥ `version_gate.min_new_gold` 200) 충족 시 candidate 생성. 상태는 웹 `GET /v1/observatory/version-gate`로 확인.
- **후보 판정**: `python scripts/run_arena.py --candidate --commit` — §6-6 promote 규칙(`global_up_and_no_region_regression_and_no_critical_worse`)으로 promote/reject. **promote만이 노드 밝기를 갱신**(+pending 링 소등, Full Brain Resonance). reject는 아무것도 바꾸지 않는다(brightness·pending 불변, evidence 전량 보존) — 나쁜 후보가 서빙에 오르지 못하는 구조 자체가 1차 롤백 장치다.
- **주의(영구 reject 함정)**: candidate 채점 전 반드시 `--candidate` 없이 1회 실행해 현행 base의 기준 점수를 만들 것 — 기준이 없으면 global_delta=0으로 후보가 영구 reject된다(스크립트가 경고를 출력) [근거: scripts/run_arena.py].
- **한계**: 이미 promote된 버전을 자동으로 되돌리는 전용 명령은 없다 — 사고 시 수동 DB 개입(decision 갱신)이 필요하며 절차는 미정(UNKNOWN).

### E-7. 화면 씨드 스튜디오 — IMPLEMENTED (07-20 추가)

**목적**: 합성 증산이 쓰는 화면 씨드(어떤 화면·물건·직전 행동 조합에서 발화가 나오는가)를 웹에서 작성·관리한다 — S5 변형의 유일한 원천을 사람이 소유한다.
**실행 방법**: 대시보드 EXPANSION 카드 → **[🖥 화면 씨드 스튜디오]**(SituationSeedPanel). 기능: 씨드 작성·수정·삭제(개별/CSV 일괄) · 통제 어휘(surface_types·object_kinds·actions) 관리 · **확장 미리보기**(`POST /v1/situation-seeds/expand-preview` — 실제 증산 전에 LLM 변형 결과를 눈으로 검증, dry-run) [근거: backend/app/api/situation_seeds.py 라우트 9종].
**PIN**: 다른 도구와 동일 관례 — env `SITUATION_SEED_PIN` → `ARENA_PIN` → 기본 2341. 모든 변경은 governance_events 기록.
**저장 위치**: DB가 아니라 파일(`seeds/situation_seeds_v1.yaml`) — 어휘 밖 값·vs-1.0 위반·도메인 공백은 저장 시점에 거부된다(증산이 시작되기 전에 막는 게 목적).
**실행 전 확인**: 씨드는 발화가 아니라 **화면 상태 정의**다 — 여기서 문장을 창작하지 않는다(발화 생성은 증산 파이프라인의 몫).

### 부록 — 전체 스크립트 일람 (scripts/ 21개, 팩트팩 대조 전수 + 07-20 추가분)

`apply_ontology_examples.py`(--write/--register — 예시 시트→온톨로지 반영의 유일한 문) · `apply_risk_model.py`(--approved-by/--commit — 위험 등급 개정 거버넌스) · `build_help_pdf.py`(--src/--out/--open — 도움말 PDF 인쇄) · `cleanup_mock_bank.py`(--commit) · `ingest_expert_episodes.py`(--template/--file/--commit) · `ktib_coverage.py`(--json) · `mine_atlas.py`(file/--title/--source-class/--commit — 07-20 추가) · `run_arena.py`(--commit/--candidate) · `run_backfill.py`(--commit/--approved-by) · `run_benchmark_review.py`(--queue/--apply/--write/--candidates) · `run_campaign.py`(--n/--baseline-n/--commit) · `run_fast_update.py`(--commit/--decay — 개인 prior 미세 조정+주간 decay) · `run_human_review.py`(--queue/--limit/--out/--apply/--commit) · `run_ktib_build.py`(--commit/--notes) · `run_persona_discovery.py`(--commit/--version) · `run_pilot.py`(--n/--kappa/--commit — Pilot 500) · `run_version_gate.py`(--commit) · `run_zero_shot_baseline.py`(--commit/--model/--write-report) · `sync_to_supabase.py`(옵션 없음) · `train_coverage.py`(--json) · `validate_schemas.py`(옵션 없음)

---

## 현재 상태

- 웹 도구(즉석 문답·공부 검수·시험지 1~5/O·X·의도 목록·채점 버튼·업로드 이력·INSIGHT·**씨드 스튜디오**)와 CLI 배치 전부 IMPLEMENTED. live rollout만 BLOCKED(PARTIAL HOLD — 문서 07 참조).
- 데이터 실측(2026-07-17): episodes 2,729(TRAIN 2,343 / BENCHMARK 386), GOLD 386(전부 시험지 — **TRAIN GOLD 0**), exemplars 0 → **채점 사전판정 ③에 걸려 채점 버튼은 현재 꺼진 상태가 정상**. 검수 대기 91+(증산 진행 중 증가), review_votes 10표.
- 갱신 실측(2026-07-20, Supabase — 출처 다름은 [05장](05-data-catalog.md) 5-7): episodes 3,139, **검수 대기 2,396**(증산 유입 — 병목 그대로), TRAIN GOLD·exemplar 여전히 0. 마이그레이션 0020 도달, 격리 테스트 DB 확립(위 D 참조).
- 증산 캠페인 실 LLM 가동 이력(400+340건, $0.071/건). KTIB: ktib-1(1)→ktib-2(185)→ktib-3(386, critical7×O/X 일치율 통과분 포함), 의도 커버 8/70.

## 주의사항

- **순서가 생명**: 공부 검수로 TRAIN GOLD를 만들어 exemplar가 생기기 전에는 채점해도 0%다(사전판정이 막아준다). TODO 5단계 순서대로.
- **같은 발화를 학습과 시험 양쪽에 넣지 말 것** — 서버가 409로 막지만, 애초에 출제용 발화는 훈련 화면에서 재사용하지 않는 습관이 안전하다.
- **시험지 문항은 반드시 사람이 쓴 비합성 발화** — LLM 생성 문장을 EXPERT_AUTHORED로 넣는 것은 코드가 탐지할 수 없는 유일한 구멍이다(그래서 authored_by를 거버넌스에 남긴다).
- **dry-run 결과 문구를 확인하고 --commit** — 모든 배치의 기본은 롤백이다. 특히 캠페인·zero-shot·채점은 실 provider 과금.
- PIN(2341)은 오클릭 방지일 뿐 보안이 아니다 — 외부 배포 시 env로 바꾸고, 접근 통제는 별도 수단으로.
- 검수·훈련이 아무리 쌓여도 **노드 밝기는 변하지 않는다** — 밝기가 안 오른다는 문의는 버그가 아니라 "채점 전"이라는 뜻(절대 규칙 3).

## 다음 단계

- 공부 검수(2인)로 TRAIN GOLD 축적 → backfill 자동 체인으로 exemplar 생성 → 채점 버튼 활성 → 첫 의미 있는 brain run 점수 확보(현재 0.0%의 탈출).
- 시험지 커버리지 확장: 현행 8/70 의도(CRITICAL 집중)에서 나머지 62개 의도 문항 채우기 — `ktib_coverage.py`로 갭 추적.
- new_gold 200 도달 시 version gate → candidate → `run_arena.py --candidate` 승격 사이클 첫 가동.
- 역방향 동기화 스크립트(scratchpad/sync_from_supabase.py)의 저장소 편입 여부 결정 — 현재 미커밋이라 두 대 운영 절차가 문서화되지 않은 반쪽이다.
