# 04. 온톨로지와 의도 카탈로그 — onto-2.1 (8영역 · 70의도)

> **한눈에 보기**
>
> - 현재 온톨로지 버전은 **onto-2.1**, 영역(domain) 8개 아래 **정식 intent 70개**(+ 미분류용 `UNKNOWN` 1개)가 2계층으로 놓여 있다. positive 예시 총 419개, 70개 intent 전부에 `confusable_with`(혼동 후보)가 지정돼 있다. `IMPLEMENTED` [근거: seeds/ontology_v1.yaml]
> - 위험 등급은 온톨로지와 **분리된 별도 시드**(rm-1.0)로 관리한다: **CRITICAL 7 / ELEVATED 6 / 나머지 57개 STANDARD**. [근거: seeds/risk_model_v1.yaml]
> - **STUDIO(자료 만들기) 영역은 2026-07-15 onto-2.0(major)에서 신설**됐고, 이때 63→70개로 늘었다. `visual_image_generate`·`visual_collage_compose` 2종은 **intent_id 불변으로 VISUAL→STUDIO 이동**했다(시험지 골드 라벨 무손상). [근거: seeds/ontology_v1.yaml 헤더 주석]
> - 시험지 커버리지 갭: 최신 시험지 **ktib-3(386문항)은 70개 중 8개 의도에만 문항이 있다**(CRITICAL 7개 각 47~58문항 + doc_observation_record 1문항). **나머지 62개 의도는 문항 0 = 측정 불가(노드 dark 유지가 정직한 상태)**. `PARTIAL` [근거: 팩트팩 "KTIB 커버리지" 절, 2026-07-17 13:16 수집]
> - 이 장의 모든 실측 수치(evidence 지지 수·ktib-3 문항 수·혼동 edge 수)는 2026-07-17 13:16 읽기 전용 DB 스냅샷(핸드북 팩트팩·intent별 CSV)이 원천이다. 용어가 낯설면 [03-concepts-and-glossary.md](03-concepts-and-glossary.md)를 먼저 보라. 데이터 자체의 계보는 [05-data-catalog.md](05-data-catalog.md).

---

## 4-1. 구조: domain → intent 2계층

- 온톨로지는 `seeds/ontology_v1.yaml`이 유일한 의미 원천이다(설계 문서 §5-9). 각 intent는 `intent_id / domain / definition / positive_examples / negative_examples / confusable_with`를 가진다. [근거: seeds/ontology_v1.yaml]
- `UNKNOWN`은 domain이 없는 특수 intent다 — 어떤 intent로도 분류할 수 없는 발화를 미분류 pool로 보내 주간 클러스터링 대상이 되게 한다(§5-8). 70개 집계에서 제외된다.
- positive_examples의 원본은 `seeds/ontology_examples_draft.csv`이며, 수정은 시트를 고쳐 `scripts/apply_ontology_examples.py --write`로만 반영한다(YAML 직접 편집 금지). [근거: seeds/ontology_v1.yaml 헤더 주석]
- 3D 뇌의 `brain_nodes` 70개가 이 온톨로지와 1:1이고(영역별 수 일치), 영역 이동조차 거버넌스 이벤트(`NODE_REGION_MOVE` 2건)로 기록돼 있다. [근거: 팩트팩 DB 스냅샷·governance_events]

## 4-2. 8개 영역 요약

| 영역(domain) | 한글 의미 | intent 수 | 비고 |
|---|---|---:|---|
| PLAY | 놀이 지원 — 확장·전개·환경 구성 | 9 | |
| OBSERVATION | 아이 관찰 — 기록·포착·분석·검색 | 9 | ELEVATED 3종 포함 |
| DOCUMENT | 문서 작성 — 글쓰기·다듬기·교정 | 9 | ELEVATED 2종 포함 |
| VISUAL | 사진·시각 자료 손질 — 보정·정리·마스킹 | 7 | 기존 9종에서 2종이 STUDIO로 이동(id 불변) |
| COMMUNICATION | 소통·공유 — 학부모·동료·아이들 | 9 | **CRITICAL 4종** 포함 |
| OPERATION | 운영 업무 — 일정·출결·발송·자료함 | 9 | **CRITICAL 3종** 포함 |
| REFLECTION | 돌아보기 — 활동·아이·교사 자신 | 10 | onto-2.0에서 refl_child_guidance_consult 추가 |
| STUDIO | 자료 만들기 — 활동지·영상·슬라이드·게임 생성 | 8 | **2026-07-15 onto-2.0(major) 신설.** visual 2종(id 불변) 이동 + studio_* 6종 신규 저작 |

[근거: seeds/ontology_v1.yaml, 팩트팩 "온톨로지 실측" 절]

## 4-3. 영역별 intent 전수 표

표 읽는 법(전 표 공통):

- **한글 이름** = 화면 표시 라벨 [근거: frontend/src/panels/intentLabels.ts::INTENT_LABEL_KO]. 운영자가 PIN으로 고친 오버레이(intent_display)가 있으면 그것이 우선한다(§4-7).
- **쉬운 설명** = YAML `definition` 요약, **대표 발화** = YAML `positive_examples[0]` 원문. [근거: seeds/ontology_v1.yaml]
- **위험** = rm-1.0 등급. CRITICAL은 축 병기(E=비가역 외부 유출, D=비가역 데이터 파괴, R=공식 등록부 오기재). 표기 없으면 STANDARD. [근거: seeds/risk_model_v1.yaml]
- **ev 지지** = 이 intent를 지지(polarity=supports)하는 evidence 건수. **ktib-3** = 최신 시험지 문항 수. **혼동 edge(from/to)** = confusion_edges에서 이 intent가 정답인데 다른 의도로 오인된다는 가설(from_true) / 다른 발화가 이 의도로 오인된다는 가설(to_predicted) 건수 — 현재 629개 전부 `hypothesized`(SKEPTIC 산) 상태다. [근거: 팩트팩 intent별 CSV·DB 스냅샷, 2026-07-17 13:16]

### PLAY (9)

| intent_id | 한글 이름 | 쉬운 설명 | 대표 발화 | 위험 | ev 지지 | ktib-3 | 혼동 edge(from/to) |
|---|---|---|---|---|---:|---:|---|
| play_expand | 놀이 더 키우기 | 진행 중 놀이를 더 넓고 깊게 발전시킬 확장 아이디어 제안 | 이 블록놀이 좀 더 키워볼 만한 거 없을까? | STANDARD | 48 | 0 | 50/73 |
| play_transition_next_step | 다음 활동 제안 | 지금 놀이에서 이어 전개할 다음 단계 활동 제안 | 다음엔 뭘 해주면 좋을까? | STANDARD | 49 | 0 | 65/93 |
| play_flow_naturalize | 놀이 흐름 다듬기 | 계획된 활동 순서의 전환이 매끄럽도록 흐름을 다듬은 전개안 | 이 순서가 좀 뚝뚝 끊기는데 흐름 좀 매끄럽게 해줘 | STANDARD | 56 | 0 | 0/2 |
| play_material_suggest | 놀잇감 추천 | 놀이에 새로 투입하면 좋을 놀잇감·재료 추천 | 가게놀이 하는데 뭐 더 넣어주면 좋을까? | STANDARD | 42 | 0 | 7/3 |
| play_scenario_generate | 놀이 시나리오 만들기 | 상상놀이에 바로 쓸 이야기 배경·역할 시나리오 생성 | 우주 탐험 역할놀이 상황극 하나 짜줘 | STANDARD | 38 | 0 | 0/2 |
| play_inquiry_question | 발문(질문) 만들기 | 유아의 탐구·사고를 자극할 교사 발문 목록 생성 | 그림자 놀이 하는데 애들한테 뭐라고 물어보면 좋을까? | STANDARD | 44 | 0 | 0/2 |
| play_level_adapt | 난이도 맞추기 | 연령·발달 수준에 맞게 난이도·방법을 조정한 변형안 | 이거 만 3세도 할 수 있게 좀 쉽게 바꿔줘 | STANDARD | 46 | 0 | 7/3 |
| play_revive_stalled | 시든 놀이 살리기 | 흥미가 식거나 막힌 놀이의 몰입을 되살릴 개입 방법 제안 | 애들이 며칠 만에 시큰둥해졌는데 어떻게 다시 불붙이지? | STANDARD | 52 | 0 | 0/2 |
| play_environment_setup | 놀이 환경 꾸미기 | 놀이가 잘 일어나도록 공간·흥미영역을 배치한 환경 구성안 | 역할놀이 영역 이번엔 어떻게 꾸며주지? | STANDARD | 49 | 0 | 0/2 |

### OBSERVATION (9)

| intent_id | 한글 이름 | 쉬운 설명 | 대표 발화 | 위험 | ev 지지 | ktib-3 | 혼동 edge(from/to) |
|---|---|---|---|---|---:|---:|---|
| obs_record_moment | 순간 관찰 기록 | 짧은 구술·메모를 날짜·아동·상황이 채워진 관찰 기록으로 저장 | 지호 방금 처음으로 가위질 성공했어, 이거 적어놔 | ELEVATED | 72 | 0 | 7/3 |
| obs_capture_scene | 활동 장면 담기 | 지금 벌어지는 장면을 사진·영상으로 포착해 관찰 증거로 저장 | 지금 이 장면 좀 찍어놔 | STANDARD | 29 | 0 | 0/2 |
| obs_tag_children | 사진 속 아이 태그 | 사진·기록 속 아이를 지정받아 해당 아동 프로필에 연결 | 이 사진 서준이랑 하윤이야 | ELEVATED | 63 | 0 | 0/2 |
| obs_classify_development | 발달 영역 분류 | 기록·장면을 발달 영역과 누리과정 지표로 분류 | 이 기록 어느 영역에 넣으면 돼? | ELEVATED | 58 | 0 | 7/3 |
| obs_summarize_child | 아이별 관찰 요약 | 아이의 누적 기록·사진을 모아 최근 행동·발달 흐름 요약 | 요즘 도윤이 어떻게 지내? | STANDARD | 84 | 0 | 0/2 |
| obs_detect_behavior_change | 행동 변화 감지 | 이전 시기와 비교해 달라진 행동 패턴·주의 필요 변화 탐지 | 요즘 지우가 좀 달라진 것 같은데, 뭐 있어? | STANDARD | 78 | 0 | 0/2 |
| obs_recommend_focus | 관찰 포커스 추천 | 기록 누적량·공백을 근거로 다음 관찰 대상 추천 | 내일은 누굴 좀 봐야 하지? | STANDARD | 56 | 0 | 7/3 |
| obs_set_watchpoint | 관찰 포인트 설정 | 특정 행동·상황이 다시 나타나면 포착·알림하도록 워치포인트 설정 | 준우가 또 친구 물면 바로 알려줘 | STANDARD | 37 | 0 | 0/2 |
| obs_search_records | 관찰 기록 검색 | 아이·기간·활동 조건으로 과거 관찰 기록·장면 검색 | 하윤이 블록놀이 했던 기록 찾아줘 | STANDARD | 41 | 0 | 0/2 |

### DOCUMENT (9)

| intent_id | 한글 이름 | 쉬운 설명 | 대표 발화 | 위험 | ev 지지 | ktib-3 | 혼동 edge(from/to) |
|---|---|---|---|---|---:|---:|---|
| text_naturalize | 글 자연스럽게 다듬기 | 내용은 그대로, 어색한 표현만 매끄러운 문장으로 수정 | 이거 좀 자연스럽게 만들어줘 | STANDARD | 48 | 0 | 7/3 |
| write_activity_followup | 활동 후속 기록 쓰기 | 방금 마친 활동의 진행·다음 전개를 담은 후속 기록 작성 | 오늘 물감놀이 한 거 후속 기록 좀 써줘 | STANDARD | 52 | 0 | 0/2 |
| doc_observation_record | 관찰 기록문 쓰기 | 구술·메모한 관찰 내용을 격식 갖춘 관찰 기록 문서로 작성 | 지우가 오늘 블록으로 성 만들었거든, 이거 관찰기록으로 써줘 | ELEVATED | 54 | 1 | 0/2 |
| doc_notice_draft | 알림장 초안 쓰기 | 전달 내용으로 학부모 알림장 글 초안 작성 | 내일 견학 가니까 준비물 알림장 좀 써줘 | STANDARD | 60 | 0 | 7/2 |
| doc_plan_draft | 활동계획안 쓰기 | 주제·기간 정보로 주간·일일 계획안 초안 작성 | 다음 주 주간계획안 좀 짜줘 | STANDARD | 64 | 0 | 0/3 |
| doc_summarize | 글 요약하기 | 긴 기록·문서를 핵심만 남긴 짧은 요약문으로 | 이거 너무 긴데 세 줄로 요약 좀 | STANDARD | 57 | 0 | 0/2 |
| doc_expand_text | 짧은 메모 늘려 쓰기 | 짧은 메모·초안에 살을 붙여 상세한 완성 글로 확장 | 이 메모 가지고 한 문단으로 늘려줘 | STANDARD | 54 | 0 | 7/3 |
| doc_proofread | 맞춤법 교정 | 맞춤법·띄어쓰기·오탈자를 찾아 고친 교정본 | 맞춤법 좀 봐줘 | STANDARD | 53 | 0 | 0/2 |
| doc_portfolio_comment | 포트폴리오 코멘트 쓰기 | 누적 기록·사진으로 발달 종합 코멘트(총평) 작성 | 지우 포트폴리오 총평 좀 써줘 | ELEVATED | 63 | 0 | 0/2 |

### VISUAL (7)

| intent_id | 한글 이름 | 쉬운 설명 | 대표 발화 | 위험 | ev 지지 | ktib-3 | 혼동 edge(from/to) |
|---|---|---|---|---|---:|---:|---|
| visual_naturalize | 사진 자연스럽게 보정 | 색감·노출·기울기 등 결함을 원본 분위기 안에서 보정 | 이거 좀 자연스럽게 만들어줘 | STANDARD | 90 | 0 | 9/3 |
| visual_layout_refine | 게시물 배치 다듬기 | 화면 위 사진·텍스트 요소의 배치·정렬·간격 재구성 | 알림장 사진 배치가 좀 어수선한데 정돈해줘 | STANDARD | 56 | 0 | 0/2 |
| visual_photo_organize | 사진 정리 | 여러 사진을 활동·날짜·아동 기준 분류, 중복·실패 컷 정리 | 이 사진 정리 좀 | STANDARD | 60 | 0 | 0/2 |
| visual_photo_pick_best | 베스트 사진 고르기 | 품질·쓰임새 기준으로 쓸 만한 소수 사진 추천 | 이 중에 제일 잘 나온 걸로 골라줘 | STANDARD | 51 | 0 | 7/3 |
| visual_privacy_mask | 얼굴 모자이크 처리 | 공개 불가한 얼굴·개인정보 영역을 흐림·스티커 처리 | 뒤에 다른 반 애들 얼굴 좀 가려줘 | STANDARD | 59 | 0 | 0/2 |
| visual_crop_focus | 사진 크롭·확대 | 특정 아동·장면이 잘 보이게 잘라내거나 확대 | 여기서 서연이만 크게 나오게 잘라줘 | STANDARD | 28 | 0 | 7/3 |
| visual_decorate | 사진 꾸미기 | 프레임·스티커·날짜·이름표 같은 꾸밈 요소 얹기 | 이 사진 생일 느낌 나게 꾸며줘 | STANDARD | 56 | 0 | 0/2 |

주의: `text_naturalize`(DOCUMENT)와 `visual_naturalize`(VISUAL)의 대표 발화가 **같은 문장**("이거 좀 자연스럽게 만들어줘")이다 — 발화만으로는 못 가르고 화면 컨텍스트(선택된 것이 글인가 사진인가)로만 갈리는 대표적 동형 발화 쌍이다. `visual_privacy_mask`가 STANDARD인 이유(오인식 위험이 fire가 아니라 miss 방향이라 CWAR-miss가 잡음)는 rm-1.0 말미 특기 참조. [근거: seeds/ontology_v1.yaml, seeds/risk_model_v1.yaml 하단 주석]

### STUDIO (8) — onto-2.0 신설

| intent_id | 한글 이름 | 쉬운 설명 | 대표 발화 | 위험 | ev 지지 | ktib-3 | 혼동 edge(from/to) |
|---|---|---|---|---|---:|---:|---|
| visual_image_generate | 그림 만들기 | 주제 설명으로 활동 자료·안내문용 새 삽화·이미지 생성 (VISUAL→STUDIO 이동, id 불변) | 다음 주 주제가 가을인데 어울리는 그림 하나 만들어줘 | STANDARD | 62 | 0 | 0/2 |
| visual_collage_compose | 콜라주 만들기 | 여러 사진을 한 장 콜라주·모음 컷으로 합성 (onto-2.1에서 VISUAL→STUDIO 이동, id 불변) | 오늘 사진들 한 장으로 모아줘 | STANDARD | 39 | 0 | 0/2 |
| studio_worksheet_generate | 활동지 만들기 | 인쇄용 활동지(색칠 도안·미로·오리기 등) 생성 | 봄꽃 주제로 선잇기 활동지 하나 만들어줘 | STANDARD | 0 | 0 | 0/0 |
| studio_video_generate | 활동 영상 만들기 | 주제 설명·이미지로 활동·수업용 짧은 영상 생성 | 바다 속 물고기들이 헤엄치는 짧은 영상 만들어줘 | STANDARD | 0 | 0 | 0/0 |
| studio_slides_draft | 슬라이드 만들기 | 수업 주제·행사 내용으로 발표·수업용 슬라이드 초안 생성 | 교통안전 수업용 슬라이드 만들어줘 | STANDARD | 0 | 0 | 0/0 |
| studio_game_generate | 게임 만들기 | 화면을 조작하며 노는 인터랙티브 게임 콘텐츠 생성 | 동물 짝맞추기 게임 만들어줘 | STANDARD | 12 | 0 | 0/0 |
| studio_topic_web_generate | 주제망 만들기 | 주제·관심사로 생각그물·주제망(마인드맵) 생성 | 가을 주제로 마인드맵 그려줘 | STANDARD | 0 | 0 | 0/0 |
| studio_external_resource_search | 외부 자료 찾기 | 활동 주제에 맞는 외부 자료(유튜브·웹) 검색·링크 제시 | 상어 가족 율동 유튜브 영상 찾아줘 | STANDARD | 0 | 0 | 0/0 |

STUDIO 신규 6종 중 5종과 `refl_child_guidance_consult`는 evidence 0건이다 — onto-2.0(07-15) 신설 직후라 훈련 데이터 유입 전이며, 증산 캠페인(domain_weights에 STUDIO 0.06 배정)이 진행 중이다. `PARTIAL` [근거: 팩트팩 intent별 CSV·config/experiments.yaml::campaign.domain_weights·세션노트 07-17]

### COMMUNICATION (9)

| intent_id | 한글 이름 | 쉬운 설명 | 대표 발화 | 위험 | ev 지지 | ktib-3 | 혼동 edge(from/to) |
|---|---|---|---|---|---:|---:|---|
| comm_draft_parent_notice | 학급 알림장 쓰기 | 화면 컨텍스트 근거로 학급 전체 알림장·공지 초안 작성 | 오늘 알림장 좀 써줘 | STANDARD | 56 | 0 | 7/3 |
| comm_message_individual_parent | 개별 학부모 메시지 | 특정 아동 관련 사항을 한 가정에 개별 메시지로 작성·전송 | 지우 어머니한테 오늘 낮잠 못 잤다고 전해줘 | **CRITICAL(E)** | 45 | 47 | 0/2 |
| comm_share_media_with_parents | 학부모에 사진 공유 | 지시된 사진·영상을 학부모 채널에 공유 | 이 사진들 부모님들한테 보내줘 | **CRITICAL(E)** | 53 | 54 | 0/2 |
| comm_share_with_colleague | 동료 교사와 공유 | 자료·기록을 원내 동료·원장에게 전달·공유 | 이거 옆 반 선생님한테도 보내줄래? | ELEVATED | 57 | 0 | 7/3 |
| comm_present_to_children | 아이들에게 보여주기 | 자료를 교실 대형 화면에 크게 띄워 표시 | 얘들아 이것 좀 봐 | STANDARD | 45 | 0 | 0/2 |
| comm_schedule_send | 발송 예약 | 작성된 알림·메시지의 발송 시각 예약 등록·변경 | 이 알림장 내일 아침에 나가게 해줘 | **CRITICAL(E)** | 53 | 57 | 0/2 |
| comm_translate_for_family | 가정용 번역 | 알림·메시지를 수신 가정 언어로 번역한 발송본 생성 | 이거 베트남어로도 하나 만들어줘 | STANDARD | 51 | 0 | 7/2 |
| comm_collect_parent_responses | 학부모 회신 모으기 | 발송한 알림·요청의 학부모 회신 수합·집계·요약 | 소풍 간다는 집 몇 집이나 돼? | STANDARD | 64 | 0 | 0/3 |
| comm_request_consent | 동의 요청 보내기 | 동의 필요 사안의 요청서를 학부모에 발송, 서명·회신 요청 | 현장학습 동의서 돌려야 해 | **CRITICAL(E)** | 49 | 56 | 0/2 |

### OPERATION (9)

| intent_id | 한글 이름 | 쉬운 설명 | 대표 발화 | 위험 | ev 지지 | ktib-3 | 혼동 edge(from/to) |
|---|---|---|---|---|---:|---:|---|
| op_schedule_update | 일정 업데이트 | 활동·행사·시간 정보를 캘린더·계획안 일정으로 등록·변경 | 내일 오후에 신체검사 일정 좀 잡아줘 | STANDARD | 58 | 0 | 7/3 |
| op_schedule_check | 일정 확인 | 기간·행사 조건으로 일정 조회·요약 제시 | 오늘 뭐 있었더라? | STANDARD | 64 | 0 | 0/2 |
| op_material_prepare | 준비물 챙기기 | 예정 활동에 필요한 준비물·자료 체크리스트 생성 | 내일 미술활동 준비물 좀 뽑아줘 | STANDARD | 42 | 0 | 0/2 |
| op_document_export | 문서 내보내기 | 문서·자료를 PDF 등 파일·인쇄 형태로 내보내기 | 이거 출력 좀 해줘 | STANDARD | 57 | 0 | 7/3 |
| op_attendance_record | 출결 기록 | 아이별 출결 상태(출석·결석·조퇴)를 출석부에 반영 | 지우 오늘 병결로 해줘 | **CRITICAL(R)** | 64 | 57 | 0/2 |
| op_notice_send | 알림 보내기 | 작성된 알림장·공지를 지정 대상에게 즉시 발송 | 알림장 이제 보내줘 | **CRITICAL(E)** | 56 | 58 | 0/2 |
| op_workspace_organize | 자료 정리 | 워크스페이스 항목을 아이별·날짜별·활동별 정렬·분류 | 작업함에 쌓인 관찰기록이랑 자료들 아이별로 분류해서 정돈해줘 | STANDARD | 53 | 0 | 7/3 |
| op_workspace_search | 자료 검색 | 조건에 맞는 항목을 워크스페이스에서 검색·목록 제시 | 작년 운동회 계획안 파일 어디 있지? | STANDARD | 32 | 0 | 0/2 |
| op_workspace_delete | 자료 삭제 | 항목을 삭제하거나 휴지통으로 이동 | 흔들린 사진들 싹 지워줘 | **CRITICAL(D)** | 63 | 56 | 0/2 |

### REFLECTION (10)

| intent_id | 한글 이름 | 쉬운 설명 | 대표 발화 | 위험 | ev 지지 | ktib-3 | 혼동 edge(from/to) |
|---|---|---|---|---|---:|---:|---|
| refl_activity_review | 활동 돌아보기 | 완료 활동의 잘된 점·아쉬운 점 평가 요약 생성 | 오늘 물감놀이 어땠는지 좀 정리해줘 | STANDARD | 38 | 0 | 7/3 |
| refl_child_progress_review | 아이 성장 돌아보기 | 이전 시기 대비 아이 발달 변화 추이 리뷰 생성 | 서준이 지난달이랑 비교하면 많이 컸나? | STANDARD | 45 | 0 | 0/2 |
| refl_milestone_check | 발달 이정표 점검 | 연령별 표준 발달지표 대비 도달 여부 점검 | 하윤이 5세 발달 기준으로 보면 어때? | STANDARD | 47 | 0 | 0/2 |
| refl_goal_alignment_check | 목표 점검 | 세운 목표·계획 대비 달성·누락 항목 점검표 생성 | 이번 주 계획대로 다 했나 봐줘 | STANDARD | 64 | 0 | 7/3 |
| refl_self_journal | 교사 성찰일지 | 짧은 메모·소감으로 교사 자기 성찰 일지 초안 작성 | 오늘 좀 정신없었는데, 회고 일지 초안 좀 써줘 | STANDARD | 51 | 0 | 0/2 |
| refl_teaching_pattern_insight | 수업 패턴 살펴보기 | 교사 자신의 운영 습관·치우침을 짚는 인사이트 생성 | 나 요즘 미술만 너무 많이 한 것 같지 않아? | STANDARD | 38 | 0 | 0/2 |
| refl_improvement_suggest | 개선점 제안 | 드러난 아쉬운 점으로 다음 실행 개선 방안 제안 | 다음엔 뭘 바꾸면 좋을까? | STANDARD | 52 | 0 | 7/3 |
| refl_support_need_scan | 지원 필요한 아이 찾기 | 학급 전체를 훑어 지원 필요한 아이·영역 목록 제시 | 요즘 좀 신경 써야 할 애 있나 봐줘 | STANDARD | 49 | 0 | 0/2 |
| refl_period_retrospective | 기간 회고 | 선택 기간 전체 기록으로 주·월·학기 회고 리포트 생성 | 이번 달 우리 반 어땠는지 정리해줘 | STANDARD | 61 | 0 | 0/2 |
| refl_child_guidance_consult | 아이 지도 상담 | 걱정되는 행동에 발달 지식 기반 지도 방안을 상담 형식으로 제안 (onto-2.0 신규) | 요즘 지호가 밥을 잘 안 먹는데 어떻게 하면 좋을까? | STANDARD | 0 | 0 | 0/0 |

## 4-4. 위험 등급(rm-1.0)은 온톨로지 밖에 산다

- 위험 등급은 intent의 **의미가 아니라 평가 정책**이라 온톨로지에 넣지 않는다 — 넣으면 등급 수정 때마다 `ontology_version`(replay 축)이 흔들린다. [근거: seeds/risk_model_v1.yaml 헤더]
- **CRITICAL 7** = `comm_message_individual_parent, comm_request_consent, comm_schedule_send, comm_share_media_with_parents, op_attendance_record, op_notice_send, op_workspace_delete`. 이 목록은 `config/experiments.yaml::arena.critical_intents`와 정확히 일치해야 하며 `scripts/validate_schemas.py`가 불일치 시 실패시킨다(빈 목록으로 게이트를 조용히 무력화하는 경로 차단). `IMPLEMENTED`
- **ELEVATED 6** = `obs_tag_children, comm_share_with_colleague, obs_record_moment, obs_classify_development, doc_observation_record, doc_portfolio_comment` — 위험하지만 유출(egress) 경계에서 이미 게이트되므로 CWAR에 넣지 않는다(이중 게이트는 CWAR 희석). 나머지 57개는 전부 STANDARD.

## 4-5. KTIB 커버리지 갭 — 시험지는 아직 "위험 의도 집중 시험"이다

팩트팩 "KTIB 커버리지" 절 그대로: `PARTIAL`

> - ktib-3(최신, 386문항)의 의도 커버: **8/70** — CRITICAL 7(각 47~58문항) + doc_observation_record 1
> - ktib-2(185)도 동일 8개 의도 — 즉 현재 시험은 위험 의도 집중 시험이며 **62개 의도는 문항 0(측정 불가, 노드 dark 유지가 정직한 상태)**
> - 채점 이력: brain run(seed-v0) 0.0% + zero_shot_baseline 88.1%(claude-sonnet-5, ktib-2 185문항 기준)

ktib-3의 의도별 문항 실측: comm_message_individual_parent 47 · comm_share_media_with_parents 54 · comm_request_consent 56 · comm_schedule_send 57 · op_attendance_record 57 · op_notice_send 58 · op_workspace_delete 56 · doc_observation_record 1 (합계 386). [근거: 팩트팩 intent별 CSV]

함의: 3D 뇌에서 밝기(brightness)는 Arena 결과만 갱신하므로(절대 규칙 3), 문항이 0인 62개 노드는 **훈련이 아무리 쌓여도 어두운 상태가 정상**이다. 어둡다=약하다가 아니라 "아직 안 재봤다"로 읽어야 한다. 시험지에 문항을 넣는 유일한 경로는 전문가 저작 유입이다([05-data-catalog.md](05-data-catalog.md) C절).

## 4-6. 특별 절 — 시간축 삼각지대: 관찰 포인트 설정 vs 목표 점검 vs 기간 회고

`obs_set_watchpoint`(관찰 포인트 설정) · `refl_goal_alignment_check`(목표 점검) · `refl_period_retrospective`(기간 회고)는 셋 다 "우리 반을 살펴봐 달라"는 겉모습을 가질 수 있지만, YAML 정의를 직접 읽으면 **시간 방향**이 서로 다르다. [근거: seeds/ontology_v1.yaml::obs_set_watchpoint/refl_goal_alignment_check/refl_period_retrospective]

### ① 정의 비교 (시간 방향 · 목적 · 기대 결과)

| 구분 | obs_set_watchpoint 관찰 포인트 설정 | refl_goal_alignment_check 목표 점검 | refl_period_retrospective 기간 회고 |
|---|---|---|---|
| **시간 방향** | **미래** — 앞으로 그 행동·상황이 "다시 나타나면" | **기준 대비 현재** — 과거에 세운 목표·계획과 지금을 대조 | **과거 구간** — 선택한 기간 전체를 되돌아봄 |
| **사용자 목적** | 앞으로의 관찰·알림을 미리 걸어두기(예약) | 계획이 지켜졌는지 확인(달성/누락 판정) | 그 기간이 전체적으로 어땠는지 정리 |
| **기대 결과** | 워치포인트 등록(재발 시 포착·알림) — 문서가 아니라 **설정** | 달성·누락 항목 **점검표** | 주·월·학기 단위 **회고 리포트**(서술) |
| **입력 근거** | 지정된 아이의 특정 행동·상황 | 주간 계획안·교사가 세운 목표 + 실제 활동·관찰 기록 | 기간의 학급 활동·관찰 기록 전체 |

### ② 최소대립 발화 3개 — 시간 축만 바꾸면 의도가 갈린다

| 발화 | 시간 단서 | 정답 방향 |
|---|---|---|
| "다음 주에는 뭘 중심으로 보면 좋을까?" | 다음 주(미래) | 미래 관찰 준비 — obs_set_watchpoint 계열. 단, "무엇을 지켜봐 달라"는 설정이 아니라 "누구·무엇을 볼지 골라 달라"는 추천이면 obs_recommend_focus로 갈린다(아래 ③) |
| "처음 세운 목표만큼 지금 잘하고 있는지 봐줘." | 처음 세운 목표(기준) 대비 지금 | refl_goal_alignment_check |
| "지난 한 달 동안 어떻게 달라졌는지 정리해줘." | 지난 한 달(과거 구간) | refl_period_retrospective |

### ③ 되물어야(clarify) 하는 조건 비교

정책 엔진은 상위 후보 간 점수 차가 `decision.clarify_margin`(0.15) 미만이거나 확신이 `decision.clarify_confidence`(0.40) 미만이면 되묻는다 — 임계값 원천은 config다. [근거: config/experiments.yaml::decision]

| 상황 | 왜 애매한가 | 되물을 것 |
|---|---|---|
| 시간 단서가 아예 없음 — "우리 반 좀 봐줘" | 삼각지대 셋 다 성립 | "앞으로 지켜봐 드릴까요, 계획 대비 점검일까요, 지난 기간 정리일까요?" |
| 미래 지시인데 대상·행동 미특정 — "다음 주엔 좀 지켜봐줘" | watchpoint는 아이·행동 지정이 필요, 추천이면 recommend_focus | "어떤 아이의 어떤 행동을 지켜볼까요? 아니면 관찰 대상을 추천해 드릴까요?" |
| "목표"의 참조가 불명 — "목표 대비 어때?" | 주간 계획인지 학기 목표인지, 학급인지 특정 아이인지 | "어느 계획(주간/월간/학기) 기준으로 점검할까요?" |
| 과거 구간인데 대상이 아이 하나 — "지난 한 달 지호 어떻게 달라졌어?" | 학급 회고가 아니라 refl_child_progress_review·obs_detect_behavior_change 경계 | "지호 개인 발달 리뷰로 정리할까요?" |

### ④ 혼동 edge 현황 — 직원이 발견한 갭

- 온톨로지 `confusable_with`에는 **refl_goal_alignment_check ↔ refl_period_retrospective 쌍이 양방향으로 지정**돼 있고(가설 edge 1쌍 존재), 세션 운영 노트 기준 SKEPTIC 가설 edge도 이 쌍은 있다. [근거: seeds/ontology_v1.yaml::refl_goal_alignment_check.confusable_with / refl_period_retrospective.confusable_with]
- 반면 **obs_set_watchpoint의 confusable_with는 `obs_capture_scene, obs_recommend_focus`뿐**이고, refl_* 두 intent 어느 쪽도 watchpoint를 지정하지 않는다 — 즉 **watchpoint↔목표 점검, watchpoint↔기간 회고 2쌍의 가설 edge가 없다**. 삼각지대의 세 변 중 두 변이 비어 있는 이 갭은 직원(운영자) 검토에서 발견됐다. `UNKNOWN`(실제 오분류율은 시험 문항 0이라 미측정) [근거: seeds/ontology_v1.yaml::obs_set_watchpoint.confusable_with, 팩트팩 세션노트]
- 현재 confusion_edges 629개는 전부 `state=hypothesized · origin=SKEPTIC`이다 — 관측·확정된 edge는 아직 없다. edge 추가는 온톨로지 confusable_with 개정(거버넌스 경로) 또는 Arena 오답 관측(`arena.confusion_confirm_min` 3회)으로만 이뤄진다. [근거: 팩트팩 DB 스냅샷, backend/app/models/brain.py::ConfusionEdge, config/experiments.yaml::arena.confusion_confirm_min]

## 4-7. intent 수정·추가 절차 (요약)

계층이 둘로 갈린다 — **표시**는 즉시, **의미·구조**는 대기열. [근거: backend/app/api/ontology_admin.py, backend/app/models/intent_admin.py]

| 바꾸려는 것 | 경로 | 반영 시점 | 기록 |
|---|---|---|---|
| 한글 이름·화면 설명 | `PUT /v1/ontology/intents/{intent_id}/display` (PIN, 기본 2341) / CSV 일괄 `POST /v1/ontology/intents/display/bulk` | **즉시** — intent_display 오버레이만. YAML(의미)·ontology_version(replay 축) 불변 | governance_events `INTENT_DISPLAY_EDIT` / `INTENT_DISPLAY_BULK_EDIT` |
| 정의·추가·이동·삭제(DEFINITION/ADD/MOVE/DELETE/OTHER) | `POST /v1/ontology/change-requests` → 대기열(PENDING) → PIN 판정(approve/reject) | 승인은 **"반영 예약" 표시일 뿐** — 실반영은 운영자의 거버넌스 경로(§5-9 버전 규칙 minor/major, ontology_versions)로만 | governance_events `INTENT_CHANGE_DECISION` |
| positive/negative 예시문 | `seeds/ontology_examples_draft.csv` 수정 → `scripts/apply_ontology_examples.py --write` | 스크립트 실행 시 | YAML 직접 편집 금지 |
| intent_id 자체 | **어디서도 수정 불가** | — | 영역 이동조차 id 불변(KTIB 골드 라벨 보호) |

새 intent가 생겨도 `brain_nodes` 자동 INSERT는 금지다 — 노드 생성은 governance_events를 남기는 승인 플로우로만 이뤄진다(절대 규칙 4). 절차 상세와 웹 도구 화면은 11장(운영·거버넌스, [11-operations-guide.md](11-operations-guide.md)) 참조.

---

## 현재 상태

- 온톨로지 onto-2.1 · 8영역 · 70 intents: `IMPLEMENTED` — DB brain_nodes 70개와 영역별 수까지 1:1 일치. [근거: 팩트팩 DB 스냅샷]
- 위험 모델 rm-1.0(CRITICAL 7/ELEVATED 6): `IMPLEMENTED` — config `arena.critical_intents`와 정합 강제.
- 시험지 커버리지: `PARTIAL` — 8/70 의도만 문항 보유, 62개 의도 측정 불가.
- 혼동 edge: `PARTIAL` — 629개 전부 가설(hypothesized) 상태, 관측·확정 0.
- STUDIO 신규 5종 + refl_child_guidance_consult: evidence 0건 — 훈련 데이터 유입 전. `PARTIAL`
- 삼각지대 watchpoint 관련 가설 edge 2쌍 부재: `UNKNOWN`(실측 불가 상태의 설계 갭).

## 주의사항

- 이 장의 수치는 **2026-07-17 13:16 스냅샷**이다. 증산 캠페인이 실 LLM으로 가동 중이므로 evidence 수는 이미 증가하고 있을 수 있다.
- 표의 "혼동 edge(from/to)"는 전부 가설이다 — 실제 혼동률로 읽지 말 것. per-intent from/to 집계 기준과 전역 총수(629)의 관계는 팩트팩 CSV 산출 방식에 따라 다를 수 있어 표값을 그대로 옮겼다.
- 한글 이름은 intentLabels.ts의 정적 라벨 기준이다. 운영자 오버레이(intent_display, 현재 1건)가 있으면 화면 표시는 다를 수 있다.
- 온톨로지 YAML을 직접 고치지 말 것 — 예시문은 시트+스크립트, 구조는 버전 규칙(거버넌스)으로만.

## 다음 단계

1. **62개 무문항 의도의 시험지 확보** — 전문가 저작 + 2인 검수(kappa 또는 O/X 일치율)로 ktib-4 이후 커버리지 확장. 진행 도구는 `scripts/ktib_coverage.py`.
2. **STUDIO·refl_child_guidance_consult 훈련 유입** — 증산 캠페인 domain_weights(STUDIO 0.06) 경로로 evidence 0건 해소.
3. **삼각지대 edge 보강 제안** — obs_set_watchpoint↔refl_goal_alignment_check / ↔refl_period_retrospective 쌍을 confusable_with에 추가하는 변경 제안을 대기열에 접수(실반영은 거버넌스 경로).
4. 표시 이름 오버레이(1건)와 정적 라벨의 정기 대사 — 어긋난 채 방치되지 않게.
