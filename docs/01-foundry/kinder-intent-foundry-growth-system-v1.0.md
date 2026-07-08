# Kinder Intent Brain Foundry & Growth System v1.1

| 항목 | 내용 |
|---|---|
| 상태 | DRAFT v1.1 |
| 지위 | **Kinder Intent Lab의 제1 설계 문서** — 킨더버스와 분리된 독립 실험실 설계 |
| 범위 밖 | 킨더버스 **live rollout** API·서빙 (0%) → PARTIAL HOLD 문서 `/docs/06-runtime-integration/kinder-intent-runtime-spec-v0.1.md`(v0.2). 단, **Shadow 0a(Distribution Capture)/0b(Shadow Inference)는 거버넌스 조건 충족 시 조기 병행 가능**(동 문서 §2) — 실사용 언어가 Atlas·OOD 검증에 조기 공급되는 플라이휠 |
| 후속 문서 | ② 어노테이션 가이드 · ③ 위험 등급표 + 지표 정의 |

## Change Log

| 버전 | 일자 | 변경 요약 |
|---|---|---|
| v1.1 | 2026-07-08 | 개발총괄 2차 리뷰 전파: 범위 선언에서 Shadow 전면 보류 해제→0a/0b 조기 병행(헤더·§0-2·§10-2), evidence에 `WEAK_BEHAVIORAL`·`DOMAIN_RULE` 추가 + 서열 고정 폐지(§3-1), episode 스키마 3축 provenance(`origin_channel`/`episode_creator_type`/`primary_subject_type`) + `dataset_split` + `label_state`(§3-2), tier에서 SYNTHETIC 제외·UNVERIFIED 추가(§3-3), constraint 재정의(§3-4), Label State Machine + Aggregator 신설(§3-6), S5 canonical scenario에 `visual_semantics` 통제 어휘 필드(§1-S5), Arena replay 무결성·KTIB extractor 버전 고정(§8-2), End-to-End Trace 신설(§6-7), config 추가(§10-1) |
| v1.0 | 2026-07-08 | 최초 작성 |

---

## 0. 이 시스템이 무엇인지 (원칙)

> 우리는 데이터 테이블을 보며 AI를 훈련하지 않는다.
> 교사의 의도를 이해하는 3차원 뇌를 돌려보며, 어두운 영역과 헷갈리는 연결을 발견하고,
> 그 영역을 직접 클릭해 인간과 AI가 함께 강화한다.

### 0-1. 지금 만드는 것 5가지

1. **Backfill Foundry** — 실사용 데이터가 0인 상태에서, 범용 LLM의 지능으로 유아교육 자료·교사 언어를 찾아 구조화해 Brain의 첫 지식을 채우는 공장
2. **Seed Brain** — 내부가 들여다보이는 의도 추론 엔진 (블랙박스 금지 — §5가 내부 구조 전체를 정의한다)
3. **3D Brain** — 별도 대시보드가 아니라 **시스템의 첫 화면이자 유일한 진입점** (§7)
4. **Growth Loop** — 클릭 → 진단 → 전략 → 훈련 → 검증 → 성장의 강화 루프 (§6)
5. **KTIB** — 독립 벤치마크. 목표: First Intent Accuracy 80% (§8)

### 0-2. 지금 만들지 않는 것 / 조기 병행 가능한 것

**만들지 않는 것:** 킨더버스 live rollout(Suggest/Assist/Auto), 서빙 인프라. **KTIB 80% + 안전 지표 충족**이 live 경로의 부활 조건이다.

**조기 병행 가능한 것:** Shadow Adapter — **0a Distribution Capture**(추론 없이 실사용 발화·컨텍스트 로깅만, Brain 불필요)와 **0b Shadow Inference**(Brain v0의 비노출 추론). 진입 게이트는 정확도가 아니라 **거버넌스 7항목**(목적 정의·법적 근거·PII 게이트·최소 수집·보존·옵트아웃·스키마 매핑, runtime 문서 §2)이다. 폐쇄 실험실에서만 80%를 만들면 Gym 82% ≠ 실사용 58% 같은 sim-to-real 붕괴를 늦게 발견한다 — 0a가 공급하는 실제 교사 언어는 Atlas → Simulator 현실성 → 합성 데이터 품질로 이어지는 플라이휠의 시동이다.

### 0-3. 운영 원칙 9

1. 처음부터 완벽한 모델을 만들지 않는다
2. 정확도보다 confusion map을 먼저 본다
3. Persona는 가정이 아니라 데이터에서 발견한다
4. 합성 데이터와 인간 검증 데이터를 절대 섞어 부풀리지 않는다 (DB constraint로 강제, §3-4)
5. 3D Brain은 장식이 아니라 훈련 조종석이다
6. 클릭 → 훈련 → 성장 시각화 루프를 반드시 구현한다
7. **모든 숫자 임계값은 실험 파라미터다** — margin, n≥20, ±0.05 같은 값은 config에만 존재하고 코드에 굳히지 않는다 (§10-1)
8. **정확도(밝기)는 오직 Arena 재평가로만 변한다** — 훈련 행위 자체는 정확도를 바꾸지 못한다
9. **노드는 자동으로 태어나지 않는다** — 온톨로지 변경은 사람이 승인하는 거버넌스 이벤트다

### 0-4. 문서 비중

| 파트 | 내용 | 비중 |
|---|---|---|
| §0 | 원칙 | 10% |
| §1 | Backfill Data Foundry | 25% |
| §2 | Teacher Language Atlas | 15% |
| §3 | Intent Episode & Evidence Model | 15% |
| §4 | Persona Discovery | 10% |
| §5–7 | Brain 내부 구조 + Growth Loop + 3D 네비게이션 | 20% |
| §8 | Gym / Arena 연결 | 5% |
| §9–10 | 저장 구조 · Config · 로드맵 | — |
| 킨더버스 Runtime API | | **0%** |

---

## 1. Backfill Data Foundry

**질문:** 실사용 데이터가 아직 없을 때 Seed Brain을 어떻게 채울 것인가.
**답:** 아래 13단계 파이프라인. 이 파이프라인이 이 프로젝트의 심장이다.

### 1-0. 파이프라인 전경

```text
S1  SOURCE DISCOVERY AGENT        공식/전문/교사 언어 자료 후보 발견
          ↓
S2  SOURCE GOVERNANCE GATE        저작권·약관·개인정보·수집 범위 판단
          ↓
S3  DOMAIN KNOWLEDGE EXTRACTOR    유아교육 개념·상황·교사 고민 추출
          ↓
S4  TEACHER LANGUAGE MINER        교사의 질문 표현과 애매한 언어 패턴 추출 → Atlas(§2)
          ↓
S5  SITUATION BUILDER             교사 상황을 canonical scenario로 변환
          ↓
S6  TEACHER SIMULATOR             Persona lens에 따라 실제 교사 발화 생성
          ↓
S7  INTENT ANALYST                잠재 Intent 후보 3~7개 생성
          ↓
S8  SKEPTIC                       반대 해석·혼동 후보 제시 → confusion edge 원천
          ↓
S9  DOMAIN JUDGE                  유아교육 맥락 검증
          ↓
S10 CONSENSUS LABELER             확률 라벨(분포) 생성
          ↓
S11 EPISODE BANK                  적재 (§3 스키마, tier ≤ SILVER)
          ↓
S12 PERSONA DISCOVERY             §4
          ↓
S13 SEED BRAIN BACKFILL           §5 — 노드에 exemplar·evidence·prior 주입
```

각 단계는 `역할 / 입출력 / 핵심 규칙 / 실패 처리`로 정의한다. S6~S10은 LLM 에이전트이며, 각각 프롬프트 계약(입력 컨텍스트·출력 스키마·금지사항)을 갖는다.

### S1. Source Discovery Agent

- **역할:** 자료 후보를 발견만 한다. 수집 여부는 S2가 결정.
- **소스 3클래스:** `AUTHORITY`(누리과정, 보육과정 해설, 평가 가이드) · `PRACTICE`(놀이사례집, 관찰기록 예시, 활동 흐름 문서) · `TEACHER_LANGUAGE`(교사 커뮤니티, Q&A, 업무 고민글)
- **출력:** Source Registry entry. `discovery_reason`(왜 이 자료가 의도/언어 밀도가 높은가) 필수.

```json
{
  "source_id": "SRC_0042",
  "source_class": "TEACHER_LANGUAGE",
  "title": "교사 커뮤니티 놀이지도 질문 게시판",
  "access": "public_web",
  "format": "forum_posts",
  "est_volume": "12000 posts",
  "discovery_reason": "놀이 개입 시점 고민 표현의 밀도가 높음",
  "governance": {
    "status": "PENDING",
    "reviewed_by": null,
    "rules": []
  }
}
```

### S2. Source Governance Gate

- **판정 3종:**

| 판정 | 의미 | 기본 적용 |
|---|---|---|
| `ALLOW` | 원문 저장 가능 | 공공누리 등 라이선스 확인된 공식 자료 |
| `TRANSFORM_ONLY` | **원문 저장 금지.** 패턴·통계·개념만 추출 | 커뮤니티·Q&A의 기본값 |
| `DENY` | 수집 금지 | 약관 위반, 식별정보 제거 불가 자료 |

- **개인정보 규칙:** 아동·교사 식별정보가 포함된 레코드는 익명화 시도가 아니라 **원천 drop**이 기본. drop 카운터만 기록.
- **핵심 규칙:** 게이트 통과 전에는 어떤 원문도 저장소에 들어가지 않는다. governance 필드가 비어 있는 source는 하류 단계가 읽을 수 없다(파이프라인 레벨 차단).

### S3. Domain Knowledge Extractor

- **역할:** ALLOW/TRANSFORM_ONLY 소스에서 3종 추출 — `concept`(교육 개념), `situation_frame`(교실 상황 프레임), `teacher_concern`(교사 고민 패턴).
- **출력:** Situation Frame — 이후 모든 시나리오의 뿌리.

```json
{
  "frame_id": "SF_00312",
  "domain": "PLAY",
  "summary": "아이들이 나뭇잎 분류 놀이를 20분 이상 지속, 교사는 확장 여부를 고민",
  "participants": {"children": "4-6명", "age": "만4"},
  "materials": ["나뭇잎", "분류판"],
  "teacher_concern": "개입 시점과 방식",
  "source_refs": ["SRC_0007#p112"],
  "extraction_confidence": 0.82
}
```

- **품질 게이트:** `extraction_confidence < config.extract_min` → 사람 검토 큐. Judge(S9)와 별개로 프레임 자체의 사실성만 본다.

### S4. Teacher Language Miner

- **역할:** TRANSFORM_ONLY 소스에서 **표현 패턴만** 추출한다 — §2 Atlas의 원료.
- **출력:** surface form 클러스터, 모호성 유형, 빈도 통계. 원문 인용 저장 금지 — 패러프레이즈된 대표형만 저장.
- **실패 처리:** 대표형이 원문과 임베딩 유사도 `> config.paraphrase_max`면 원문 잔존으로 간주하고 폐기(거버넌스 위반 방지).

### S5. Situation Builder

- **역할:** situation_frame → **canonical scenario**. 여기서 처음으로 "화면"이 생긴다 — workspace 상태(사진 n장, 텍스트 m개, 선택 상태)와 직전 행동을 프레임에 결합한다.

```json
{
  "scenario_id": "CS_04412",
  "frame_id": "SF_00312",
  "workspace_state": {
    "surface_type": "play_board",
    "objects_summary": {"photo": 4, "text": 2, "title": 1},
    "selection": {"type": "photo", "count": 2},
    "recent_actions": ["move_object", "move_object", "zoom_in"],
    "visual_semantics": [
      {
        "object_ref": "photo_1",
        "schema_version": "vs-1.0",
        "extractor_version": "SYNTH_BUILDER_v1",
        "scene_type": ["OUTDOOR_YARD"],
        "activity_types": ["NATURE_SORTING"],
        "materials": ["LEAF", "TRAY"],
        "observed_actions": ["SORT", "COMPARE"],
        "interaction_pattern": ["PEER_COLLABORATIVE"],
        "group_size_band": "SMALL_GROUP",
        "identity_removed": true
      }
    ]
  },
  "variation_of": null,
  "variation_axis": null
}
```

- **다양성 규칙:** 같은 frame에서 workspace 변형 k개(`config.scenario_variants`)를 생성한다 — 선택 유무 × 직전 행동 × 오브젝트 구성. **이것이 나중에 노드의 Screen Context Coverage가 된다.**
- **`visual_semantics` 계약 대칭:** 시나리오의 시각 의미 필드는 실서비스 Visual Context Gateway가 만드는 descriptor와 **동일 스키마·동일 통제 어휘**(runtime 문서 §3-1)를 쓴다 — Gym과 Live가 같은 신호로 훈련·추론되게 하는 Single Intent Core Contract의 Foundry 측 구현. 자유 서술 금지, `schema_version`·`extractor_version` 필수(합성 생성분은 `SYNTH_BUILDER_*`로 표기해 실측 extractor와 구분).

### S6. Teacher Simulator (LLM Agent)

- **역할:** persona lens × scenario → 교사 발화 생성. **persona lens는 생성 도구이지 라벨이 아니다** (§4 원칙).
- **현실성 규칙:** 발화 길이 분포·지시어("이거/저거") 비율·오타·축약 주입률은 Atlas 통계(§2)를 따른다. Atlas가 없는 초기 배치는 임시 분포로 시작하고, Atlas 갱신 시 재보정.
- **중복 통제:** 신규 발화가 기존 발화와 임베딩 유사도 `≥ config.dedup_similarity`면 폐기. 데이터 "부풀리기" 방지.
- **금지사항:** 정답 intent를 알고 발화를 생성하지 않는다(역방향 생성 금지) — scenario에서 발화가 나오고, intent 해석은 S7 이후의 일.

### S7. Intent Analyst (LLM Agent)

- **역할:** (발화 + scenario) → 잠재 intent 후보 3~7개 + 각 후보의 rationale. 온톨로지 v1의 intent_id만 사용, 매핑 불가 시 `UNKNOWN` + 자유 서술(온톨로지 확장 큐 공급).

### S8. Skeptic (LLM Agent)

- **역할:** Analyst의 해석에 반대한다. "이 발화가 사실은 X일 가능성", 혼동 후보 쌍 제시.
- **핵심 산출:** **confusion edge의 최초 공급자.** Skeptic이 제시한 쌍은 `state=hypothesized`로 confusion_edges에 적재된다(§5-6).

### S9. Domain Judge (LLM Agent + 규칙)

- **역할:** 유아교육 타당성 검증 — 발달 적합성, 누리과정 정합성, 현장 개연성. reject 사유 코드 필수.
- **운영 신호:** reject율이 `config.judge_reject_max`를 넘으면 스케일 중단 — 상류(S5/S6) 품질 문제라는 뜻이다.

### S10. Consensus Labeler

- **역할:** S7~S9 산출을 종합해 **단일 정답이 아니라 label distribution**을 만든다. 합의도와 disagreement를 함께 기록 — disagreement 자체가 confusion 후보의 두 번째 공급원이다.
- **출력:** episode의 `label_distribution` + `consensus` 필드 (§3).

### S11~S13

- **S11 Episode Bank 적재:** §3 스키마. 이 파이프라인이 만드는 것은 전부 `BRONZE/SILVER`다. GOLD는 여기서 절대 생성되지 않는다.
- **S12 Persona Discovery:** §4.
- **S13 Seed Brain Backfill:** §5 — 노드별 exemplar 선정, evidence 통계 집계, prior 테이블 초기화.

### 1-14. 실행 단위·파일럿 게이트·비용

- **Run Manifest:** 배치 실행 단위마다 source→frame→scenario→episode 계보를 기록한다. 어떤 에피소드든 원천 소스까지 역추적 가능해야 한다.
- **Pilot 500 규칙:** 전 단계를 E2E로 통과한 500 에피소드를 먼저 만든다. 게이트(전부 config): 평균 합의도 ≥ `consensus_min`, Judge reject ≤ `judge_reject_max`, 사람 스팟 검수 kappa ≥ `pilot_kappa_min`. **통과 전 스케일 금지.**
- **비용 공식:** 에피소드당 LLM 호출 ≈ 6~9회(S6~S10). 30k 에피소드 ≈ 20~27만 호출. run manifest에 토큰·비용 실측 기록, 배치별 단가 추세 모니터.

---

## 2. Teacher Language Atlas

**정의:** 교사 발화의 "애매함"을 구조화한 자산. "무슨 말인지"가 아니라 **무엇이 생략됐고, 그것이 어떤 컨텍스트 신호로 복원되는지**를 기록한다.

### 2-1. 4층 구조

| 층 | 이름 | 내용 | 예 |
|---|---|---|---|
| L1 | **Utterance Pattern** | 표현 클러스터 | `NATURALIZE`("자연스럽게"), `TIDY_UP`("정리해줘"), `PRETTIFY`("예쁘게"), `WHATS_NEXT`("다음엔 뭐하지"), `TOO_FORMAL`("평가처럼 들려") |
| L2 | **Ambiguity Taxonomy** | 모호성 유형 | `TARGET_UNSPECIFIED`(이거/저거 — 대상 불명), `VERB_POLYSEMY`(정리 = 배치? 요약? 삭제?), `SCOPE_UNSPECIFIED`(전체? 선택만?), `PURPOSE_HIDDEN`(표면 요청 뒤의 목적) |
| L3 | **Resolution Signal Map** | 각 모호성을 푸는 컨텍스트 신호 | TARGET_UNSPECIFIED → selection 신호로 해소 |
| L4 | **Domain Lexicon** | 누리과정 용어, 현장 은어, 축약 | "확장", "전이", "개입", "관찰기록" |

L3이 Atlas의 심장이다 — **Brain이 "어떤 신호를 봐야 하는지"를 배우는 곳.**

### 2-2. Atlas Entry 스키마

```json
{
  "atlas_id": "ATL_0871",
  "surface_form": "자연스럽게 해줘",
  "pattern_cluster": "NATURALIZE",
  "ambiguity_types": ["TARGET_UNSPECIFIED", "VERB_POLYSEMY"],
  "possible_intents": ["text_naturalize", "visual_layout_refine", "play_flow_naturalize"],
  "resolution_signals": [
    {"signal": "selection_type", "rule": "선택 대상이 photo면 VISUAL 계열 우세"},
    {"signal": "recent_actions", "rule": "직전에 텍스트 편집이면 DOCUMENT 계열 우세"},
    {"signal": "surface_type", "rule": "parent_message 화면이면 COMMUNICATION 계열 우세"}
  ],
  "register": {"style": "반말·해요체 혼재", "typical_length": "5-9어절"},
  "observed_count": 143,
  "source_class_mix": {"TEACHER_LANGUAGE": 0.71, "SYNTHETIC": 0.29}
}
```

### 2-3. Atlas의 소비처 3곳

1. **Teacher Simulator(S6)** — 현실적 발화 생성의 통계 기준(길이·지시어·오타 분포)
2. **Brain 추론(§5-4)** — 발화의 모호성 유형을 감지하고, 어떤 컨텍스트 신호를 우선 볼지 결정
3. **Weakness 진단(§7-3)** — 노드 상세의 `Ambiguous Language: HIGH` 판정 근거

### 2-4. 커버리지 지표

신규 발화 중 기존 pattern_cluster에 매핑되는 비율 = **Atlas Coverage**. 미매핑 발화는 Atlas 확장 큐로 자동 적재. 이 지표가 정체되면 TEACHER_LANGUAGE 소스 추가 발굴(S1 재가동) 신호다.

---

## 3. Intent Episode & Evidence Model

**핵심 전환:** episode는 정답 하나를 갖지 않는다. **evidence의 집합이 label distribution을 만든다.** "LLM이 상상한 의도"와 "인간이 확인한 의도"는 같은 episode 안에서도 다른 무게를 가진다.

### 3-1. Evidence — 시스템의 최소 학습 단위

```json
{
  "evidence_id": "EV_0918822",
  "episode_id": "EP_00018423",
  "intent_id": "play_expand",
  "polarity": "supports",
  "strength": 0.8,
  "evidence_type": "HUMAN_CORRECTION",
  "actor": {"actor_type": "TEACHER_TRAINER", "trainer_ref": "TR_031", "reliability": 0.87},
  "context": {"gym_mode": "correction_drill", "challenge_pack": "CP_0042", "adversarial": false},
  "created_at": 1783850060
}
```

**evidence_type 목록 — 고정 서열 없음:**

| 유형 | 생산자 |
|---|---|
| `SYNTHETIC_CONSENSUS` | Foundry S10 다중 에이전트 합의 |
| `WEAK_BEHAVIORAL` | Shadow 0b — 발화 후 행동 윈도우 신호 (Domain 수준) |
| `DOMAIN_RULE` | 규칙 기반 신호 (예: parent_message 화면 → COMMUNICATION 지지) |
| `HUMAN_CORRECTION` | Gym에서 교사가 "아니, ~였어"로 교정 |
| `HUMAN_CONFIRMATION` | Gym에서 교사가 제시된 의도를 확인 |
| `EXPERT_REVIEW` | 도메인 전문가 검수 |

**가중치 원칙: `REAL > SYNTHETIC` 같은 한 줄 서열을 만들지 않는다.** 단일 행동 신호(사진을 움직였다)보다 독립 Analyst 3 + Domain Rule + Skeptic + Judge가 일치한 Synthetic Consensus가 강할 수 있다. 실효 가중치는 `evidence_type × empirical reliability × agreement × conflict × domain`으로 계산하며 전부 config다(§10-1). `actor.actor_type` enum: `LLM_ANALYST / DOMAIN_EXPERT / TEACHER_TRAINER / STAFF_TRAINER / BEHAVIOR_SIGNAL / RULE_ENGINE`. `adversarial: true`(Break the Brain 산출)는 별도 태그로 자연 분포 학습에서 분리한다.

### 3-2. Episode v2 스키마

```json
{
  "episode_id": "EP_00018423",
  "ontology_version": "onto-1.0",
  "lang": "ko",
  "dataset_split": "TRAIN",
  "reliability_tier": "SILVER",
  "label_state": "LABELED",
  "origin_channel": "FOUNDRY_SYNTHETIC",
  "episode_creator_type": "FOUNDRY_PIPELINE",
  "primary_subject_type": "SIMULATED_TEACHER",
  "scenario_id": "CS_04412",
  "teacher_prompt": "다음엔 뭘 해주면 좋을까?",
  "persona_lens_used": "P_hypo_3",
  "label_distribution": {
    "play_expand": 0.57,
    "play_transition_next_step": 0.25,
    "write_activity_followup": 0.10,
    "UNKNOWN": 0.08
  },
  "consensus": 0.71,
  "disagreement_pairs": [["play_expand", "play_transition_next_step"]],
  "evidence_refs": ["EV_0918822"],
  "human_review": null,
  "dedup_hash": "e3b0c44298",
  "created_at": 1783850000
}
```

**축 분리 원칙 — 용도·신뢰·출생·상태는 서로 다른 개념이다:**

| 축 | 필드 | 값 |
|---|---|---|
| 어디에 쓰는가 | `dataset_split` | `TRAIN / VALIDATION / TEST / BENCHMARK_HOLDOUT` |
| 얼마나 믿는가 | `reliability_tier` | `UNVERIFIED / BRONZE / SILVER / GOLD` |
| 어디서 태어났는가 | `origin_channel` | `FOUNDRY_SYNTHETIC / FOUNDRY_AUGMENTED / GYM_HUMAN / EXPERT_AUTHORED / PRODUCTION_SHADOW / OFFICIAL_CORPUS / COMMUNITY_DERIVED` |
| 처리가 어디까지 왔는가 | `label_state` | §3-6 상태 기계 |

**provenance 3필드 분리** — episode 생성 주체를 evidence에서 역추론하지 않는다. 하나의 episode에 LLM_ANALYST·DOMAIN_EXPERT·TEACHER_TRAINER의 evidence가 섞여 있어도, "누가 이 record를 만들었는가"(`episode_creator_type`: `FOUNDRY_PIPELINE / GYM_SESSION / SHADOW_CONVERTER / HUMAN_ANNOTATOR`)와 "발화 주체가 누구인가"(`primary_subject_type`: `TEACHER / SIMULATED_TEACHER`)는 별개의 사실이다.

### 3-3. Reliability Tier 규칙

| Tier | 조건 |
|---|---|
| `UNVERIFIED` | 신호 부족 — 집계 전 기본값 (PRODUCTION 유입분의 초기 상태) |
| `BRONZE` | 합성 단독, 합의도 낮음 |
| `SILVER` | Aggregator 게이트 통과(§3-6): 독립 신호 ≥ 2 ∧ confidence ∧ conflict 기준 충족 |
| `GOLD` | **인간 검수 2인 이상 일치**(kappa 기록). 확정 라벨 보유 |

> 참고: tier에 `SYNTHETIC`을 두지 않는다 — 출생 정보는 `origin_channel` 축이 담당하며, 같은 개념을 두 축에 두면 축 분리 원칙이 무너진다.

### 3-4. 구조적 강제 (유지 확정)

- **DB constraint:**

```text
dataset_split = BENCHMARK_HOLDOUT
requires
  reliability_tier = GOLD
  AND label_state = LABELED
  AND origin_channel NOT IN (FOUNDRY_SYNTHETIC, FOUNDRY_AUGMENTED)
```

LLM이 상상한 교사 의도가 벤치마크 정답으로 둔갑하는 경로를 물리적으로 차단한다. KTIB(§8)는 `BENCHMARK_HOLDOUT`만 읽는다.

### 3-5. Evidence Diversity — 노드 밀도의 정의

```text
EvidenceDiversity(node)
= f( persona 분포 엔트로피
   × 상황(scenario) 커버리지
   × evidence_type 다양성 )
```

이 값이 **3D Brain에서 노드의 density**로 렌더링된다(§7-4). "합성 8,400개 + 인간 32개"인 노드는 크지만 성기게 보인다 — 그게 정확한 상태 표현이다.

### 3-6. Label State Machine + Aggregator — 상태와 품질을 섞지 않는다

`label_state`는 **처리 워크플로 상태**이고 `reliability_tier`는 **라벨 품질**이다. `{"label_state": "LABEL_CANDIDATE", "reliability_tier": "UNVERIFIED"}`가 정상적으로 공존한다.

```text
UNLABELED                신호 없음 (예: shadow 무행동 케이스)
  ↓ evidence 유입
EVIDENCE_ACCUMULATING    evidence 축적 중
  ↓ 최소 신호 수 도달
AGGREGATION_READY        집계 대상
  ↓ Label Aggregator 실행
LABEL_CANDIDATE          집계 통과 — tier 승격 심사 대상 (SILVER까지)
REVIEW_REQUIRED          conflict 초과 or 저신뢰 — 사람 검수 큐
  ↓ 사람 검수
LABELED                  확정 (GOLD은 2인 일치 시)
REJECTED                 폐기 판정 — evidence는 보존, episode만 학습 제외
```

**Label Aggregator 게이트**(전부 config, §10-1): 독립 labeling 신호 수 ≥ `min_label_functions` ∧ `aggregate_confidence ≥ 임계` ∧ `conflict_score ≤ 임계`. Snorkel류 weak supervision과 같은 전제 — 개별 신호는 부정확하고 서로 상관될 수 있으므로, 신호 수·합의·충돌 구조를 함께 본다. **PRODUCTION 유입분은 이 기계를 통과하기 전까지 절대 SILVER가 되지 않는다.**

---

## 4. Persona Discovery

**원칙: 8축은 가설이다. 확정은 데이터가 한다.**

### 4-1. 발견 절차 5단계

```text
[1] 가설 lens 생성      기존 8축을 Teacher Simulator의 생성 다양화 도구로만 사용 (라벨 아님)
[2] 상호작용 축적       Gym 세션에서 trainer별 교정·선택·수락 패턴 로그 수집
[3] 행동 벡터화         trainer × (intent 선택 편향, 교정 방향, 응답 선호) 벡터 구성
[4] 클러스터 발견       밀도 기반 클러스터링(HDBSCAN 등, 알고리즘·파라미터 = config)
[5] 가설 대조·개정      발견된 클러스터 ↔ 8축 가설 비교 → 축 폐기/병합/신설 → persona_vector v2 확정
```

### 4-2. 운영 규칙

- Persona는 **prior에만** 작용한다. prior 영향에 상한(`config.persona_prior_cap`)을 둔다 — 필터버블(습관적 intent로만 예측) 방지.
- 지표 쌍: **Persona Lift**(persona 덕에 맞춘 비율)와 **Persona Harm**(persona 탓에 틀린 비율)을 항상 함께 측정. Harm > Lift인 클러스터는 prior 비활성화.
- **Cold start:** 신규 trainer는 population prior에서 시작, 교정 k회(`config.persona_warmup`) 누적 시 개인 prior 분기.
- Persona Overlay(§7-6)로 클러스터별 뇌 활성 분포를 시각 비교한다 — "교사마다 뇌의 어느 부위를 쓰는가".

---

## 5. Seed Brain 내부 구조

여기가 기술 경쟁력이다. Brain은 블랙박스가 아니라 `노드 + 방향성 confusion edge + prior 테이블 + 버전`의 투명한 구조물이며, 3D Brain(§7)은 이 구조를 **그대로** 렌더링한 것이다. 개발 총괄의 13개 질문에 순서대로 답한다.

### 5-1. Intent node는 무엇인가

온톨로지의 intent와 1:1인 **상태 저장소**다. v1에서 노드 수 = intent 수(~100). 수천 개의 점은 장식 파티클 레이어(§7-5)이지 의미 노드가 아니다.

```json
{
  "node_id": "N_visual_naturalize",
  "intent_id": "visual_naturalize",
  "region": "VISUAL",
  "definition_ref": "onto-1.0#visual_naturalize",
  "exemplars": {"count": 48, "index": "vector_store", "diversity": 0.41},
  "counter_exemplars": [{"against": "text_naturalize", "count": 12}],
  "evidence_stats": {"synthetic": 8402, "human_confirmed": 32, "gold": 231, "expert": 6},
  "priors": {"domain_prior_ref": "domain_prior_table", "persona_prior_ref": "persona_prior_table"},
  "performance": {"heldout_accuracy": 0.31, "calibration_ece": 0.18, "last_arena_run": "AR_0091"},
  "coverage": {"scenario_coverage": 0.382, "persona_entropy": 0.22, "atlas_ambiguity": "HIGH"},
  "pending_evaluation": true
}
```

### 5-2. node 하나는 무엇을 기억하는가

5종: ① 정의 참조(온톨로지) ② **exemplar store** — 대표 에피소드 임베딩 K개, 추론 시 retrieval 근거 ③ **counter-exemplar** — 혼동 상대와의 대비 사례 ④ evidence 통계(§3-1 유형별 카운트) ⑤ 성능·커버리지 통계(Arena 산출만 기록).

### 5-3. Persona prior는 어디에 저장되는가

**노드가 아니라 별도 테이블 2장.** population: `(persona_cluster × intent) → prior`, individual: `(trainer_ref × intent) → prior`. 추론 시 노드 점수에 **밖에서** 곱한다(§5-5의 이유).

### 5-4. Prompt signal은 어떻게 node를 활성화시키는가

```text
[1] RETRIEVAL      발화 임베딩 ↔ 노드 exemplar 유사도 + Atlas 패턴 매치
                   → 활성 후보 노드 ≤ 20개로 축소
[2] LLM SCORER     후보 노드 + 명시된 컨텍스트 신호(선택 대상, 직전 행동, 화면 요약)
                   → 후보별 점수 0~1 + 근거 문장
[3] PRIOR 재정렬    score × persona_prior × domain_prior  (cap 적용)
[4] 정규화          → 후보 목록 + confidence + margin(top1−top2)
```

Atlas의 역할: 발화의 모호성 유형을 먼저 판정하고(L2), 그 유형을 푸는 신호(L3)를 [2]의 프롬프트에서 우선순위로 명시한다.

### 5-5. Context signal과 Persona signal은 어떻게 합산되는가

개념 수식:

```text
Score(i) = Activation(i | prompt, workspace, actions) × PersonaPrior(p, i) × DomainPrior(ctx, i)
```

v1 구현의 정직한 선언: 신호 가중치를 학습하지 않는다. Activation은 LLM Scorer가 통째로 판별하고, **prior는 LLM 밖에서 곱한다.** 이유 3가지 — ① Persona Lift/Harm을 측정 가능 ② cap·롤백 가능 ③ LLM 프롬프트 안에 persona를 넣으면 통제 불능. 신호별 기여는 전건 로그로 남겨, 이후 학습형 결합(소형 scorer)의 훈련 데이터로 쓴다.

### 5-6. Confusion pair는 Brain 내부에서 어떻게 연결되는가

**방향성 edge**다: `P(예측=B | 정답=A) ≠ P(예측=A | 정답=B)`.

```json
{
  "edge_id": "CE_0331",
  "from_true": "visual_naturalize",
  "to_predicted": "text_naturalize",
  "confusion_rate": 0.31,
  "state": "observed",
  "origin": "SKEPTIC",
  "evidence_runs": ["AR_0090", "AR_0091"],
  "contrast_exemplars": [
    {"utterance": "이거 자연스럽게 해줘 (사진 2장 선택)", "true_intent": "visual_naturalize"},
    {"utterance": "이 문장 자연스럽게 해줘 (문단 선택)", "true_intent": "text_naturalize"}
  ]
}
```

상태 기계: `hypothesized`(Skeptic 제안, S8) → `observed`(Gym 교정 통계) → `confirmed`(Arena 오답 매트릭스 검증). edge에 저장된 contrast exemplar 쌍이 C형 강화(§6)의 교재가 된다.

### 5-7. 새 Episode가 들어오면 어느 node에 귀속되는가

- 확정 라벨(GOLD) → 해당 노드의 exemplar 후보. 채택 기준: 기존 exemplar들과 임베딩 거리 ≥ `config.exemplar_min_dist` (중복 exemplar로 다양성을 부풀리지 않기 위해).
- 분포 라벨(BRONZE/SILVER) → `label_distribution` 상위 노드들에 **가중 귀속** — evidence 통계에만 반영, exemplar로는 채택하지 않는다.

### 5-8. 새로운 Intent가 발견되면 node가 새로 생기는가

**자동 생성 금지** (원칙 9). 경로는 하나뿐이다:

```text
UNKNOWN·미분류 발화 → unassigned pool
  → 주간 클러스터링 → "노드 후보" 제안 리포트
  → 도메인 전문가 승인
  → 온톨로지 minor 버전 업 + 노드 생성 (거버넌스 이벤트 기록)
```

### 5-9. node끼리 cluster를 만드는가

의미 구조의 권한은 온톨로지(domain → intent 2계층)에만 있다. 임베딩 클러스터는 ① 3D 공간 배치 계산 ② 온톨로지 개정 제안(어떤 intent가 사실상 겹치는가) — 두 용도뿐이며 추론에 직접 개입하지 않는다.

### 5-10. Brain region은 고정인가, 성장하는가

7개 region은 **v1 고정** — 3D 의미 좌표계의 안정성을 위해서다(노드가 늘어도 PLAY는 항상 같은 자리). region 내부 노드 수는 성장한다. region 신설·개편 = 온톨로지 major 버전.

### 5-11 ~ 5-13

"Train This Region의 데이터 선택", "교정 20개 = 정확도 상승인가", "v0.38 → v0.39는 언제인가"는 강화의 정의 그 자체이므로 §6에서 답한다.

---

## 6. Growth Loop — "강화한다"의 정의

**"20문제 풀었으니 정확도 +5%"는 이 시스템에 존재하지 않는다.** 훈련은 evidence를 만들고, 정확도는 Arena만 바꾼다(원칙 8). "강화"는 하나의 행위가 아니라 진단에 따라 갈라지는 4가지 전략이다.

### 6-1. 강화 4유형

| 유형 | 발동 진단 | 사람 필요 | 하는 일 | 즉시 변하는 것 | 밝기(정확도) 변화 |
|---|---|---|---|---|---|
| **A. Data Coverage** | scenario coverage LOW | 아니오 | Foundry(S5~S10)에 해당 노드 시나리오 생성 주문 | coverage, node size | 없음 |
| **B. Human Evidence** | synthetic ≫ human (예: 8,400 vs 32) | **예** | 교사 검증 문제 우선 출제 | density, gold count | 없음 |
| **C. Confusion** | edge confusion_rate ≥ config | **예** | contrast exemplar 기반 구분 훈련만 집중 | edge 통계, counter-exemplar | 없음 |
| **D. Model** | 유효 신규 evidence 임계 충족 | 아니오 | candidate brain 빌드 → Arena 시험 | — | **Arena 통과 시에만** |

### 6-2. 전체 루프

```text
CLICK BRAIN NODE
        ↓
DIAGNOSE WEAKNESS TYPE        ← §7-3 진단 엔진 (4축)
        ↓
SELECT TRAINING STRATEGY      ← A/B/C/D 매핑 (복합 진단이면 조합, 예: C+B)
        ↓
GENERATE / RETRIEVE CHALLENGES ← Challenge Pack 생성
        ↓
HUMAN INTERACTION             ← Gym (A·D는 이 단계 생략)
        ↓
EVIDENCE ACCUMULATION         ← §3-1 evidence 적재 (trainer 신뢰도 가중)
        ↓
VALIDATION                    ← 중복·적대 태그·신뢰도 필터
        ↓
BRAIN CANDIDATE UPDATE        ← exemplar/prior/edge 갱신본 = candidate
        ↓
ARENA TEST                    ← KTIB gold 전체 재평가
        ↓
     PASSED?
   YES       NO
    ↓         ↓
ACTIVATE    REJECT
NODE        (evidence는 보존, 원인 리포트)
```

### 6-3. 훈련 우선순위 (질문 11의 답)

전략이 선택되면 문항 샘플링 순서: ① heldout 정확도 최저 intent ② confusion_rate 최고 edge ③ 최근 성능 하락 intent ④ evidence 최소 intent ⑤ persona 영향 큰 intent ⑥ 서비스 중요도. 순위 가중치는 config.

### 6-4. Challenge Pack 스펙

```json
{
  "pack_id": "CP_0042",
  "origin": {"trigger": "observatory_click", "node": "visual_naturalize", "diagnosis": ["CONFUSION_HIGH", "GOLD_LOW"]},
  "strategy": ["C_CONFUSION", "B_HUMAN_EVIDENCE"],
  "target_edges": [{"from_true": "visual_naturalize", "to_predicted": "text_naturalize"}],
  "items": 20,
  "difficulty_curve": "medium_to_hard",
  "persona_mix": ["PC_1", "PC_3", "PC_4", "PC_6", "PC_7"],
  "delivery_modes": ["choose_right_meaning", "correction_drill"],
  "expected_yield": {"human_evidence": 20, "contrast_pairs": 12}
}
```

Gym의 6개 모드는 독립 기능이 아니라 **Challenge Pack의 배달 형식**이다(§8-1).

### 6-5. 교정 20개가 들어오면 정확도가 올라간 것인가 (질문 12의 답)

아니다. 교정은 evidence 축적이다. 즉시 변하는 것: coverage·density·evidence 카운트·edge 통계(= 3D의 size/density/edge). **밝기는 변하지 않고, 노드에 `pending_evaluation` 링이 켜진다** — "훈련됨, 검증 대기" 상태의 시각 표현. Fast 반영(개인 prior 미세 조정)은 허용하되 안전 규칙: 최소 표본 `n ≥ config.fast_min_samples`, 세션당 변화 `≤ config.fast_delta_cap`, 주간 decay, 버전 롤백 — **전부 실험 파라미터이지 확정값이 아니다.**

### 6-6. v0.38 → v0.39는 언제 발생하는가 (질문 13의 답 — Version Gate)

```json
{
  "version": "v0.39-rc1",
  "base": "v0.38",
  "trigger": "D_MODEL: new_gold 328, new_valid_episodes 2314",
  "delta": {"updated_nodes": ["visual_naturalize", "text_naturalize"], "updated_edges": ["CE_0331"]},
  "arena_result": {"global_delta": "+2.1pp", "region_regressions": [], "critical_pair_delta": "-9pp confusion"},
  "decision": "promote"
}
```

- **candidate 생성 조건**(config): 신규 GOLD ≥ 임계, 또는 타깃 confusion pair 개선 캠페인 완료
- **promote 규칙:** global 상승 ∧ region 회귀 없음 ∧ (critical intent 정확도 악화 없음)
- promote 순간에만 뇌 전체 공명(Full Brain Resonance) 애니메이션 발동 — 버전 업의 시각 서명
- reject 시 evidence는 전량 보존, 실패 원인 리포트(어느 노드가 회귀했는가) 생성

### 6-7. End-to-End Trace — 어두운 점 하나를 클릭하면 정확히 무슨 일이 일어나는가

```text
[0] 관찰   3D Brain 회전 중 visual_naturalize 노드가 어둡다
           (brightness 31% = Arena run AR_0091의 heldout 정확도)

[1] 클릭   진단 엔진(§7-3) 실행:
           CONFUSION_HIGH (→text_naturalize 31%, edge CE_0331 state=observed)
           + GOLD_LOW (gold evidence 231 < config.gold_low_threshold... 기준 미달 판정)

[2] 전략   진단 → 강화 유형 매핑(§6-1): C(Confusion) + B(Human Evidence)
           → Challenge Pack CP_0042 생성:
             문항 20 = contrast 12(CE_0331의 contrast_exemplars 기반) + 검증 8
             난이도 medium→hard, persona mix 5클러스터
             배달 모드: choose_right_meaning + correction_drill

[3] 출제   Gym trainer 큐로 발행 (teacher_trainer 우선 배정)

[4] 상호작용  세션 산출 → evidence 20건 적재:
             HUMAN_CORRECTION 7 + HUMAN_CONFIRMATION 13
             (actor_type=TEACHER_TRAINER, trainer reliability 가중, adversarial=false)

[5] 집계   Label Aggregator(§3-6):
           episode 12건 label_state → LABELED
           2인 일치 확인된 5건 tier SILVER → GOLD 승격
           나머지 conflict 2건 → REVIEW_REQUIRED (사람 검수 큐)

[6] 즉시 반영  노드 size ↑ (evidence 총량), density ↑ (persona 엔트로피 개선)
             + pending_evaluation 링 점등
             ※ brightness는 변하지 않는다 (원칙 8)

[7] 후보   Version Gate(§6-6) 조건 충족 (누적 new_gold ≥ config.min_new_gold)
           → candidate v0.39-rc1 빌드:
             exemplar 3건 추가(diversity 기준 통과분), counter-exemplar 5건,
             edge CE_0331 contrast_exemplars 갱신, persona prior 미세 조정(cap 내)

[8] 시험   Arena 전체 실행: KTIB(BENCHMARK_HOLDOUT ∧ GOLD ∧ 비합성) 재평가
           기록: model_version + ontology_version + persona_state_version
                + visual extractor_version (replay 무결성 4종)

[9] 판정   promote 규칙: global 상승 ∧ region 회귀 없음 ∧ critical 악화 없음
           PASS → v0.39 승격 → 노드 brightness 31%→44%, edge flicker 31%→22%,
                  pending 링 소등, Full Brain Resonance 1회
           FAIL → reject: evidence 전량 보존, 회귀 노드 원인 리포트,
                  candidate 폐기 (다음 campaign의 진단 입력으로)
```

이 체인의 어느 단계도 건너뛸 수 없다 — 특히 [4]→[6]에서 밝기가 바로 오르는 지름길은 구조적으로 존재하지 않는다.

---

## 7. 3D Brain — 시스템의 네비게이션

**정체성:** 지표 시각화 화면이 아니다. **시스템의 첫 화면이자 모든 작업의 진입점.** 훈련 시작, 데이터 검수, 벤치마크 실행, 버전 확인 — 전부 뇌에서 시작한다. 별도 메뉴는 최소화한다. Brain 내부 구조(§5)가 곧 렌더링 대상이므로, 보이는 것과 실제 상태가 1:1이다.

### 7-1. Zoom 0 — 메인 화면

```text
                KINDER INTENT BRAIN v0.21

                         61.8%

                   · · ● ● ·
              · ● ● ● ● ● ● ·
           · ● ● ● ● ● ● ● ● ·
         · ● ● ● ● ● ● ● ● ● ●
           ● ● ● ● ● ● ● ● ●
