# Kinder Intent Lab — 이 서비스는 무엇이고, 어떤 원리로 작동하는가

> 처음 오는 사람을 위한 안내서. 설계의 **왜**와 코드의 **어디**를 잇는다.
>
> 이 문서는 요약이다. 충돌하면 **제1 설계 문서**가 이긴다:
> `docs/01-foundry/kinder-intent-foundry-growth-system-v1.0.md` (현재 v1.3)
>
> | 문서 | 무엇 |
> |---|---|
> | 여기 (`docs/00-overview`) | 전체 그림·원리·데이터 흐름·운영 |
> | `docs/01-foundry` | **제1 설계 문서** — 모든 티켓이 이 문서의 §를 참조한다 |
> | `docs/05-arena` | 문서 ③ — 위험 등급표 + Arena 지표 정의 |
> | `docs/06-runtime-integration` | Runtime Spec (PARTIAL HOLD — live 경로 미구현) |
> | `CLAUDE.md` | 절대 규칙 10개. 위반 시 어떤 티켓도 완료가 아니다 |

---

## 1. 무엇을 푸는가

유아교사는 화면 앞에서 **짧고 애매하게** 말한다.

> "이거 자연스럽게 해줘"
> "다음엔 뭘 해주면 좋을까"
> "이거 좀 치워야 하나"

같은 문장이 사진 2장을 선택한 상태면 `visual_naturalize`이고, 문단을 선택한 상태면
`text_naturalize`다. 발화만으로는 알 수 없다. 그래서 이 시스템은 네 가지를 함께 본다:

1. **발화** (`prompt.text`)
2. **화면 컨텍스트** (`workspace_context` — 무엇이 선택돼 있나, 어떤 객체가 있나)
3. **직전 행동** (`recent_actions`)
4. **교사 성향** (`teacher_context` → persona prior)

이것을 **Kinder Intent Brain**이라 부르고, 킨더버스(실서비스)와 **분리된 실험실**에서 만든다.
실서비스에 연결하는 코드는 이 저장소에 없다 (§7 참조).

**1차 목표:** KTIB(격리 벤치마크) First Intent Accuracy **80%**.

---

## 2. 왜 3D 뇌인가 — 이 프로젝트의 진짜 UX

핵심 UX는 데이터 테이블이 아니다. **3D 뇌를 돌려 어두운 노드를 클릭해 진단하고 훈련시키는 것**이다.

의도(intent) 하나 = 뇌의 노드 하나. 63개 intent가 7개 region(도메인)에 박혀 있다.
노드의 **모든 시각 속성은 실제 측정치에 묶여 있다** (설계 §7-5, 확정):

| 시각 요소 | 무엇을 뜻하나 | 어디서 오나 |
|---|---|---|
| Node **Size** | 훈련량 (evidence 총량) | `brain_nodes.evidence_stats` |
| Node **Brightness** | **Held-out 정확도 — Arena만이 바꾼다** | `brain_nodes.heldout_accuracy` |
| Node **Density** | Evidence 다양성 (섀넌 엔트로피) | `evidence_stats` 버킷 분포 |
| Node **Pulse** | 지금 추론에 개입 중 | 추론 로그 |
| **Edge Thickness** | intent 연관 강도 | `confusion_edges` |
| **Edge Flicker** | 혼동률 | `confusion_edges.confusion_rate` |
| **Pending Ring** | 훈련됨 · 검증 대기 | `brain_nodes.pending_evaluation` |

**여기가 이 프로젝트의 철학이 사는 곳이다.** 노드가 밝다는 건 "훈련을 많이 했다"가 아니라
**"격리된 벤치마크에서 실제로 맞혔다"**는 뜻이다. 훈련은 크기만 키우고, 밝기는 못 건드린다.

---

## 3. 다섯 모듈

```text
Foundry (S1~S13)  →  데이터 공장. 소스 발굴 → 시나리오 → LLM 에이전트 합의 라벨링
Seed Brain        →  추론 엔진. retrieval → LLM scorer → prior → 정규화
Gym               →  훈련장. 교사가 뇌의 오답을 교정 → evidence
Observatory       →  3D 뇌. 진단하고 클릭해서 훈련을 발주
Arena             →  유일한 심판. KTIB 벤치마크로 채점 → 밝기의 원천
```

### 3-1. Seed Brain의 추론 4단계 (`app/brain/inference.py`)

```text
[1] RETRIEVAL   발화 임베딩 ↔ 노드 exemplar 최근접(pgvector) + Atlas 매치 → 후보 ≤ 20
[2] LLM SCORER  후보 + 화면 컨텍스트 → 후보별 activation 0~1
[3] PRIOR       activation × persona_prior × domain_prior   ← LLM **밖에서** 곱한다
[4] 정규화       → 후보 목록 + confidence + margin(top1−top2)
```

**[3]이 LLM 밖에 있는 것은 의도적이다** (설계 §5-5). 이유 셋:

1. **Persona Lift/Harm을 측정할 수 있다** — prior 없이 재정렬해 비교하면 된다. LLM을 다시
   부를 필요도 없다.
2. **cap과 롤백이 가능하다** — `brain.persona_prior_cap`(0.20)이 prior가 점수를 지배하지 못하게 막는다.
3. **프롬프트에 persona를 넣으면 통제 불능이 된다.**

그 다음 `app/brain/decision.py`가 정책을 고른다: `abstain`(너무 약함) → `clarify`(모호, 상위 2개
제시) → `suggest`(확신). 임계값은 전부 `config.decision.*`.

### 3-2. Growth Loop — "강화한다"의 정의

**교정 20개가 들어오면 정확도가 올라간 것인가? 아니다** (설계 §6-5).

교정은 evidence 축적이다. 즉시 변하는 것은 size·density·evidence 카운트뿐이고,
**밝기는 변하지 않으며 노드에 `pending_evaluation` 링이 켜진다** — "훈련됨, 검증 대기".

밝기가 바뀌려면 Arena를 통과해야 한다.

---

## 4. End-to-End Trace — 어두운 점 하나를 클릭하면 무슨 일이 일어나는가

설계 §6-7이자 이 시스템의 나침반. `backend/tests/test_e2e_trace_0_to_9.py`가 이 체인 전체를
무중단으로 통과시킨다.

```text
[0] 관찰      3D 뇌에서 play_expand 노드가 어둡다 (brightness 25% = Arena run의 heldout)
[1] 클릭      진단 엔진(§7-3) 4축 실행:
              CONFUSION_HIGH (→other 75%, edge confirmed) + GOLD_LOW (학습 GOLD 1건)
[2] 전략      진단 → 강화 유형(§6-1) → C(Confusion) + B(Human Evidence)
              → Challenge Pack 생성: contrast 문항 + persona mix + 배달 모드
[3] 출제      Gym trainer 큐로 발행
[4] 상호작용  세션 산출 → evidence 적재 (HUMAN_CORRECTION / HUMAN_CONFIRMATION)
[5] 집계      Label Aggregator(§3-6): 1인 신호는 축적 유지, 2인 일치 → SILVER
              그 다음 **사람 2인 검수** → LABELED + GOLD  (§3-3, 자동 루프 밖)
[6] 즉시반영  size↑ density↑ + pending 링 점등.  ★ brightness는 그대로 어둡다
[7] 후보      Version Gate(§6-6): 누적 new_gold ≥ 임계 → candidate v1-rc1 빌드
[8] 시험      Arena 전체 실행: KTIB 재평가. replay 4버전 기록
[9] 판정      promote 규칙 = global 상승 ∧ region 회귀 없음 ∧ critical 악화 없음
              PASS → 밝기 25%→100%, flicker 75%→0%, pending 소등, Full Brain Resonance 1회
              FAIL → reject: evidence 전량 보존, 회귀 리포트, candidate 폐기
```

> **이 체인의 어느 단계도 건너뛸 수 없다.**
> 특히 [4]→[6]에서 밝기가 바로 오르는 지름길은 **구조적으로** 존재하지 않는다.

---

## 5. 정보의 종류와 그것을 지키는 규칙

이 시스템의 거의 모든 복잡도는 **"이 숫자는 무엇에서 왔는가"**를 잃지 않으려는 데서 나온다.

### 5-1. Episode — 최소 관측 단위

한 건의 (발화 + 컨텍스트 + 라벨). `episodes` 테이블. **네 개의 독립 축**이 붙는다:

| 축 | 값 | 뜻 |
|---|---|---|
| `dataset_split` | TRAIN / VALIDATION / TEST / **BENCHMARK_HOLDOUT** | 어디에 쓰나 |
| `reliability_tier` | UNVERIFIED / BRONZE / SILVER / **GOLD** | 라벨 **품질** |
| `label_state` | UNLABELED → … → LABELED / REJECTED | 워크플로 **상태** |
| `origin_channel` | FOUNDRY_SYNTHETIC / GYM_HUMAN / **EXPERT_AUTHORED** / … | **출생** |

**tier와 state를 섞지 않는다**(절대 규칙 8). "품질이 좋다"와 "작업이 끝났다"는 다른 말이다.
**출생을 tier에 섞지도 않는다** — 그래서 tier에 `SYNTHETIC`이 없다.

### 5-2. Evidence — 최소 학습 단위

라벨은 하나의 값이 아니라 **신호들의 집계**다. `evidence` 한 행 = 신호 하나.
`evidence_type`(SYNTHETIC_CONSENSUS / HUMAN_CORRECTION / EXPERT_REVIEW / …) +
`actor_type`(누가) + `adversarial`(스트레스 테스트인가).

`app/aggregator/`가 이 신호들을 모아 상태 기계를 전이시킨다. **하지만 GOLD는 절대 안 만든다.**

### 5-3. GOLD는 오직 사람이 만든다

```text
Aggregator (§3-6)          → 최대 SILVER
Gym / Foundry / Arena      → GOLD 경로 없음
app/aggregator/review.py   → 여기가 유일한 문
```

`review.py`의 규칙 (§3-3 "인간 검수 2인 이상 일치, kappa 기록"):

- 서로 다른 검수자 2명 이상 ∧ **만장일치**여야 확정. 1인이거나 불일치면 **상태 불변**
  (다수결로 밀어붙이지 않는다)
- 검수자 신원은 **정규화**해서 센다 — `"alice"`와 `"alice "`, `"Alice"`는 한 사람이다
- 배치 전체의 Cohen's kappa < 0.65면 **배치 전량 거부**. 반올림 전 원값으로 비교한다
- 모든 라벨이 같아 kappa를 계산할 수 없으면(변별력 0) **거부** — 완전 일치를 1.0으로 치지 않는다

### 5-4. KTIB — 유일한 심판, 그리고 그것을 지키는 벽

```sql
-- db/migrations/001_init.sql, 절대 규칙 2
CHECK (dataset_split <> 'BENCHMARK_HOLDOUT'
       OR (reliability_tier = 'GOLD'
           AND label_state = 'LABELED'
           AND origin_channel NOT IN ('FOUNDRY_SYNTHETIC','FOUNDRY_AUGMENTED')))
```

**합성 데이터는 벤치마크에 물리적으로 들어갈 수 없다.** DB가 막는다.
그래서 KTIB에 넣는 경로도 하나뿐이다 — `app/foundry/expert_ingest.py`.

KTIB는 **동결**된다. 채택 시점의 발화·정답·화면 스냅샷을 `ktib_items`에 복사하고,
`content_hash = sha256(에피소드 집합 ⊕ extractor 지문)`이 UNIQUE다.

- 같은 내용 재빌드 → 같은 `ktib_version` (멱등)
- **extractor를 올려 재추출 → 새 `ktib_version` 강제.** 신·구 벤치마크 점수를 같은 축에 그리지 않는다
- 발급된 스냅샷 수정은 flush 리스너가 차단(`KtibFrozen`)

그리고 **학습 파이프라인은 KTIB를 읽을 수 없다.** `app/core/datasets.py::training_gold()`가
exemplar 선정·노드 통계·진단·Version Gate 네 곳 모두에서 벤치마크를 뺀다.
(이 누수는 실제로 있었고, Phase 5에서 잡아 고쳤다.)

### 5-5. replay 무결성 — 점수를 믿을 수 있게 하는 4개의 축

모든 `arena_runs`는 넷을 기록한다. 넷이 같으면 같은 실험이고, 결과는 재현되어야 한다.

| 축 | 왜 |
|---|---|
| `model_version` | 어느 뇌를 쟀나 |
| `ontology_version` | 어떤 intent 집합으로 쟀나 |
| `persona_state_version` | 어떤 prior로 쟀나 |
| `extractor_versions` | 화면을 어떤 추출기로 읽었나 |

> "Brain이 좋아진 것인지 Extractor가 좋아진 것인지 귀속을 분리할 수 없으면
> 그 점수는 신뢰할 수 없다." (§8-2)

같은 이유로 **게이트 지표는 run 시점에 계산해 `arena_runs.metrics`에 동결**하고, 게이트는
저장값만 읽는다. 게이트 시점에 다시 계산하면 config를 고치는 것만으로 과거 판정이 바뀐다.

---

## 6. Arena — 유일한 심판

`app/arena/`. 실행 시점: 주간 정기 + Version Gate 시.

### 6-1. 산출 지표

| 지표 | 정의 |
|---|---|
| **First Intent Accuracy** | top-1 == 정답. global / region / node 3층. **순수 argmax** |
| **방향성 Confusion Matrix** | `P(예측=B \| 정답=A) ≠ P(예측=A \| 정답=B)` |
| **Calibration (ECE)** | 신뢰도 버킷의 \|정확도 − 신뢰도\| 가중평균 |
| **1-Turn Recovery** | clarify한 것 중 정답이 제시된 top-2에 있던 비율 |
| **Persona Lift / Harm** | prior 덕에 맞춘 / prior 탓에 틀린 비율 (LLM 재호출 0) |
| **CWAR-fire** | `P(오발 \| critical 행동을 커밋함)` |
| **CWAR-miss** | `P(인식 실패 \| 정답이 critical)` |
| **CCC** | critical 정답 중 실제로 커밋한 비율 |

**왜 CWAR가 양방향인가.** fire 방향만 재면 "마스킹을 원했는데 crop으로 오인식 → 아동 얼굴이
그대로 노출"이라는 실패를 **구조적으로 볼 수 없다.** 그건 miss 방향만이 잡는다.
그리고 어려운 critical만 clarify로 흘려 fire를 0으로 만드는 회피는 **CCC**가 닫는다.
세 지표가 정밀도·재현율·커밋률로 서로를 덮는다.

### 6-2. Risk Model rm-1.0 — 무엇이 critical인가

`seeds/risk_model_v1.yaml`. 축 셋:

- **E** 비가역 외부 유출 (아동 데이터가 교실 밖으로, 회수 불가)
- **D** 비가역 데이터 파괴
- **R** 공식·법적 등록부 오기재

핵심 원칙: **egress(유출) 경계에서 게이트하고, 그 하위 egress를 통해서만 피해가 실현되는
내부 변이는 이중 게이트하지 않는다.** 이중 게이트는 CWAR를 희석시킨다.

CRITICAL 7종: `comm_message_individual_parent` · `comm_share_media_with_parents` ·
`comm_request_consent` · `comm_schedule_send` · `op_notice_send` · `op_attendance_record` ·
`op_workspace_delete`

> 위험 등급은 intent의 *의미*가 아니라 *평가 정책*이다. 그래서 **온톨로지에 넣지 않는다** —
> 넣으면 등급을 고칠 때마다 `ontology_version`(replay 축)이 흔들려 과거 run과 비교할 수 없다.

### 6-3. 정직성의 비대칭 (`app/arena/gate.py`)

- 능력 지표가 **미측정이면 FAIL**. 측정하지 못한 능력은 능력이 아니다.
- critical 정답이 존재하는데 안전 지표가 null이면 **FAIL**. 측정하지 못한 안전은 안전이 아니다.
- critical 정답 표면 자체가 없으면 **N/A + 큰 경고**. 조용히 통과시키지 않는다.
- 품질 지표는 측정 대상이 없으면 WAIVE.
- **어느 경우에도 null을 0%나 100%로 렌더하지 않는다.**

---

## 7. 하지 않는 것 (경계)

- **킨더버스 live rollout 서빙 코드를 만들지 않는다.** `docs/06-runtime-integration`은 PARTIAL HOLD.
  `app/arena/gate.py`는 §10-2 준비도 **리포트**일 뿐 어떤 경로도 켜지 않는다.
- **`brain_nodes`를 자동 생성하지 않는다.** 노드 생성은 `governance_events`를 남기는 승인 플로우로만.
- **훈련 메타데이터(정답·scenario_id·target_confusion)를 Brain 추론 입력에 넣지 않는다.**
  `mode=gym`이어도 scorer는 Core 신호만 받는다.
- **`adversarial=true` evidence를 자연 분포 학습·집계에 섞지 않는다.**
- **발화를 생성해 벤치마크에 넣지 않는다.** LLM이 쓴 문장을 `EXPERT_AUTHORED`로 찍으면
  Arena 점수는 뇌가 자기가 만든 문장을 얼마나 외웠는지의 측정치가 된다.
  코드는 이걸 탐지할 수 없어서 `authored_by`를 필수로 받아 거버넌스에만 남긴다.

---

## 8. 코드 지도

```text
backend/app/
  core/      config(experiments.yaml 단일 접근점) · ontology · datasets(벤치마크 격리) · risk_model
  contracts/ pydantic — schemas/*.json에서 파생, 왕복 테스트로 고정
  models/    SQLAlchemy 27테이블 + guards(밝기·GOLD·KTIB 동결 flush 리스너)
  foundry/   S1~S13 데이터 공장 · persona(클러스터링) · expert_ingest(KTIB 유일 입구)
  brain/     inference(4단계) · decision · priors · diagnosis · promote · version_gate
  aggregator/ state_machine(§3-6) · aggregator(≤SILVER) · review(GOLD 유일 경로)
  gym/       challenge_pack · session · growth
  arena/     ktib · runner · metrics · persona · reflect · stages · gate · baseline
  api/       infer · gym · observatory
frontend/src/brain3d/   R3F 3D 뇌 (instanced mesh, 2D fallback)
config/experiments.yaml ★ 모든 숫자 임계값이 사는 유일한 곳
seeds/                  ontology_v1.yaml · risk_model_v1.yaml
db/migrations/          0001~0014
```

### 절대 규칙 10개 (`CLAUDE.md`) — 위반 시 어떤 티켓도 완료가 아니다

1. 숫자 임계값은 `config/experiments.yaml`에만. 코드에 리터럴 금지
2. `BENCHMARK_HOLDOUT ⇒ GOLD ∧ LABELED ∧ 비합성` — DB CHECK. 우회 금지
3. **노드 brightness는 Arena 결과만 갱신한다.** 훈련 코드는 size/density/pending만
4. `brain_nodes` 자동 INSERT 금지 — 거버넌스 승인 플로우로만
5. 훈련 메타데이터를 Brain 추론 입력(Core)에 넣지 않는다
6. `adversarial=true`는 자연 분포 학습·집계에서 분리
7. TRANSFORM_ONLY 소스의 원문 저장 금지
8. `label_state`(상태)와 `reliability_tier`(품질)를 혼용하지 않는다
9. provenance 4필드 — 생성 주체를 evidence에서 역추론 금지
10. `evidence_type` 고정 서열 금지 — 가중치는 config

규칙 3은 코드로 강제된다: `models/guards.py::arena_brightness_write` 컨텍스트 밖에서
`heldout_accuracy`를 대입하면 flush가 `BrightnessWriteBlocked`로 실패한다.

---

## 9. 지금 어디까지 와 있나

**Phase 1~5 코드 완료.** backend 639 테스트, frontend 80 테스트, ruff·schema 검증 통과.
§6-7 E2E 체인이 자동 테스트로 무중단 통과한다.

**그러나 실 데이터로는 한 번도 흐른 적이 없다.**

| 테이블 | 현재 |
|---|---:|
| KTIB 자격 에피소드 | 0 |
| GOLD 에피소드 | 0 |
| exemplar | 0 |
| gym_sessions | 0 |
| persona_clusters | 0 |
| arena_runs | 0 |

에피소드 2,200건은 전부 TRAIN + 합성 + 비GOLD다. 남은 것은 코드가 아니라 **사람**이다.

### 운영 절차

```bash
# 0) 위험 등급 승인 (완료: GOV_RM_rm-1_0)
python scripts/apply_risk_model.py --approved-by "이름" --commit

# 1) 학습 GOLD 만들기 → exemplar 해금  (합성분도 가능. 단 KTIB엔 영원히 못 감)
python scripts/run_human_review.py --queue --limit 50 --out review_queue.yaml
#    → 서로 다른 사람 2명이 각자 chosen_intent를 채우고 votes를 합친다
python scripts/run_human_review.py --apply review_queue.yaml --commit

# 2) KTIB 만들기  ★ 발화는 사람이 쓴다. LLM 생성물 금지
python scripts/ingest_expert_episodes.py --template ktib_seed.yaml
python scripts/ingest_expert_episodes.py --file ktib_seed.yaml --commit
python scripts/run_ktib_build.py --commit

# 3) zero-shot 베이스라인 → 그 위에서 80% 목표의 난이도를 재확정 (§8-2)
python scripts/run_zero_shot_baseline.py --commit --write-report

# 4) 현행 뇌의 기준 점수 → 그 다음에야 candidate 판정이 가능하다
python scripts/run_arena.py --commit
python scripts/run_version_gate.py --commit
python scripts/run_arena.py --candidate --commit

# 5) persona (실제 트레이너가 Gym을 플레이한 뒤)
python scripts/run_persona_discovery.py --commit
```

모든 스크립트는 **기본이 dry-run + 롤백**이다. `--commit`을 붙여야 쓴다.
그리고 실패할 때는 조용히 0을 반환하지 않고 **loud-fail한다** — 빈 벤치마크는 정확도 0%가 아니라
`EmptyKtib`이고, 클러스터가 없으면 없는 성향을 지어내는 대신 exit 2다.

### 게이트가 열리는 조건

`gate.critical_surface_min_items = 30` — CRITICAL 7종이 정답인 벤치마크 아이템이 최소 30건
있어야 안전 레그가 N/A를 벗어난다. 그전까지 §10-2 게이트는 **통과할 수 없다.** 의도된 보수성이다.

---

## 10. 이 프로젝트를 읽는 한 줄

> **측정하지 않은 것을 측정한 것처럼 보이게 하지 않는다.**

미측정은 0%가 아니다(`null`). 훈련은 밝기가 아니다(`pending` 링). 합성은 벤치마크가 아니다
(DB CHECK). 별칭 두 개는 두 사람이 아니다(정규화). 완전 일치는 검증이 아니다(kappa 계산 불가면 거부).
안전을 재지 못했으면 안전한 게 아니다(FAIL).

이 문장들의 목록이 곧 이 저장소의 아키텍처다.
