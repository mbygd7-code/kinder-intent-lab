# Arena / KTIB — 지표 정의 (문서 ③, 진행 중)

> 제1 설계 문서: `docs/01-foundry/kinder-intent-foundry-growth-system-v1.0.md` §8-2.
> 충돌 시 제1 설계 문서가 이긴다. 이 문서는 **구현된 것만** 정의한다.

## Change Log

| 날짜 | 변경 |
|---|---|
| 2026-07-10 | 최초 작성 — Phase 5(T5.1~T5.2)에서 구현된 지표만 기술 |
| 2026-07-10 | §6 추가 — Arena→Observatory 반영, 밝기 가드, §7-6 스테이지 해석 2건, Persona Overlay |

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

top-1 예측이 gold intent와 정확히 일치한 비율. global / region / node 3층.

- **abstain**(`predicted_intent=None`; UNKNOWN 예측·계약 위반 포함)은 **오답**으로 센다.
  단 `abstain_count`로 따로 기록해 오답과 구분한다.
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

### 성장 스테이지 (§7-6) — 구현 시 내린 두 가지 해석

문서 §7-6 표를 그대로 코드로 옮길 수 없는 지점이 두 곳 있었다. **설계를 바꾸지 않고**
아래처럼 좁게 해석했다. 설계 확정이 필요한 항목이다.

1. **Stage 1~3 기준이 서로 배타적이지 않다.** 예: 측정 비율 40% + region reliability 60%는
   Stage 1(`reliability < 50%`)에도, Stage 2(`측정 ≥ 50%`)에도, Stage 3(`≥ 70%`)에도
   해당하지 않는다. → **높은 단계부터 검사해 처음 만족하는 값**을 쓴다(단조 사다리):
   `3 if reliability ≥ 0.70` → `2 if 측정비율 ≥ 0.50` → `1 if 측정 ≥ 1` → `0`.
2. **Stage 4(Cross-Region Flow)는 판정하지 않는다.** 판정 기준의 "인접 region"이 설계 어디에도
   정의돼 있지 않고("주요 confusion edge 감소 추세"도 run 이력 윈도 정의가 없다), 인접성을
   임의로 만들지 않기로 했다. 따라서 전역 스테이지는 3에서 5로 건너뛴다.

Stage 5(global ≥ 목표)는 `config.arena.first_intent_accuracy_target`을 재사용한다 —
KTIB 목표가 두 곳에 따로 있으면 안 된다.

### Persona Overlay

`GET /v1/observatory/persona-overlay`. 원천은 `population_priors`(현재 `state_version`) —
§5-5에서 **LLM 밖에서 activation에 곱해지는 배수**다. 측정된 클러스터별 정확도가 아니다.
클러스터가 없으면 빈 목록을 돌려준다(분포를 지어내지 않는다).

## 7. 아직 정의되지 않은 지표 (TBD)

§8-2가 "문서 ③"으로 미룬 항목들. **구현되지 않았고, 여기서 임의로 정의하지 않는다.**

- **Recovery** — clarify 이후 의도 복구율
- **Persona Lift / Harm** — prior가 정확도를 올린/내린 정도 (§5-5의 곱셈 단계 기여 분리)
- **CWAR** — runtime live 경로 부활 트리거의 안전 지표 (§10-2)

이 셋은 도메인 합의가 필요하다. 정의가 서기 전까지 Phase 5 완료 게이트는
`first_intent_accuracy`만으로 판정한다.

## 8. 알려진 공백

- **`arena.critical_intents`가 빈 목록이다.** §6-6 promote 규칙의 "critical intent 악화 없음"
  조건은 대상이 지정될 때까지 항상 통과한다. 지어낸 목록으로 게이트를 위장하지 않는다.
- **에피소드는 `scenario_id`를 통해서만 workspace를 갖는다.** 시나리오가 없는 벤치마크
  에피소드(전문가 작성 등)의 `workspace_snapshot`은 `null`이고, 그 경우 `visual_semantics`
  extractor 축은 비어 있다 — 화면 컨텍스트 없는 발화로 평가된다.
