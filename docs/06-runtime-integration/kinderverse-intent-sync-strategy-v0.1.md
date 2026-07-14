# 킨더버스 ↔ 킨더브레인 의도 싱크 전략 (Intent Sync Strategy)

| 버전 | 일자 | 변경 요약 |
|---|---|---|
| v0.1 | 2026-07-15 | 최초 작성 — 양 저장소 전수 감사 기반. 이중 계층 원칙·크로스워크·Shadow 0a 캡처·8번째 영역(STUDIO) 신설 검토. (사용자 승인 범위: 전략 문서 작성까지 — 코드 구현·마스터 문서 개정은 별도 승인) |

> **지위**: 이 문서는 설계 제안이다. 제1 설계 문서(`docs/01-foundry/kinder-intent-foundry-growth-system-v1.0.md`)와
> 충돌하면 제1 설계 문서가 이긴다. 여기 담긴 마스터 문서 개정안(§9)은 **제안일 뿐이며 사용자 승인 전에는 효력이 없다**.
>
> **HOLD 고지**: live rollout(Suggest/Assist/Auto)은 여전히 **PARTIAL HOLD**다. 이 문서의 어떤 내용도
> live 서빙 코드를 정당화하지 않는다. 다루는 것은 어휘 정렬(온톨로지·크로스워크)과 Shadow 0a/0b까지다.
> 랩의 `/v1/intent/infer`가 mode=gym 외를 501로 거부하는 현 상태(`backend/app/api/infer.py:100`)는 유지된다.

---

## §1 배경·목표

**두 시스템의 역할 분담.** 킨더버스(`D:\claude_project\kinderverse concept`)는 유아교사의 공간 단위
올인원 생성 워크스페이스다 — 교사가 자연어로 말하거나 보드 객체를 선택해 명령하면, 3계층 스택이
해석해 전문 에이전트로 라우팅하고 결과를 레지스트리 제약 AUI로 그린다. 킨더브레인(이 저장소)은
그 해석의 첫 단추 — **짧고 애매한 발화 + 화면 컨텍스트 + 직전 행동 + 성향으로 의도를 추론** — 를
서비스에서 분리된 실험실에서 검증 가능하게 만드는 프로젝트다.

**문제.** 두 시스템의 의도 어휘가 서로 다르게 자랐다:

- 킨더버스: **기능 수준(feature-level)** 의도 — ContentIntent 8종(worksheet·coloring·image·plan·letter·
  record_story·record_observation·mindmap, `src/ai/intent-lexicon.ts`) + 보드 조작 board.* 9종 +
  하위 분류(활동지 ~19종, 게임 방식 12종, 슬라이드, 영상, 동화책, 수업모드 …).
- 킨더브레인: **필요 수준(need-level)** 의미 의도 63종(7영역×9) + UNKNOWN (`seeds/ontology_v1.yaml`,
  onto-1.1). 서비스 액션과의 연결 고리인 `proposed_action`(`schemas/infer_response.schema.json`)은
  계약에만 정의된 **빈 자리표시자** — 어떤 코드도 채우지 않는다.

이 간극을 방치하면: 뇌가 KTIB 96%를 달성해도 그 추론이 서비스의 어떤 버튼과도 연결되지 않고,
서비스의 실사용 발화 분포(교사가 실제로 뭐라고 말하는가)는 뇌 훈련에 한 줄도 들어오지 않으며,
두 어휘가 각자 진화하다 조용히 어긋난다. **오판은 교사에게 편리가 아니라 복잡함을 준다** — 이것이
킨더브레인의 존재 이유이므로, 어휘 싱크는 부가 기능이 아니라 전제 조건이다.

**싱크의 3대 목표:**

1. **분포 학습** — 뇌가 킨더버스의 실제 교사 발화·컨텍스트 분포를 본다 (현재 실교사 데이터 0건).
2. **실행 가능성** — 뇌의 intent 추론이 서비스가 실행할 수 있는 액션 기술자(`proposed_action`)로 번역된다.
3. **시끄러운 실패** — 두 어휘가 따로 진화해 어긋나면 조용히 오동작하는 게 아니라 양쪽 CI가 깨진다.

---

## §2 이중 계층 원칙 — 의도(need)와 액션(feature)을 분리한다

**원칙: 뇌 의도는 need-level을 유지하고, 서비스 액션 매핑은 온톨로지 밖의 별도 아티팩트(크로스워크)로 둔다.**

근거는 이 저장소가 이미 확립한 전례다. 리스크 모델(`seeds/risk_model_v1.yaml`)의 머리말은 등급이
"평가 정책이지 intent의 의미가 아니"라서 온톨로지 밖에 두었다고 명시한다 — 등급을 고칠 때마다
`ontology_version`(arena run 재현 4축의 하나)이 올라가 과거 채점이 전부 비교 불능이 되는 걸 막기
위해서다. **의도→액션 매핑도 정확히 같은 범주다: 실행 정책이지 의미가 아니다.** 킨더버스가 기능
이름을 바꾸거나 파라미터를 추가할 때마다 온톨로지가 범프되어서는 안 된다.

### 2-1 뇌 의도 승격 판정 규칙 (어떤 서비스 기능이 뇌 의도가 되는가)

서비스 기능이 뇌 의도로 승격되려면:

1. **언어적 모호성** — 자연스러운 교사 발화가 기존 의도의 positive_examples와 충돌한다
   (임베딩 유사도로 검증 가능). 예: "영상"(Veo 생성 vs 유튜브 검색), "짝맞추기"(활동지 vs 게임),
   "정리해"(보드 정렬 vs 문서 요약 vs 사진 정리) — 이 충돌들은 킨더버스
   `intent-lexicon.ts`의 주석 자체가 기록한 실증 혼동 사례다. **그리고**
2. **필요-안정성** — 기능 스킨이 아니라 안정적인 교사 니즈다. 활동지 유형(~19종), 게임 방식(12종),
   덱 테마는 서비스 릴리스 주기로 바뀌는 스킨이므로 **항상 파라미터**이지 의도가 아니다. **또는**
3. **리스크** — 오판이 rm-1.0의 E(외부 유출)/D(파괴)/R(공적 기록) 축을 건드린다.

### 2-2 fast-path 경계 — 뇌가 배우지 않는 것

킨더버스의 결정적 정규식 계층(Layer 1)이 100% 정확도로 처리하는 표면은 뇌 의도가 아니다:

| 표면 | 처리 | 이유 |
|---|---|---|
| 보드 조작 8종 (resize·move·group·align·arrange·duplicate·recolor·match_size) | fast-path 유지 | 결정적·무모호·즉시 실행. 추론을 끼우면 지연+불일치 채널만 생긴다 |
| `delete` | **분할** | 선택된 보드 노드 삭제(undo 가능, L1) = fast-path. 워크스페이스·기록 삭제 = 뇌 게이트 `op_workspace_delete`(CRITICAL-D). 스코프 모호("이거 다 지워줘", 선택 없음) ⇒ 뇌 `clarify` |
| vessel(메모·노트·텍스트), URL/미디어 로드, 배경제거 정규식 | fast-path 유지 | 결정적 |

이 제외는 크로스워크의 `fastpath_surface` 블록(§5)에 **명문화**한다 — "측정 안 함"이 깜빡이 아니라
감사 가능한 결정이 되도록. fast-path 발화도 Shadow 0a 캡처에는 포함된다(§6) — 뇌가 분포를 보되
KTIB 측정 대상은 아니다.

---

## §3 킨더버스 표면 감사 결과

### 3-1 이미 커버되는 것 (크로스워크만 필요, 온톨로지 무변경)

| 킨더버스 표면 | 커버하는 뇌 의도 | 비고 |
|---|---|---|
| plan (계획안·활동추천) | `doc_plan_draft`, `play_transition_next_step`, `play_expand` | 뇌가 서비스의 단일 'plan' 버킷보다 **세밀하게** 분해 (다:1 매핑) |
| letter (통신문·공지) | `doc_notice_draft`, `comm_draft_parent_notice` | |
| image (이미지·환경판) | `visual_image_generate` | |
| record_observation | `doc_observation_record`, `obs_record_moment` | |
| record_story (놀이이야기) | `write_activity_followup` + `params.record_mode='story'` | 파라미터 우선 — UNKNOWN 풀 관찰 |
| 수업모드 시작 | `comm_present_to_children` | 정의가 이미 "교실 대형 화면에 크게 띄워 표시" |
| 우리반·캘린더·갤러리·문서편집·꾸미기 | `obs_search_records`, `obs_summarize_child`, `op_schedule_update`, `visual_photo_organize`, `text_naturalize`, `visual_decorate` 등 | |
| 프로젝트 수업 | `doc_plan_draft` + `params.plan_type='project'` | |
| 동화책 | `play_scenario_generate` + `params.artifact_format='storybook'` | positive example에 이미 이야기 생성 존재. 파라미터 우선 |
| **주제 패키지** (`buildPlayPackage`) | **의도가 아니라 `intent_plan`** | 계약의 다의도 합성(relation=parallel): 계획+이미지+활동지+영상+게임+웹자료. 단일 intent_id 기반 KTIB v1에서는 **측정 불가** — 헤드라인 지표에서 제외하고 다의도 KTIB 확장은 후속 과제로 명시 |

### 3-2 진짜 갭 — 신설 의도 7종 제안

| intent_id | 영역(7영역 기준) | 정의 한 줄 | 필수 confusable_with |
|---|---|---|---|
| `visual_worksheet_generate` | VISUAL | 주제·연령을 입력으로 인쇄용 활동지(색칠·선잇기·오리기·짝맞추기 등)를 생성한다 | `visual_image_generate`, `play_game_generate`, `op_material_prepare` |
| `visual_video_generate` | VISUAL | 주제 설명이나 이미지를 입력으로 활동용 짧은 영상을 생성한다 | `visual_image_generate`, `op_external_resource_search`('영상' 다의성) |
| `doc_slides_draft` | DOCUMENT | 수업 주제를 입력으로 발표·수업용 슬라이드 초안을 생성한다 | `doc_plan_draft`, `visual_image_generate`, `comm_present_to_children` |
| `play_game_generate` | PLAY | 주제·연령을 입력으로 아이들이 조작하며 노는 인터랙티브 게임을 생성한다 | `visual_worksheet_generate`('짝맞추기' 충돌), `play_scenario_generate` |
| `play_topic_web_generate` | PLAY | 주제·유아 관심사를 입력으로 생각그물·주제망(마인드맵)을 생성한다 | `play_expand`, `doc_plan_draft` |
| `op_external_resource_search` | OPERATION | 활동 주제에 맞는 외부 자료(유튜브·웹)를 검색해 제시한다 | `op_workspace_search`(내부/외부), `visual_video_generate` |
| `refl_child_guidance_consult` | REFLECTION | 교사가 묘사한 아동의 걱정 행동에 발달 기반 지도 방안을 상담 형식으로 제안한다 | `obs_detect_behavior_change`, `refl_support_need_scan` |

결과: 63 → **70 의도**. 색칠도안(coloring)은 `visual_worksheet_generate`의
`params.worksheet_type` 파라미터다(사용자 확정).

**같은 범프에 반드시 포함할 예시 이동**: `visual_image_generate`의 positive example
"우주 주제 색칠도안 하나 생성해줘"(`seeds/ontology_v1.yaml:534`)는 신설 활동지 의도로 **이동**해야
한다 — 남겨두면 새 의도에 대한 심어진 골드 라벨 모순이 된다. 편집은 규칙대로 CSV
(`seeds/ontology_examples_draft.csv`) + `scripts/apply_ontology_examples.py --write` 경유
(YAML 직접 편집 금지).

---

## §4 영역 정책 — 8번째 영역 STUDIO 신설 검토 ★핵심 결정 절

사용자 지시로 "7영역 유지" 권장안 대신 **8번째 영역 신설을 정식 검토**한다. 이 절이 그 검토의
전문이며, go/no-go는 §10의 사용자 결정란에서 확정한다.

### 4-1 신설안: `STUDIO` — 자료 만들기

- **의미**: "만들어줘" 계열 생성 스튜디오 — 인쇄물·미디어·인터랙티브 콘텐츠 생성이라는 교사 니즈의
  독립 축. 킨더버스의 핵심 가치("자료만 제작해주는 서비스가 아니라 주제에 따른 니즈를 한번에 제공")
  에서 '제작' 축이 운영실·3D 뇌에서 **별도 영역의 실력으로 보이는** 제품 서사 가치가 있다.
- **한국어 라벨**: "자료 만들기". **후보 색**: `#f87171`(coral) — 기존 7색(#4ade80 초록, #38bdf8 하늘,
  #fb923c 주황, #c084fc 보라, #f472b6 분홍, #facc15 노랑, #22d3ee 시안)과 구분되는 잔여 색상축.
  단 대시보드 하락 세그먼트(#fb7185)와의 근접은 구현 시 dataviz 검증기로 확인할 것.
- **후보 3D 중심좌표**: `[0, -0.42, 0.55]`(아래-앞 사분면 — 기존 7좌표가 비운 슬롯. DOCUMENT
  [0,-0.08,0.8]·REFLECTION [0,-0.48,-0.68]과의 간섭은 `brainShape`/`layout` 스냅샷으로 검증 필요).

### 4-2 수용 범위 — A안 vs B안

| | **A안: 최소 (신설 의도만 수용)** | **B안: 정합 (기존 생성 의도 이동 포함)** |
|---|---|---|
| STUDIO 구성 | 신설 생성형 5종: worksheet·video·slides·game·mindmap → `studio_*`로 개명 | A안 + 기존 `visual_image_generate`(및 생성 성격의 기존 의도 심사) 이동 |
| 의미 경계 | 흐림 — "이미지 생성은 VISUAL인데 활동지 생성은 STUDIO"인 비대칭 | 순수 — 생성=STUDIO, 사진·꾸미기=VISUAL로 정리 |
| 기존 노드 영향 | 없음 (신설만) | `visual_image_generate` 노드의 region 변경 → 영역 신뢰도 이력 단절, VISUAL 영역 집계 축소 |
| KTIB 영향 | 신설분 문항 필요(공통) | + 기존 문항의 intent_id는 유효하나 영역별 집계축이 이동 |
| 영역 크기 | STUDIO 5, 기존 7영역 중 일부 9 유지 | STUDIO 6+, VISUAL 8로 감소 — 9±균형 재설계 필요 |

경계 사례의 영역 배치(사용자가 승인한 권장안: 마인드맵=PLAY, 슬라이드=DOCUMENT)는 **7영역
유지 시의 배치**다. STUDIO 채택 시 두 의도는 '생성물' 성격이 우세해져 STUDIO로 이동하는 것이
정합적이며, 최종 배치는 §10 결정과 함께 확정한다.

### 4-3 공통 비용 — major 버전(onto-2.0) 이벤트의 전체 목록

§5-10("7개 region은 v1 고정 — region 신설·개편 = 온톨로지 major 버전")에 따라 다음이 **전부** 필요하다:

1. **마스터 문서 §5-10 개정** + Change Log 항목 (사용자 승인 필수 — 작업 규칙 5).
2. 백엔드 `CANONICAL_DOMAINS` 튜플 확장 (`backend/app/core/ontology.py:17` — 검증기가 순서·구성까지 잠금).
3. **DB CHECK 마이그레이션**: `brain_nodes.region`·`situation_frames.domain`
   (`db/migrations/001_init.sql:22,107`의 CHECK + ORM `DOMAIN_CHECK` 문자열, `models/foundry.py:10`).
4. 스키마 region enum 3곳: `schemas/brain_node.schema.json`, `infer_response.schema.json`,
   프론트 TS `RegionId` 유니온.
5. 프론트 `frontend/src/brain3d/regions.ts` — 색·라벨·3D 좌표 추가, `regions.test.ts` 스냅샷 갱신,
   `brainShape`/`layout` 간섭 검증.
6. 영역 집계 코드: `backend/app/api/observatory.py`(region_acc 시딩), `observatory/aggregate.py`,
   `arena/stages.py`(Stage 사다리 — 신설 영역은 Stage 0 Dormant로 시작, 교차영역 혼동 그래프 재형성).
7. **`ontology_version` major → 과거 arena run 전부와 비교축 단절.** 완화책: §7의 core-63 고정
   슬라이스 병행 보고. (참고: 현재 arena_runs 0건이라 **지금이 단절 비용이 가장 싼 시점**이기는 하다 —
   첫 실채점 전에 결정하면 잃는 이력이 없다.)
8. B안이라면 + 이동 대상 노드의 region UPDATE 마이그레이션과 governance_events 기록.

### 4-4 판단 기준·권고

- **기능상 결과는 동일하다**: 7영역+minor(신설 7종을 기존 영역에 배치)로도 크로스워크·Shadow·측정은
  전부 같은 힘으로 작동한다. STUDIO의 실익은 순수하게 **가시성·제품 서사**(운영실에서 "자료 제작
  실력"이 별도 축으로 보임)와 **의미 응집**(생성 니즈가 4개 영역에 흩어지지 않음)이다.
- **비용은 위 4-3 전부** + 앞으로 영역이 8이 되는 순간 "영역은 늘어나는 것"이라는 선례가 생겨
  §5-10의 고정 원칙이 약해진다.
- **대안 경로(권장 기본값)**: 지금은 7영역+minor로 가고, **영역 압력 트리거**를 마스터 문서에
  명문화한다 — *"주간 클러스터링에서 UNKNOWN 클러스터가 반복적으로 어느 영역에도 검수자 합의
  배정이 불가능할 때, major 버전(영역 신설) 논의를 개시한다."* Shadow 0a 실데이터가 근거를
  만들면 그때 STUDIO를 연다 — 추측이 아닌 증거 기반 major.
- 단, **지금 열겠다면 최적 타이밍**이라는 사실도 인정한다(arena_runs 0, KTIB 문항의 intent_id는
  영역 개편에도 유효). 결정은 §10-1.

---

## §5 크로스워크 아티팩트 — `seeds/intent_action_map_v1.yaml`

의미(온톨로지)·리스크(rm)·**실행(크로스워크)** 3정책 파일이 `seeds/`에 나란히 사는 구조.
킨더버스는 이 파일을 절대 직접 편집하지 않고 **생성된 TS**만 소비한다.

```yaml
# seeds/intent_action_map_v1.yaml — intent → 서비스 액션 크로스워크 (실행 정책, 의미 아님)
crosswalk_version: iam-1.0
ontology_version: onto-1.2      # 핀 — 어긋나면 validate_schemas.py가 시끄럽게 실패
risk_model_version: rm-1.1      # 핀 — 자율성 게이트 정합 검사용
service_vocab_version: kv-lex-1 # 킨더버스 ContentIntent+board.* 목록 핀

mappings:                        # ① 뇌 의도 → 서비스 액션 (proposed_action의 원천)
- intent_id: doc_notice_draft
  action_type: writing.letter_draft      # 킨더버스 capability id
  route: writing                         # RouteTarget (src/ai/contract.ts)
  params_template: { kind: letter }
  slots: [{ name: topic, required: true }]   # 뇌가 발화에서 추출해 params에 주입
  autonomy_level: L1                     # L1 자동 / L2 확인 / L3 사람 게이트
  undoable: true
  preview_available: true
- intent_id: op_notice_send
  action_type: comm.notice_send
  route: null                            # 생성 라우트 아님 — 직접 op
  autonomy_level: L3                     # CRITICAL-E ⇒ L3 (검증기 강제)
  undoable: false
  preview_available: true

service_to_brain:                # ② 서비스 어휘 → 뇌 의도 (약한 라벨 변환용)
- { service_intent: worksheet, mapping_type: exact,  intent_ids: [visual_worksheet_generate] }
- { service_intent: plan,      mapping_type: coarse, domain: DOCUMENT,
    intent_ids: [doc_plan_draft, play_expand, play_transition_next_step] }  # coarse ⇒ Domain 수준 증거
- { service_intent: board.resize_up, mapping_type: out_of_scope }

unmapped_intents:                # ③ 의도적 무매핑 — "깜빡"과 구분되게 명시
- { intent_id: refl_teaching_pattern_insight, reason: 챗 응답형 — 서비스 액션 없음 }

fastpath_surface:                # ④ 뇌 의도가 아님을 문서화 — KTIB 측정 제외의 감사 근거
- { op: board.resize_up, note: OP_RE 결정적 처리 — Shadow 텔레메트리만 }
```

**거버넌스·검증 장치:**

- `scripts/apply_intent_action_map.py` — `apply_risk_model.py` 패턴 복제: 검증 후
  `INTENT_ACTION_MAP_UPDATE` governance_event 기록.
- `scripts/validate_schemas.py`에 `check_action_map_coherence()` 추가
  (기존 `check_risk_model_coherence` 패턴): ⓐ 모든 매핑 intent_id가 온톨로지에 존재
  ⓑ **모든 온톨로지 의도가 mappings/unmapped_intents 중 정확히 한 곳에** (전수 커버 — 조용한 구멍 금지)
  ⓒ 버전 핀 일치 ⓓ 리스크 정합: rm CRITICAL ⇒ L3, `undoable: false` ⇒ L1 금지.
- `scripts/gen_service_contract.py` — Python이 온톨로지+크로스워크 YAML을 읽어 킨더버스용
  `src/ai/intent-crosswalk.gen.ts` 방출: `ONTOLOGY_VERSION`/`CROSSWALK_VERSION`/`SOURCE_DIGEST`
  (두 YAML sha256), `BrainIntentId` 유니온, `SERVICE_TO_BRAIN`, `BRAIN_TO_ROUTE`,
  `ROUTER_VOCAB_GEN`. `--check` 모드 = 재생성 diff(신선도 게이트).
- **드리프트 테스트 (양 레포 각자 자기 절반을 잠금)**: 랩 `backend/tests/test_crosswalk_sync.py`
  (의도 쪽 FK + 버전 핀 — 온톨로지 범프에 크로스워크 PR이 빠지면 실패) / 킨더버스
  `check:intent-map`(npm build 체인): 생성 파일 digest 검증 + 모든 action_type/route가 실제
  레지스트리(`INTENT_TO_ROUTE`, composer)에 존재 + **라운드트립 속성**
  `BRAIN_TO_ROUTE[SERVICE_TO_BRAIN[c].intent_ids[i]] === INTENT_TO_ROUTE[c].route`.
- **라우터 프롬프트는 전체 생성하지 않는다.** 킨더버스 `src/ai/prompt.ts` L2_TASK의 수작업 현장어
  가이드(활동지≠글 문서 등)는 라우터의 실전 강점이므로 보존하고, **어휘 줄 + 혼동 사례 few-shot
  부록(~10줄, 크로스워크 라우트가 순진한 추측과 다른 의도의 positive_examples에서 샘플)**만
  `ROUTER_VOCAB_GEN`으로 생성해 스플라이스한다.
- **`proposed_action` 채우기**: 랩 `backend/app/core/action_map.py` 로더(ontology.py 패턴) →
  추론 파이프라인이 각 IntentCandidate에 action_type·params(template ∪ 추출 슬롯)·undoable·preview를
  장식, `requires_confirmation = (autonomy_level != 'L1')`. (구현은 후속 승인 범위.)

---

## §6 Shadow 0a 캡처 — 실발화가 뇌로 흐르는 유일한 다리

### 6-1 데이터 플로우

```
[킨더버스 클라이언트]                        [킨더버스 서버]                [랩]
프롬프트바 라우팅 출구 3곳                 api/shadow/capture.ts        scripts/ingest_shadow_batch.py
 L1 정규식 fast-path ┐                      - 킬스위치·옵트아웃 확인      - infer_request 스키마 검증
 L2 runRouter(LLM)   ├─ 결과 확정 후 ──────▶ - teacher_ref = HMAC(...)  ─▶ - PII 감사 샘플
 L3 보드 실행기      ┘  fire-and-forget      - 2차 PII 정규식             - 벤치마크 누출 가드(해시 대조→드랍)
 (+~60s 결과 창:                             - capture_batch_id 부여      - episodes: PRODUCTION_SHADOW
  수락/undo/교정 신호)                       - INSERT shadow_capture        /UNVERIFIED/SHADOW_CONVERTER
                                              (anon 전면 거부 테이블)      - 사이드카 → WEAK_BEHAVIORAL 증거
                                                    │                      - 미분류 → atlas_expansion_queue
                                                    └── NDJSON 배치 export ──▶   (PENDING — 규칙 4)
```

핵심 설계 결정 3가지:

1. **캡처 레코드 = 스키마 유효한 `infer_request`(mode=shadow) + 물리적으로 분리된 `service_outcome`
   사이드카.** 사이드카(서비스 라우터 판정·교사 수락/undo/mismatch 교정)는 훈련 메타데이터라
   절대 규칙 5에 따라 Core 안에 절대 못 들어간다 — 분리를 관례가 아니라 레코드 모양으로 강제한다.
   레코드가 곧 유효한 infer_request이므로 Shadow 0b는 **재생만 하면 된다**(마이그레이션 0).
2. **저장은 서비스 쪽, 랩은 배치로만 받는다.** 랩 `/infer`는 shadow를 501로 거부하는 현 상태 유지.
   킨더버스 `kv_store`는 anon 읽기/쓰기라 캡처 저장 불가(`supabase/schema.sql`) — 전용
   `shadow_capture` 테이블(anon 정책 없음 = 전면 거부, service-role만 INSERT)을 새로 만든다.
3. **L1 fast-path 히트도 캡처한다.** 라우터 LLM 호출만 캡처하면 어려운 발화로 분포가 편향된다 —
   뇌는 쉬운 대량 분포도 봐야 한다.

### 6-2 필드 매핑 (요지)

| infer_request | 킨더버스 원천 |
|---|---|
| `prompt.text` | RouterInput.text **원문**(오타 포함 — normalizePlayTheme 적용 금지), 단 PII 스크럽 후 |
| `workspace_context.objects≤50` | boardStore 노드 → {id, type, bbox, selected, text_preview≤200 마스킹} — 선택 우선, 최근순 |
| `objects[].visual_semantics` | **정직한 생략 우선** — 결정적 도출 가능할 때만 방출(예: 색칠 프레임→DRAWING_PAINTING), `[UNKNOWN]` 배열 방출 금지, extractor_version="kv-board-heuristic-0.1" |
| `workspace_context.derived_summary` | {page, available_actions, selection_types, …} — 키 집합은 크로스워크 YAML에 고정 |
| `recent_actions≤10` | `src/board/commands.ts` 언두 커맨드 이름 + 생성 이벤트 링버퍼 |
| `session.conversation_history≤6` | 프롬프트바 턴 링버퍼 (clarify 응답 = role brain) |
| `teacher_context.teacher_ref` | **서버 측** HMAC-SHA256(tenant+device, SHADOW_SALT) — 가명·삭제 핸들 겸용 |
| `teacher_context.profile` | v0: {age_band, curriculum}만 — **명부·특이사항(child.notes) 절대 금지** |
| `shadow_extension.capture_batch_id` | 서버 부여 `KV-<YYYYMMDD>-<gitsha7>-<seq>` — 배치=export=재생 단위 |

`service_outcome` 사이드카: `decided_by`(regex/router_llm/…), L1/L2 판정, `teacher_signal`
{accepted, edited, undo_within_window, mismatch_choice, clarify_answer}, client_build 버전들,
pii_scrub 증명. 랩 변환: 각 신호 → `evidence_type=WEAK_BEHAVIORAL`, `actor_type=BEHAVIOR_SIGNAL`,
intent는 크로스워크로 번역(coarse 매핑은 Domain 수준 — 설계 문서의 shadow 행동 증거 입도와 일치),
극성은 수락=supports/undo·교정=refutes, 가중치는 `config.label_aggregator.evidence_type_weights`
(절대 규칙 10 — 하드코딩 금지). 신호 없는 행은 UNLABELED로 남는다.

### 6-3 PII·거버넌스 7항목 충족표

| 항목 | 장치 |
|---|---|
| 목적 정의·법적 근거 | 정책 1쪽 문서(후속: `docs/06-runtime-integration/shadow-0a-governance.md`) — **사용자 결정** |
| PII 게이트 | 3계층: ①클라 — 기존 `maskName` 확장(명부 이름 → `<CHILD>` 치환, prompt/preview/history 전체) ②서버 — 일반 한국어 이름·전화·주소 정규식 2차 ③랩 — 수입 시 감사 샘플 + pii_scrub 증명 없는 행 거부 |
| 최소 수집 | 구조로 강제: 텍스트는 발화+200자 프리뷰뿐, 이미지·명부·특이사항 없음, objects≤50·history≤6·actions≤10 |
| 보존 | `shadow_capture` 보존일수 크론 삭제 — 일수는 **사용자 결정** |
| 옵트아웃 | 서버 확인 테넌트 플래그(클라 신뢰 안 함) + 전역 킬스위치 env + teacher_ref(HMAC)를 삭제 핸들로 |
| 스키마 매핑 | §6-2 표 — 크로스워크 YAML에 버전 관리 |
| (수집 개시) | 위 전부의 사인오프가 **S1 게이트** — 그 전엔 코드가 있어도 플래그 OFF |

**벤치마크 누출 가드(필수)**: KTIB 문항 발화를 누가 서비스에 타이핑하면 shadow로 재수입될 수 있다.
`ingest_shadow_batch.py`는 `expert_ingest.py`와 같은 dedup_hash 계열로 발화 해시를
BENCHMARK_HOLDOUT 전체와 대조해 히트를 드랍하고 리포트에 계수한다.

---

## §7 측정 정직성 — KTIB와 신설 의도

1. **신설 의도는 태어날 때 어둡다.** 사람 저작 문항(검수 2인, kappa ≥ `config.review.min_agreement_kappa`
   = 0.65, 합성 금지)이 생기기 전까지 dark/`pending_evaluation` — 절대 규칙 3(밝기는 Arena만)과
   정합. 미측정을 0으로 그리지 않는 기존 원칙 그대로.
2. **분모 슬라이드 금지.** onto-1.2(또는 2.0) 이후 헤드라인 First Intent Accuracy는 **core-63 고정
   슬라이스를 병행 보고**한다 — 신설 의도가 분모에 슬며시 들어와 96% 목표의 의미가 바뀌는 것을 막는다.
   (replay-axis 규율을 지표 자신에게 적용.)
3. **KTIB → 킨더버스 라우터 회귀.** 시험지 185문항(ktib-2)의 (intent_id, 발화)를 `BRAIN_TO_ROUTE`로
   기대 route_to에 매핑해 킨더버스 `/eval` 하네스의 두 번째 스위트로 — 단 **mock/오프라인 라우터
   전용**(배포 게이트웨이 금지 — 비용·누출 방지). 서비스는 아무것도 훈련하지 않으므로 KTIB 오염 없음.
4. **골든셋은 데이터가 아니라 픽스처.** 킨더버스 골든셋(사전 진단 49건 + `ROUTING_GOLDEN` 10건,
   `src/eval/golden.ts`)은 단독 저자·무 kappa라 `expert_ingest.py`가 (올바르게) 거부한다 — 크로스레포
   드리프트 픽스처로만 쓴다. 선택지: ROUTING_GOLDEN 10건을 2인 검수로 승격해 EXPERT_AUTHORED
   VALIDATION으로 수입(§10-4, 사용자 결정).

---

## §8 단계별 로드맵

| 단계 | 내용 | 게이트 | 산출물 |
|---|---|---|---|
| **S0 계약·스캐폴딩** | 크로스워크 YAML + 검증기 + 코드젠 + 양측 드리프트 테스트; (온톨로지 범프는 §10-1 결정 후) 킨더버스 캡처 빌더(플래그 기본 OFF) + 랩 수입 스크립트 `--dry-run` | 없음 (거버넌스 무의존 — 실데이터 이동 0) | iam-1.0, gen TS, 테스트 |
| **S1 캡처 ON** | `api/shadow/capture.ts` + `shadow_capture` 테이블 + 옵트아웃/보존 크론; 동의 테넌트 플래그 ON; 첫 배치 export→수입; 분포 리포트(UNKNOWN율→확장 큐) | **거버넌스 7항목 사인오프** (사용자) | PRODUCTION_SHADOW 에피소드, 분포 리포트 |
| **S2 Shadow 0b** | 저장된 NDJSON을 뇌 추론으로 오프라인 재생 → 서비스 판정과의 불일치 리포트; WEAK_BEHAVIORAL 증거 유입 | Pilot 게이트 (설계 문서 §10-2) | 불일치 리포트, 교사 노출 0 유지 |
| **S3 live assist** | L1 미스+저신뢰 케이스에 뇌 `/infer` 호출 | **KTIB 96% + 안전 게이트 — 현 HOLD** | (설계 동결 — 이 문서 범위 밖) |

오늘 S3를 위해 하는 유일한 양보: 캡처 레코드 모양이 곧 미래 live 요청 모양이라는 것.

---

## §9 마스터 문서 Change Log 제안 목록 (사용자 승인 대기 — 이 문서는 제안만 담는다)

1. **§5-9/§5-10 부록**: 크로스워크 아티팩트(실행 정책의 온톨로지 외부화)와 fastpath_surface 경계 —
   "서비스의 결정적 조작 표면은 뇌 의도가 아니며 KTIB 측정 대상에서 감사 가능하게 제외된다."
2. **§5-8 확장 출처 예외**: `atlas_expansion_queue`에 `source=SERVICE_ALIGNMENT` — UNKNOWN 풀이
   아니라 서비스 표면 감사에서 온 후보도 같은 승인 파이프라인을 탄다(우회 아님).
3. **영역 압력 트리거**(§5-10 각주): UNKNOWN 클러스터가 반복적으로 어느 영역에도 합의 배정
   불가할 때 major(영역 신설) 논의를 개시한다.
4. **KTIB 보고 정책**(§8-2 각주): 온톨로지 범프 후 헤드라인 FIA는 core-63 고정 슬라이스를 병행 보고.
5. **(8영역 채택 시)** §5-10 개정 전문: STUDIO 추가, CANONICAL_DOMAINS 8원소, onto-2.0.

---

## §10 미결 결정 목록 (사용자)

| # | 결정 | 선택지 | 이 문서의 권고 |
|---|---|---|---|
| 1 | **8영역 go/no-go** | STUDIO-A(최소) / STUDIO-B(정합) / 보류+영역 압력 트리거 | 보류+트리거. 단 연다면 arena_runs 0인 지금이 최저 비용(§4-4) |
| 2 | 상담 의도 리스크 등급 | STANDARD / ELEVATED(rm-1.1 필요) | ELEVATED — 아동 평가 영역 접촉 |
| 3 | Shadow 캡처 기본값·보존 | 옵트인/옵트아웃, 보존일수, HMAC 솔트 관리 주체 | 명시적 옵트인, 보존은 짧게 시작 |
| 4 | 골든셋 10건 승격 | 2인 검수 후 VALIDATION 수입 / 픽스처로만 | 검수 여력 있으면 승격(값싼 실데이터) |
| 5 | 크로스워크 리뷰 주기 | onto-* 범프 PR마다 필수 / 분기별 | 범프 PR마다 필수 |
| 6 | 다의도 KTIB(패키지 측정) | v2 과제로 명시 / 무기한 보류 | v2 과제로 명시 |

---

## 부록 A — 절대 규칙 10개 정합 자가점검

| 규칙 | 이 전략에서 지키는 방식 | 절 |
|---|---|---|
| 1 임계값은 config만 | 증거 가중치·보존일수 등 전부 config/env — 하드코딩 없음 | §6-2 |
| 2 벤치마크 DB CHECK | shadow 데이터는 UNVERIFIED — 벤치마크 진입 불가(기존 CHECK 그대로) + 누출 해시 가드 | §6-3 |
| 3 brightness는 Arena만 | 신설 의도 dark 시작, Shadow 증거는 밝기에 접근 안 함 | §7-1 |
| 4 노드 자동 INSERT 금지 | 신설 7종도 확장 큐(PENDING, source=SERVICE_ALIGNMENT)→승인→`run_backfill.py`(governance_events) | §3-2, §9-2 |
| 5 훈련 메타데이터 Core 금지 | `service_outcome` 사이드카를 Core 밖 레코드 모양으로 강제 | §6-1 |
| 6 adversarial 분리 | 해당 없음(이 전략은 adversarial 채널을 만들지 않음) | — |
| 7 TRANSFORM_ONLY 원문 금지 | 해당 없음(캡처는 교사 자기 발화 — 단 PII 스크럽 §6-3) | — |
| 8 label_state ≠ reliability_tier | shadow는 UNVERIFIED(품질)·UNLABELED(상태)로 각각 정확히 표기 | §6-1 |
| 9 provenance 4필드 | PRODUCTION_SHADOW / SHADOW_CONVERTER / TEACHER / BEHAVIOR_SIGNAL 명시 | §6-1 |
| 10 evidence_type 서열 금지 | mismatch 교정 가중치도 config로 (§6-2) | §6-2 |

## 부록 B — 근거 파일 색인

랩: `seeds/ontology_v1.yaml`(onto-1.1, intent_id 64 = 63+UNKNOWN; :534 색칠도안 예시),
`backend/app/core/ontology.py`(CANONICAL_DOMAINS), `db/migrations/001_init.sql:22,107`,
`frontend/src/brain3d/regions.ts`, `schemas/infer_request.schema.json`·`infer_response.schema.json`·
`visual_semantics.schema.json`, `backend/app/api/infer.py:100`(비 gym 501),
`backend/app/foundry/expert_ingest.py`, `seeds/risk_model_v1.yaml`(CRITICAL 7),
`scripts/apply_ontology_examples.py`, `backend/app/brain/backfill.py`.

킨더버스: `src/ai/intent-lexicon.ts`(ContentIntent 8·BoardOpType 9), `src/ai/contract.ts`
(RouterOutput, CONFIDENCE_THRESHOLD 0.7), `src/ai/prompt.ts`(L2_TASK), `src/ai/actions.ts`
(PAGE_ACTIONS), `src/board/prompt.ts`(3계층 캐스케이드), `src/board/commands.ts`,
`src/eval/golden.ts`(ROUTING_GOLDEN 10) + `docs/INTENT_DIAGNOSIS.md`(골든셋 49건·사전 정확도 100%),
`supabase/schema.sql`(kv_store anon RW), `src/board/composer.ts`(buildPlayPackage).
