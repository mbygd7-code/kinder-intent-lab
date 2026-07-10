# Arena / KTIB — 지표 정의 (문서 ③, 진행 중)

> 제1 설계 문서: `docs/01-foundry/kinder-intent-foundry-growth-system-v1.0.md` §8-2.
> 충돌 시 제1 설계 문서가 이긴다. 이 문서는 **구현된 것만** 정의한다.

## Change Log

| 날짜 | 변경 |
|---|---|
| 2026-07-10 | 최초 작성 — Phase 5(T5.1~T5.2)에서 구현된 지표만 기술 |
| 2026-07-10 | §6 추가 — Arena→Observatory 반영, 밝기 가드, §7-6 스테이지 해석 2건, Persona Overlay |
| 2026-07-10 | **4결정 확정 (사용자 승인, 설계 문서 v1.3).** §6 해석 2건 폐합(사다리 highest-satisfied-wins 확정, Stage 4 = Semantic Cross-Region Flow 정의). §7 신설 — Risk Model rm-1.0(축 E/D/R, CRITICAL 7종, 온톨로지 밖 저장 근거, validate_schemas drift 차단, 거버넌스 이벤트). 기존 §7 TBD 3종을 §8 확정 정의로 승격 — 1-Turn Recovery, Persona Lift/Harm(LLM 0회·run-stamped state_version·비활성화는 제안만), CWAR 양방향(fire+miss) + Critical Commit Coverage. §9 신설 — Phase 5/Live-rollout 준비 게이트 4레그 + null 정직성 비대칭. §8 공백(critical_intents 빈 목록) 폐합. §10-1에 절대 규칙 6 adversarial 가드 명시 |

---

## 1. KTIB란 무엇인가

`dataset_split=BENCHMARK_HOLDOUT ∧ reliability_tier=GOLD ∧ label_state=LABELED
∧ origin_channel ∉ {FOUNDRY_SYNTHETIC, FOUNDRY_AUGMENTED}`를 만족하는 에피소드만으로 구성된
격리 벤치마크. 학습 파이프라인은 접근할 수 없다.

- 자격의 **물리적 강제**: `episodes.benchmark_integrity` CHECK (마이그레이션 0001, 절대 규칙 2)
- 구성기: `app/arena/ktib.py` → `ktib_versions` / `ktib_items`
- **동결**: 채택 시점의 발화·gold intent·workspace(`visual_semantics` 포함)를 `ktib_items`에 복사

### ktib_version 동일성

`content_hash = sha256(에피소드 집합 ⊕ extractor 지문)`이 UNIQUE다.

- 같은 내용 재빌드 → 같은 `ktib_version` (멱등)
- **extractor를 올려 재추출 → 해시가 달라져 새 `ktib_version` 강제** (§8-2)
- 기존 버전의 스냅샷 수정은 `config.visual_semantics.ktib_extractor_pinned`가 켜진 동안
  flush 리스너(`KtibFrozen`)가 차단한다

> 신·구 KTIB 점수를 같은 축에 그리지 않는다. `ktib_version`이 다르면 다른 벤치마크다.

## 2. replay 무결성 4종

모든 `arena_runs`는 다음 넷을 기록한다. 넷이 같으면 같은 실험이고, 결과는 재현되어야 한다.

| 축 | 컬럼 | 출처 |
|---|---|---|
| model_version | `arena_runs.model_version` | brain 버전(`brain_versions.version`) 또는 `zero_shot:<model>` |
| ontology_version | `arena_runs.ontology_version` | `seeds/ontology_v1.yaml` |
| persona_state_version | `arena_runs.persona_state_version` | `persona_state_versions` (zero-shot은 `none`) |
| extractor_versions | `arena_runs.extractor_versions` | KTIB가 동결한 지문 (`ktib_versions.extractor_versions`) |

> "Brain이 좋아진 것인지 Extractor가 좋아진 것인지 귀속을 분리할 수 없으면 그 점수는
> 신뢰할 수 없다." (§8-2)

## 3. run_type — 밝기의 원천 분리

| run_type | 의미 | 3D 밝기 갱신 |
|---|---|---|
| `brain` | Seed Brain 추론 파이프라인 평가 | **예 — 유일한 원천** |
| `zero_shot_baseline` | 범용 LLM zero-shot 베이스라인 | 아니오 |

`GET /v1/observatory/brain`의 `ktib_global`, `brain_nodes.heldout_accuracy`는 `brain` run만
읽는다 (절대 규칙 3 / 원칙 8).

## 4. 구현된 지표

`app/arena/metrics.py` — DB를 모르는 순수 계산.

### 4-1. First Intent Accuracy

top-1 예측이 gold intent와 정확히 일치한 비율. global / region / node 3층. **순수 argmax다.**

**abstain은 두 종류이고, 섞으면 지표가 거짓말한다:**

| 종류 | 표현 | 의미 | accuracy | abstain_count | CWAR-miss | CCC |
|---|---|---|---|---|---|---|
| no-candidate | `predicted_intent = None` | 후보를 못 냄(OOD·계약위반) = **인식 실패** | 오답 | 센다 | miss | 미커밋 |
| decision | `decision='abstain'`, pred 있음 | argmax는 맞혔지만 강도가 낮아 **행동 안 함** | 그대로 | 안 센다 | miss 아님 | **미커밋** |

- **`first_intent_accuracy`가 decision과 무관한 것은 의도적이다.** 그러지 않으면
  `config.decision.abstain_score`를 만지는 것만으로 노드 밝기(heldout)가 조용히 바뀌고, decision
  엔진을 돌리지 않는 zero-shot 베이스라인과 비교할 수 없게 된다(§8-2 베이스라인 규칙).
- decision 분포는 `metrics["decisions"] = {suggest, clarify, abstain}`으로 **따로 드러낸다** —
  "argmax는 맞혔지만 겁이 나서 행동하지 않은" 브레인을 숨기지 않는다.
- **측정되지 않은 노드는 `by_node`에 나타나지 않는다** — 미측정(§7-6 Stage 0 Dormant)과
  정확도 0%는 다른 값이다. 0으로 채워 넣지 않는다.
- 표본이 0이면 지표는 `null`이다.

### 4-2. 방향성 Confusion Matrix (§5-6)

`confusion_rate(A→B) = P(예측=B | 정답=A) = count(true=A, pred=B) / n(true=A)`

- 방향성이다: `P(예측=B|정답=A) ≠ P(예측=A|정답=B)`. 두 방향은 별개 행이고 분모가 다르다.
- 분모 `n(true=A)`에는 abstain도 포함된다(정답 A의 전체 표본). 그러나 abstain은 "다른 intent와
  혼동한 것"이 아니므로 **pair를 만들지 않는다**.
- `count ≥ config.arena.confusion_confirm_min`인 pair만 `confirmed`로 표시한다.
  이것이 `confusion_edges.state`를 `observed` → `confirmed`로 올리는 근거다(§5-6 상태 기계).

### 4-3. Calibration (ECE)

등간격 신뢰도 버킷(`config.arena.ece_bins`)의 표본수 가중 |정확도 − 신뢰도|:

```
ECE = Σ_b (n_b / N) · |acc_b − conf_b|
```

global과 node별로 계산한다.

## 5. Zero-shot 베이스라인 규칙 (§8-2)

> "첫 KTIB 완성 직후 범용 LLM zero-shot 베이스라인을 측정하고, 그 위에서 80% 목표의 난이도를
> 재확정한다. **목표 수치를 베이스라인보다 먼저 확정하지 않는다.**"

`app/arena/baseline.py`. zero-shot 러너는 이 시스템이 만든 어떤 것도 보지 않는다:

- retrieval·exemplar 없음 (훈련 산출물)
- persona/domain prior 없음 (§5-5의 곱셈 단계를 건너뛴다)
- 입력 = 온톨로지 intent 카탈로그(id + 정의) + 동결된 KTIB 스냅샷(발화·workspace)뿐

리포트(`scripts/run_zero_shot_baseline.py --write-report`)는 노드/도메인별 분해와
**목표 재확정 제안서**를 담는다. 제안서는 측정값에서 유도한 사실(절대 격차, 상대 오류 감소율)만
제시하고 **새 목표 수치를 확정하지 않는다** — 확정은 사람 승인 + 설계 문서 Change Log 소관이다.

## 6. Arena → Observatory 반영 (§7-5·§7-6)

`app/arena/reflect.py`. **Arena 결과만이** 3D 뇌의 밝기와 edge flicker를 바꾼다.

| 시각 요소 | 저장 위치 | 누가 쓰는가 |
|---|---|---|
| Node Brightness | `brain_nodes.heldout_accuracy` | 반영 잡 (아래 규칙) |
| Edge Flicker | `confusion_edges.confusion_rate` | 모든 `brain` run (`runner.apply_confusion_edges`) |
| Pending Ring | `brain_nodes.pending_evaluation` | 훈련이 점등, **promote만** 소등 (§6-7 [6]→[9]) |

### 밝기는 "현행 뇌"의 heldout이다

`arena_runs.model_version`이 **어떤 뇌를 쟀는지** 말해준다. 밝기는 그 귀속을 따른다:

| run이 잰 대상 | 밝기 | pending 링 |
|---|---|---|
| 현행 base 버전 (주간 정기 실행) | 갱신 | **건드리지 않음** — 이 run은 candidate의 훈련을 검증한 적이 없다 |
| candidate → promote | 갱신 (`resolve_candidate`) | 소등 + Full Brain Resonance (§6-7 [9]) |
| candidate → reject | 불변 (숫자 폐기) | 불변 (§6-6) |
| `zero_shot_baseline` | 반영 불가 (`BaselineRunNotReflectable`) | — |

> 이 규칙이 §7-6 Stage 1(Spark = "측정 1회 이상")을 가능하게 한다. 밝기를 promote에서만 켜면
> 첫 promote 이전의 뇌는 영원히 Stage 0에 머물러 §7-6 표와 모순된다.
> 훈련이 밝기를 올리는 지름길은 여전히 어느 경로에도 없다(§6-7 [4]→[6]).

### 강제 수단 (절대 규칙 3)

`models.guards.arena_brightness_write(run_id)` 컨텍스트 + `before_flush` 리스너:

- 컨텍스트 **밖**에서 `heldout_accuracy` / `calibration_ece` / `last_arena_run`을 ORM 대입하면
  `BrightnessWriteBlocked`로 flush가 실패한다. 훈련(`gym.growth`)·교정(`fast_update`)·
  `backfill`은 size/density/pending만 만지므로 영향이 없다.
- 컨텍스트 **안**에서도 노드의 `last_arena_run`이 반영 중인 run_id와 같아야 한다.
  어느 run이 그 밝기를 만들었는지 귀속되지 않는 값은 §8-2 replay 무결성에서 의미가 없다.
- 한계: statement 레벨 쓰기(`session.execute(update(...))`)는 이 리스너를 우회한다.
  `promote_tier()`와 동일한 계약 — 밝기를 쓰는 코드는 반드시 이 컨텍스트를 경유한다.

### 성장 스테이지 (§7-6) — 2026-07-10 확정

`app/arena/stages.py`. 두 해석이 사용자 승인으로 확정됐다(설계 문서 v1.3 Change Log).

**① Stage 사다리 = highest-satisfied-wins (확정).** §7-6의 Stage 1~3 기준은 서로 배타적이지
않다(측정 비율 40% + reliability 60%는 어느 줄에도 없다). 높은 단계부터 검사해 **처음 만족하는
값**을 쓴다:

```
3 if reliability ≥ stages.region_online_reliability
2 if measured/node_count ≥ stages.cluster_awake_measured_ratio
1 if measured ≥ 1
0 otherwise (Dormant)
```

Stage 1의 `reliability < 50%`는 임계값이 아니라 사다리 폴백의 *서술*이다 — 그 이름의 config
키는 존재하지 않는다. `reliability`는 **측정된 노드만** 평균낸다(미측정은 0%가 아니다).

**② Stage 4 = Semantic Cross-Region Flow (확정 — 재정의).** "인접 region"은 설계 어디에도
정의된 적이 없고, 공간/온톨로지 인접 그래프를 발명하지 않는다(CLAUDE.md). Arena가 실측하는
유일한 인접 신호는 **cross-region confusion**이다.

- **인접:** region A의 intent와 region B의 intent 사이에 `state='confirmed'`인 방향성 confusion
  edge가 있으면 A·B는 의미적으로 인접하다. `hypothesized`/`observed`는 다리를 놓지 않는다
  (순간 잡음이 인접을 지어내지 못하게).
- **★ 인접은 rate가 아니라 state로 판정한다.** `apply_confusion_edges`는 state를 절대 낮추지
  않고(단조) 혼동이 사라지면 `confusion_rate=0.0`으로만 소등한다. 그래서 **혼동이 줄어 목표를
  달성해도 인접이 사라지지 않는다.** rate를 인접 기준으로 삼으면 Stage 4는 도달하는 순간
  스스로를 지운다(설계 검토에서 발견된 자기소멸 결함).
- **감소 추세:** 동일 `ktib_version`의 최근 `stages.cross_region_trend_window`개 brain run
  윈도에서, **윈도 시작 run에 스냅샷된** 주요 다리(그 run의 `rate ≥
  stages.cross_region_major_edge_min`)의 평균 `confusion_rate`가
  `stages.cross_region_trend_min_drop` 이상 순감소.
- **두 인접 region 모두** `reliability ≥ stages.region_online_reliability`.
- **미측정 ≠ 미충족:** 윈도가 W개에 못 미치면 추세는 NULL → Stage 4 미방출.
- Stage 4는 **읽기 시점 VIEW**다. `arena_runs`에 저장하지 않는다 — run 이력에 의존하므로
  얼려두면 replay가 깨진다. 게이트 입력도 아니다.

Stage 5(global ≥ 목표)는 `config.arena.first_intent_accuracy_target`을 재사용한다 —
KTIB 목표가 두 곳에 따로 있으면 안 된다. `brain_stage`는 `5 → 4 → region 최고 단계` 순으로
검사한다(같은 highest-satisfied-wins).

### Persona Overlay

`GET /v1/observatory/persona-overlay`. 원천은 `population_priors`(현재 `state_version`) —
§5-5에서 **LLM 밖에서 activation에 곱해지는 배수**다. 측정된 클러스터별 정확도가 아니다.
클러스터가 없으면 빈 목록을 돌려준다(분포를 지어내지 않는다).

## 7. Risk Model rm-1.0 — evaluation_critical (2026-07-10 확정)

`seeds/risk_model_v1.yaml` + `app/core/risk_model.py`. 설계 문서 헤더가 예고한 "문서 ③ 위험
등급표"가 이것이다.

**위험 판정 기준:** "top-1 오예측이 실행됐을 때, 그 피해가 심각하고 **다른 어떤 게이트도 그것을
막지 못하는가**". 핵심 원칙은 **egress(유출) 경계에서 게이트하고, 그 하위 egress를 통해서만
비가역 피해가 실현되는 내부 변이는 이중 게이트하지 않는다** — 이중 게이트는 CWAR를 희석시킨다.

| 축 | 질문 |
|---|---|
| **E** | 오예측 실행이 아동 데이터·이미지를 교실 신뢰경계 밖으로 되돌릴 수 없이 내보내는가? |
| **D** | 오예측 실행이 데이터를 파괴하며 하위 어떤 경계에서도 복구되지 않는가? |
| **R** | 오예측이 공식·법적 등록부를 잘못 기록하고, 그 오기재 자체가 게이트 없이 외부 결과를 낳는가? |

`evaluation_critical(intent) ⟺ tier == CRITICAL ⟺ (E ∨ D ∨ R)`

**CRITICAL 7종:** `comm_message_individual_parent`(E) · `comm_share_media_with_parents`(E) ·
`comm_request_consent`(E) · `comm_schedule_send`(E) · `op_notice_send`(E) ·
`op_attendance_record`(R) · `op_workspace_delete`(D)

**주요 등급 결정 (감사 채택):**

- `obs_tag_children` → **ELEVATED**. 내부 신원 결합이며 재태깅 가능하다. 비가역·유출 피해는 이미
  CRITICAL인 `share_media`/`document_export`를 통해서만 실현되므로 egress에서 게이트한다.
- `comm_schedule_send` → **CRITICAL로 승격**. 발화 시점에 사람이 개입하지 않은 채 학부모 발송이
  큐잉된다 — 취소창을 놓치기 쉬워 즉시 발송보다 위험하다.
- `visual_privacy_mask` → **STANDARD**. 위험 방향은 "마스킹을 원했는데 crop으로 오인식 → 아동
  얼굴 노출"이고, 이것은 **fire 방향 CWAR로는 구조적으로 볼 수 없다**. 그래서 CWAR를 양방향으로
  정의했고 이 실패는 **CWAR-miss**가 잡는다.

`ELEVATED`는 UX/telemetry 티어일 뿐이며 **CWAR·게이트에 들어가지 않는다.**

### 저장 위치 — 온톨로지가 아닌 이유

위험 등급은 intent의 *의미*가 아니라 *평가 정책*이다. 의미 구조의 권한은 온톨로지에만 있고(§5-9),
`arena_runs.ontology_version`은 replay 무결성 축이다(§8-2). 등급을 온톨로지에 두면 등급을 고칠
때마다 `ontology_version`이 올라가고, intent 집합·정의가 하나도 안 바뀌었는데도 과거 모든 arena
run이 "다른 온톨로지"가 되어 같은 축에서 비교할 수 없게 된다. (실제로 `OntologyIntent`는
`extra="forbid"`라 risk 필드를 받지도 않는다.)

- **소비:** `config/experiments.yaml`의 `arena.critical_intents`
- **저작·감사:** `seeds/risk_model_v1.yaml`
- **drift 차단:** `scripts/validate_schemas.py`가 둘의 CRITICAL 집합이 어긋나면 loud-fail한다.
  config만 비워 §6-6 critical 절과 CWAR를 **조용히** 무력화하는 경로를 물리적으로 막는다.
- **거버넌스:** `scripts/apply_risk_model.py`가 `RISK_MODEL_UPDATE` 이벤트를 남긴다. 최초 지정은
  promote 거동을 바꾼다(이전에 통과하던 candidate가 critical 회귀로 새로 차단될 수 있다 — 의도된
  안전 강화). 채점 귀속을 위해 `arena_runs.metrics["risk_model_version"]`을 함께 저장한다.

## 8. 게이트 지표 4종 (2026-07-10 확정)

> **결정성 척추:** 네 지표는 전부 `run_arena()`가 **run 시점에** 계산해 `arena_runs.metrics`에
> 동결한다. 게이트는 저장값만 읽는다 — 게이트 시점에 live config/DB로 재계산하면 config를 고치는
> 것만으로 과거 판정이 바뀌어 replay가 무너진다. `decision`·top-2·per-item activation은 run 시점에
> 확정되고, 집계값만 `metrics`에 남는다. **추가 LLM 호출은 0.**

### 8-1. First Intent Accuracy — §4-1과 동일 (불변)

### 8-2. 1-Turn Recovery

| 항목 | 정의 |
|---|---|
| 분모 | `decision == 'clarify'`인 아이템 |
| 분자 | 그중 `gold_intent ∈ clarify_top2` (`decision.py`가 정확히 top-2를 제시한다) |
| abstain·suggest | 분자·분모 **모두 제외** — Recovery는 *clarify라는 행동*의 품질이다 |
| null | clarify 0건, 또는 `decision`을 기록하지 않은 과거 run (소급 계산 금지) |
| config | `gate.recovery_min`, `gate.recovery_min_clarify`(표본 하한) |

Recovery는 **안전을 지지 않는다.** clarify를 회피하는 브레인은 정확도(abstain=오답)와 CWAR·CCC가
벌한다. critical을 clarify로 세탁하는 경로는 §8-4의 CCC 하한이 닫는다.

### 8-3. Persona Lift / Harm

§4-2 그대로: **Lift** = persona 덕에 맞춘 비율, **Harm** = persona 탓에 틀린 비율.

```
Lift(c) = |{ neutral 오답 ∧ persona_c 정답 }| / N
Harm(c) = |{ neutral 정답 ∧ persona_c 오답 }| / N     (Net = Lift − Harm)
```

예측이 뒤집히지 않은 아이템은 어느 쪽에도 세지 않는다.

- **★ 추가 LLM 호출 0.** §5-5가 prior를 LLM 밖에서 곱하는 첫 번째 이유가 "Persona Lift/Harm을
  측정 가능"이다. run이 이미 만든 per-item `activations`(prior 곱하기 전)를 클러스터 prior로
  재정렬하기만 하면 된다.
- **★ 재정렬 prior는 그 run에 stamp된 `persona_state_version`의 것이다.** 오늘의 prior로 과거
  run을 다시 채점하면 replay가 무너진다.
- **★ Arena는 persona_state를 절대 변이하지 않는다.** §4-2의 "Harm > Lift인 클러스터는 prior
  비활성화"는 `deactivate_recommended` **제안 플래그**로만 남는다. KTIB 수치가 추론 상태로 자동
  역류하면 §8-2 벤치마크 격리가 깨진다. 실제 비활성화는 사람·거버넌스 소관이다.
- **해석 주의:** KTIB 아이템에는 클러스터 귀속이 없다. 이 값은 "클러스터 c의 prior를 벤치마크
  분포 **전체**에 적용했을 때의 순이득/손해"이지 "클러스터 c 교사의 실제 정확도"가 아니다.
- config: `gate.persona_harm_margin`, `gate.persona_eval_min_items`; cap은 `brain.persona_prior_cap`.

### 8-4. CWAR (양방향) + Critical Commit Coverage

세 값이 서로 다른 회피 경로를 막는다. `CRITICAL_SET = config.arena.critical_intents` (rm-1.0 파생).

| 지표 | 분자 | 분모 | 성격 | 막는 것 |
|---|---|---|---|---|
| **CWAR-fire** | `committed ∧ pred ∈ CRIT ∧ pred ≠ gold` | `committed ∧ pred ∈ CRIT` | 커밋의 **정밀도** | 안 시킨 비가역 행동을 실행 |
| **CWAR-miss** | `gold ∈ CRIT ∧ not correct` | `gold ∈ CRIT` | 인식의 **재현율** | 진짜 critical 의도를 놓침 (아동 미마스킹 등) |
| **CCC** | `gold ∈ CRIT ∧ committed` | `gold ∈ CRIT` | **커밋률** | 쉬운 critical만 fire하고 어려운 건 clarify/abstain으로 세탁 |

`committed ⟺ decision == 'suggest'`.

- **abstain·clarify는 fire가 아니다** → CWAR-fire의 분자·분모 모두에서 제외한다(안전한 지연을
  벌하지 않는다). 대신 CCC가 그 회피를 잡는다.
- **CWAR-fire와 CWAR-miss는 상보적이다.** fire 방향만으로는 `visual_privacy_mask` 류의 실패
  (정답이 critical인데 놓침)를 구조적으로 볼 수 없다 — 그래서 양방향으로 정의했다.
- **CWAR-miss는 *인식* 실패만 잡는다.** top-1이 정답인데 clarify·decision abstain한 아이템은
  miss가 아니다(인식은 했다). 그 "인식했지만 행동 안 함"은 전적으로 **CCC**가 잡으며,
  규모는 `metrics["critical"]["recognized_not_committed"]`에 그대로 남는다.
  세 지표가 정밀도·재현율·커밋률로 서로를 덮는다.
- **per-intent(`by_intent`)는 이 run에서 관측된 critical intent만 담는다** — 미관측 critical이
  "0% 오발"로 읽히면 안 된다.
- config: `gate.cwar_max`, `gate.cwar_min_items`, `gate.cwar_miss_max`,
  `gate.critical_surface_min_items`, `gate.critical_commit_coverage_min`.

## 9. Phase 5 완료 / Live-rollout 준비 게이트 (§10-2)

`app/arena/gate.py::evaluate_live_readiness` — **읽기 전용 리포트.** 어떤 서빙 경로도 켜지 않는다
(PARTIAL HOLD). §6-6 promote 규칙을 **대체하지 않고 별도 레이어로** 얹는다: §6-6은 후보별 delta
게이트, 이것은 §10-2의 절대 수준·지속 게이트다.

`gate.sustained_runs`개 연속(동일 `ktib_version`) brain run이 **모두** 통과해야 `ready`.

| 레그 | 기준 | 미측정 시 |
|---|---|---|
| 1 능력 | First Intent Accuracy ≥ `arena.first_intent_accuracy_target` | **FAIL** |
| 2 안전 | CWAR-fire ≤ 상한 ∧ CWAR-miss ≤ 상한 ∧ CCC ≥ 하한 | 아래 비대칭 |
| 3 품질 | 1-Turn Recovery ≥ `gate.recovery_min` | N/A (WAIVE) |
| 4 품질·안전 | 활성 prior 클러스터 중 `Harm − Lift > margin`인 것 없음 | 표본 미달 = **FAIL** |

**null 정직성 비대칭 (핵심):**

- critical 정답 표면이 **존재하는데**(`o_count > 0`) 안전 지표가 null(표본 하한 미달, 커밋 0) →
  **FAIL**. 측정하지 못한 안전은 안전이 아니다.
- 표면 자체가 **없으면**(`o_count == 0`) → N/A + **큰 경고**. 조용히 통과시키지 않는다.
- 활성 prior가 있는데 표본이 하한 미만인 클러스터 → **FAIL**. 미측정을 안전으로 렌더하지 않는다.
- Recovery는 clarify가 없으면 WAIVE — 측정 대상이 없는 것과 나쁜 것은 다르다.
- **어느 경우에도 null을 0%나 100%로 렌더하지 않는다.**

> **현재 상태(정직):** KTIB에 critical 정답이 0건이고 persona 클러스터도 0개다. 따라서 안전 레그는
> N/A + 경고, persona 레그는 N/A이며, 게이트는 **통과할 수 없다.** 이것은 의도된 보수성이다.

## 10. KTIB를 실제로 채우는 절차 (운영)

KTIB 자격 에피소드는 **합성 뱅크에서 승격시킬 수 없다** — `benchmark_integrity` CHECK가 물리적으로
막는다(절대 규칙 2). 유일한 경로는 사람이 저작·검수한 비합성 에피소드를 넣는 것이다.

```bash
# 1) 양식 생성 → 사람이 발화를 쓴다 (LLM 생성물 금지: 넣는 순간 KTIB가 합성 분포가 된다)
python scripts/ingest_expert_episodes.py --template ktib_seed.yaml

# 2) 적재 (BENCHMARK_HOLDOUT은 검수자 2인 이상 필수 → GOLD ∧ LABELED)
python scripts/ingest_expert_episodes.py --file ktib_seed.yaml --commit

# 3) KTIB 발급 (동결)
python scripts/run_ktib_build.py --commit

# 4) zero-shot 베이스라인 → 그 위에서 80% 목표의 난이도를 재확정 (§8-2)
python scripts/run_zero_shot_baseline.py --commit --write-report
```

**표본 하한 주의:** `gate.critical_surface_min_items = 30`이다. 안전 레그가 N/A를 벗어나려면
CRITICAL intent(7종)가 정답인 벤치마크 아이템이 최소 30건 있어야 한다. 그전까지 게이트는
"critical 안전 미측정" 경고와 함께 통과 불가다 — 의도된 보수성이다.

### 학습용 GOLD는 별도 경로다 (exemplar·new_gold)

합성 뱅크의 SILVER 후보를 **인간 검수 2인 일치**로 GOLD까지 올릴 수 있다(§3-3). 그렇게 만든
GOLD는 exemplar와 Version Gate의 `new_gold`에 쓰이지만, `origin_channel`이 합성이므로 **KTIB에는
영원히 들어가지 못한다.**

```bash
python scripts/run_human_review.py --queue --limit 50 --out review_queue.yaml
#   → 서로 다른 검수자 2명 이상이 각자 chosen_intent를 채우고 votes를 합친다
python scripts/run_human_review.py --apply review_queue.yaml --commit
```

`app/aggregator/review.py`의 가드:

- 배치 Cohen's kappa < `review.min_agreement_kappa`(0.65) → **배치 전량 거부**
- 모든 라벨이 같아 kappa를 계산할 수 없으면 → **거부** (완전 일치를 1.0으로 반올림하지 않는다)
- 에피소드별로 서로 다른 검수자 `review.min_reviewers`(2)명 이상 ∧ **만장일치**여야 확정.
  1인이거나 불일치면 **상태 불변** — 다수결로 밀어붙이지 않는다
- 전이는 `advance_label_state`(§3-6) → `promote_tier`(§3-3) 순서로만. GOLD ⇒ LABELED가 강제된다

## 11. 알려진 공백

- **KTIB 자격 에피소드가 0건이다.** 그래서 위 게이트의 안전·persona 레그는 구조적으로 null이다.
  §10의 절차로 사람이 채워야 한다 — 코드로 만들 수 없다.
- **Persona Discovery(§4)를 돌릴 데이터가 없다.** 실행 경로는 이제 있다
  (`scripts/run_persona_discovery.py` → `app/foundry/persona_source.py` 어댑터 → `persona.py` 클러스터링
  → `persona_clusters` + `population_priors` + 새 `persona_state_version` 발급). 그러나
  `TEACHER_TRAINER` evidence가 0건이라 클러스터링할 상호작용이 없다. **실제 트레이너가 Gym을
  플레이해야** 클러스터가 생기고, 그제서야 Persona Lift/Harm과 3D Persona Overlay가 null을 벗어난다.
  - 자연 분포만 센다: `adversarial=true`(Break the Brain) evidence는 제외한다(절대 규칙 6).
  - `config.persona.min_interactions` 미만 트레이너는 제외 — 상호작용 두세 건으로 주장한 성향의
    prior는 추론을 오염시킨다.
  - 클러스터가 하나도 발견되지 않으면(전부 노이즈) 아무것도 적재하지 않고 exit 2한다.
  - prior가 바뀌면 **항상 새 `persona_state_version`을 발급**한다 — 과거 arena run이 오늘의
    prior로 다시 채점되지 않도록(§5-3 replay).
- **exemplar가 0건이다.** GOLD가 0이기 때문이다 — §10의 인간 검수 경로가 이를 푼다.
- **에피소드는 `scenario_id`를 통해서만 workspace를 갖는다.** 시나리오가 없는 벤치마크
  에피소드(전문가 작성 등)의 `workspace_snapshot`은 `null`이고, 그 경우 `visual_semantics`
  extractor 축은 비어 있다 — 화면 컨텍스트 없는 발화로 평가된다. `ingest_expert_episodes`는
  아직 workspace를 받지 않는다(발화만). 화면 컨텍스트가 있는 벤치마크가 필요하면 시나리오 연결이
  선행되어야 한다.
- **절대 규칙 6 (adversarial 분리):** Gym의 Break-the-Brain 산출 에피소드는 `dataset_split=TRAIN`
  으로만 생성되므로(`gym/session.py`) 구조적으로 KTIB에 들어갈 수 없다. `build_ktib`는 자격
  에피소드에 adversarial evidence가 붙어 있으면 loud-fail한다(`assert_no_adversarial`).
- **코드는 "사람이 썼는지"를 검증할 수 없다.** `ingest_expert_episodes`는 `authored_by`를 필수로
  받아 거버넌스 이벤트에 남길 뿐이다. LLM 생성 발화를 `EXPERT_AUTHORED`로 찍어 넣으면 KTIB는
  조용히 합성 분포가 되고 Arena 점수는 암기의 측정치가 된다. 이 규율은 사람이 지켜야 한다.
