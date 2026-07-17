# 09. 평가와 성능 — 96%와 2%가 정확히 무엇을 뜻하는가

> **한눈에 보기** — 킨더브레인의 공식 성적은 단 하나의 경로로만 만들어진다: 사람이 출제해 동결한 시험지(KTIB)를 Arena가 채점하고, 그 결과만이 점수·밝기(brightness)가 된다. 목표 96%(first intent accuracy)는 **실측이 아니라 장기 목표**이고, 현재 실측은 뇌 0.0%(대표 예문 0의 정직한 0) vs 범용 LLM 베이스라인 88.1%다. 2%(cwar_max)는 "위험 의도를 실행하겠다고 커밋한 것 중 오발 비율"의 상한이며, 실서비스 오실행률 그 자체가 아니다(실행 전 확인 게이트가 별도로 존재).

---

## 1. 점수가 만들어지는 유일한 경로

```
사람 출제 문항 → 2인 검수 → BENCHMARK_HOLDOUT(GOLD) → KTIB 동결(스냅샷)
→ Arena가 전 문항 추론 → 지표 계산 → arena_runs.metrics에 동결 저장
→ reflect가 노드 밝기·혼동 실측 반영 (이 경로 밖에서 brightness 쓰기 = 가드 폭발)
```
[근거: backend/app/arena/runner.py, backend/app/arena/metrics.py, backend/app/arena/reflect.py, backend/app/models/guards.py]

지표는 run 시점에 계산돼 `arena_runs.metrics`에 **동결**된다 — 나중에 config를 바꿔도 과거 판정이 바뀌지 않는다(replay 무결성). [근거: docs/01-foundry v1.3 Change Log]

---

## 2. 지표 사전 (쉬운 정의 → 기술 정의 → 임계값 → 착시 주의)

### first intent accuracy (첫 시도 정확도) — 헤드라인 지표
- 쉬운: "말 한마디에 첫 추측이 바로 맞은 비율"
- 기술: KTIB 문항 중 top_intent == gold_intent인 비율(문항 단위 micro)
- 목표: **0.96** [근거: config/experiments.yaml::arena.first_intent_accuracy_target — v1.4에서 zero-shot 88.1% 실측 위에 재확정, §7-6 Stage 5도 같은 값 재사용]
- 착시: 전체 평균이 높아도 특정 의도가 0%일 수 있다 → intent별·region별 분해와 함께 볼 것. 또 현재 시험지가 8개 의도에 집중이라 "70개 의도의 실력"이 아니라 "위험 7 의도 중심 실력"을 잰다는 점을 명시해야 한다.

### confidence / margin
- 쉬운: 확신의 크기 / 1등과 2등의 격차
- 기술: 정규화된 top activation / top1−top2 [근거: backend/app/brain/inference.py]
- 사용처: decision 정책 — margin<0.15 또는 confidence<0.40이면 clarify, top<0.25면 abstain [근거: config::decision]
- 착시: confidence는 "맞을 확률"이 아니다 — 보정(calibration) 전에는 과신·저신뢰 왜곡이 있다.

### calibration / ECE (Expected Calibration Error)
- 쉬운: "80% 확신이라고 말했을 때 실제로 80% 맞는가"의 어긋남
- 기술: 확신 구간별 |실제 정확도 − 평균 확신|의 가중 평균. 노드별 calibration_ece로 Arena가 기록 [근거: backend/app/models/brain.py::BrainNode.calibration_ece, reflect]
- 좋은 값: 0에 가까움. 착시: 정확도가 높아도 ECE가 크면 confidence 기반 자동화(Assist 등급)가 위험하다.

### CWAR (Critical Wrong-Action Rate) — 위험 오발률
- 쉬운: "위험한 일을 하겠다고 확정한 것 중 잘못 짚은 비율"
- 기술: fire = P(오발 | critical로 커밋), miss = P(오인식 | 정답이 critical) 양방향 [근거: backend/app/arena/metrics.py, v1.3 정의]
- 상한: **0.02** [근거: config::arena.cwar_max]
- **정확한 해석**: 이것은 Arena 평가 지표다. 실서비스에서 CRITICAL 7은 성적과 무관하게 **실행 전 확인(requires_confirmation)** 이 또 한 겹 있으므로, "2% = 실제 오실행 허용률"이 아니다. 다만 확인 UI에 잘못된 미리보기가 뜨는 빈도의 상한으로 이해하는 것이 정확하다.

### CCC (Critical Commit Coverage)
- 쉬운: "위험 의도를 겁나서 전부 '되묻기'로 도망가지 않았는가"
- 기술: 정답이 critical인 문항 중 clarify/abstain으로 세탁하지 않고 커밋한 비율, 하한 **0.80** [근거: config::arena.critical_commit_coverage_min]
- 왜 필요: CWAR만 보면 "전부 abstain"이 최적해가 된다 — CCC가 그 꼼수를 막는다. 분모 성립 조건: critical 문항 수 ≥ critical_surface_min_items(30)/의도. **critical 표면이 있는데 지표가 null이면 게이트 FAIL**("측정 못 한 안전은 안전이 아니다").

### Cohen's kappa / 관측 일치율(agreement_rate)
- 쉬운: 두 검수자가 "우연 이상으로" 일치했는가 / 그냥 일치한 비율
- 임계: kappa ≥ **0.65**(독립 라벨링) 또는 일치율 ≥ **0.80**(O/X 승인 — v1.6에서 추가) [근거: config::review.min_agreement_kappa·min_expert_agreement]
- 착시(실측 사례): O/X 승인처럼 판정이 O로 쏠리면 일치율 95.7%인데 kappa −0.02가 나온다(base-rate 역설) — 그래서 두 척도를 경로별로 나눠 쓴다. [근거: docs/01-foundry v1.6 Change Log]

### 그 외
- **abstain rate / clarify rate / correction rate** — 공식 게이트 지표가 아니라 운영 관찰 지표. 애매 발화 리포트가 출처별로 집계(clarify권 판정: margin/confidence 임계 재사용) [근거: backend/app/api/observatory.py::ambiguity_report] — PARTIAL(리포트만, 시계열 없음)
- **top-k recall** — PLANNED(문서 언급, 코드 미구현 확인)
- **1-Turn Recovery / Persona Lift·Harm** — Arena metrics에 정의·동결 [근거: backend/app/arena/metrics.py] — IMPLEMENTED(데이터 대기)
- **GOLD count / KTIB size / confusion measured_count** — 성장 재료·자 크기·실측 혼동 수. 현재 386(전부 시험지) / 386문항 / 0(전부 가설).

### macro vs micro
- micro(현재 헤드라인): 문항 단위 평균 — 문항 많은 의도가 지배.
- macro: 의도별 정확도의 평균 — 소수 문항 의도도 동등 가중. 62개 의도가 문항 0인 현재는 macro 자체가 성립하지 않는다(분모 없음) — 시험 확충 후 병행 보고 권장.

---

## 3. brightness — 무엇이고 누가 갱신하나

- 정의: 노드(의도)별 `heldout_accuracy` — 3D 뇌에서 노드의 **밝기**로 시각화되는 "시험에서 증명된 실력". [근거: backend/app/models/brain.py::BrainNode.heldout_accuracy]
- 갱신 주체: **Arena 반영(reflect) 단 하나**. 훈련·교정·backfill·API 어디에서도 쓸 수 없고, 시도하면 가드 예외. [근거: backend/app/models/guards.py::arena_brightness_write, CLAUDE.md 절대 규칙 3]
- 따라서 "공부를 시켰는데 왜 안 밝아지죠?"의 답: 공부는 크기(size)·대기 링을 바꾸고, **밝기는 시험을 봐야** 바뀐다.

---

## 4. 현재 성능 스냅샷 (2026-07-17 로컬 DB 실측)

| 항목 | 값 | 해석 |
|---|---|---|
| zero-shot 베이스라인 | **88.1%** (claude-sonnet-5, ktib-2 185문항) | 범용 LLM의 출발선 — 목표 96%의 근거 [근거: arena_runs AR_26fabf09a3c2] |
| Seed Brain(seed-v0) | **0.0%** × 3회 (ktib-2 2회, ktib-3 1회) | 대표 예문 0 → 전 문항 abstain — **정직한 0**(고장 아님) |
| 대표 예문(exemplar) | 0 | 채점 버튼이 이 상태를 감지해 비활성(0% 예정 가드) |
| KTIB | ktib-3 · 386문항 · **8/70 의도** | CRITICAL 7 각 47~58문항 + doc_observation_record 1 |
| 혼동 edge | 629 (전부 hypothesized·SKEPTIC) | 실측 확정(confirmed) 0 — 첫 유효 채점 후 시작 |
| CWAR·CCC·ECE | null | 유효 run 없음 — **UNKNOWN이 아니라 "측정 전"**으로 읽을 것 |
| brain_versions | 0행 | 첫 candidate는 new GOLD ≥ 200 이후 |

## 현재 상태
- 측정 축(시험지·베이스라인·지표 동결 체계): IMPLEMENTED.
- 유효 점수: BLOCKED — 대표 예문 0(사람 검수 게이트 대기).

## 주의사항
- "96%"를 현재 성능처럼 말하지 말 것 — **목표**다. 현재 실측은 0.0%(사유 명확)이고, 다음 이정표는 "첫 유효 점수 > 0".
- "0.0%"를 실패로 보고하지 말 것 — 지어내지 않는 설계의 증거이며, 베이스라인 88.1%가 상한 참고선이다.
- 전체 평균만 인용하지 말 것 — 시험 커버리지(8/70)를 반드시 병기.

## 다음 단계
- 채점 실행 조건과 방법: [11-operations-guide.md](11-operations-guide.md) E절 · 지표의 안전 규칙 연결: [10-safety-and-governance.md](10-safety-and-governance.md)
