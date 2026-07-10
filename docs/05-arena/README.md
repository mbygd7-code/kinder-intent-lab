# Arena / KTIB — 지표 정의 (문서 ③, 진행 중)

> 제1 설계 문서: `docs/01-foundry/kinder-intent-foundry-growth-system-v1.0.md` §8-2.
> 충돌 시 제1 설계 문서가 이긴다. 이 문서는 **구현된 것만** 정의한다.

## Change Log

| 날짜 | 변경 |
|---|---|
| 2026-07-10 | 최초 작성 — Phase 5(T5.1~T5.2)에서 구현된 지표만 기술 |

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

## 6. 아직 정의되지 않은 지표 (TBD)

§8-2가 "문서 ③"으로 미룬 항목들. **구현되지 않았고, 여기서 임의로 정의하지 않는다.**

- **Recovery** — clarify 이후 의도 복구율
- **Persona Lift / Harm** — prior가 정확도를 올린/내린 정도 (§5-5의 곱셈 단계 기여 분리)
- **CWAR** — runtime live 경로 부활 트리거의 안전 지표 (§10-2)

이 셋은 도메인 합의가 필요하다. 정의가 서기 전까지 Phase 5 완료 게이트는
`first_intent_accuracy`만으로 판정한다.

## 7. 알려진 공백

- **`arena.critical_intents`가 빈 목록이다.** §6-6 promote 규칙의 "critical intent 악화 없음"
  조건은 대상이 지정될 때까지 항상 통과한다. 지어낸 목록으로 게이트를 위장하지 않는다.
- **에피소드는 `scenario_id`를 통해서만 workspace를 갖는다.** 시나리오가 없는 벤치마크
  에피소드(전문가 작성 등)의 `workspace_snapshot`은 `null`이고, 그 경우 `visual_semantics`
  extractor 축은 비어 있다 — 화면 컨텍스트 없는 발화로 평가된다.
