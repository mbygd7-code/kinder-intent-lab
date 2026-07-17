/**
 * intent_id → 한글 라벨 (유아교사 톤). Gym·패널이 기계 id 대신 이걸 보여준다.
 *
 * 원천은 온톨로지 정의(seeds/ontology_v1.yaml) — 여기 라벨은 그 정의를 유아교사가 쓰는 짧은
 * 말로 옮긴 표현이다. 지금은 프론트 프레젠테이션 상수(향후 온톨로지 label_ko로 이관 가능).
 * 미등록 id는 fallback으로 id를 사람이 읽기 쉬운 형태로 정리해 보여준다(값 날조 아님).
 */
export const INTENT_LABEL_KO: Record<string, string> = {
  // PLAY
  play_expand: '놀이 더 키우기',
  play_transition_next_step: '다음 활동 제안',
  play_flow_naturalize: '놀이 흐름 다듬기',
  play_material_suggest: '놀잇감 추천',
  play_scenario_generate: '놀이 시나리오 만들기',
  play_inquiry_question: '발문(질문) 만들기',
  play_level_adapt: '난이도 맞추기',
  play_revive_stalled: '시든 놀이 살리기',
  play_environment_setup: '놀이 환경 꾸미기',
  // OBSERVATION
  obs_record_moment: '순간 관찰 기록',
  obs_capture_scene: '활동 장면 담기',
  obs_tag_children: '사진 속 아이 태그',
  obs_classify_development: '발달 영역 분류',
  obs_summarize_child: '아이별 관찰 요약',
  obs_detect_behavior_change: '행동 변화 감지',
  obs_recommend_focus: '관찰 포커스 추천',
  obs_set_watchpoint: '관찰 포인트 설정',
  obs_search_records: '관찰 기록 검색',
  // DOCUMENT
  text_naturalize: '글 자연스럽게 다듬기',
  write_activity_followup: '활동 후속 기록 쓰기',
  doc_observation_record: '관찰 기록문 쓰기',
  doc_notice_draft: '알림장 초안 쓰기',
  doc_plan_draft: '활동계획안 쓰기',
  doc_summarize: '글 요약하기',
  doc_expand_text: '짧은 메모 늘려 쓰기',
  doc_proofread: '맞춤법 교정',
  doc_portfolio_comment: '포트폴리오 코멘트 쓰기',
  // VISUAL
  visual_naturalize: '사진 자연스럽게 보정',
  visual_layout_refine: '게시물 배치 다듬기',
  visual_photo_organize: '사진 정리',
  visual_photo_pick_best: '베스트 사진 고르기',
  visual_privacy_mask: '얼굴 모자이크 처리',
  visual_crop_focus: '사진 크롭·확대',
  visual_decorate: '사진 꾸미기',
  // STUDIO (onto-2.0 B안: visual_image_generate 이동 · onto-2.1: 콜라주 이동 — id 불변)
  visual_image_generate: '그림 만들기',
  visual_collage_compose: '콜라주 만들기',
  studio_worksheet_generate: '활동지 만들기',
  studio_video_generate: '활동 영상 만들기',
  studio_slides_draft: '슬라이드 만들기',
  studio_game_generate: '게임 만들기',
  studio_topic_web_generate: '주제망 만들기',
  studio_external_resource_search: '외부 자료 찾기',
  // COMMUNICATION
  comm_draft_parent_notice: '학급 알림장 쓰기',
  comm_message_individual_parent: '개별 학부모 메시지',
  comm_share_media_with_parents: '학부모에 사진 공유',
  comm_share_with_colleague: '동료 교사와 공유',
  comm_present_to_children: '아이들에게 보여주기',
  comm_schedule_send: '발송 예약',
  comm_translate_for_family: '가정용 번역',
  comm_collect_parent_responses: '학부모 회신 모으기',
  comm_request_consent: '동의 요청 보내기',
  // OPERATION
  op_schedule_update: '일정 업데이트',
  op_schedule_check: '일정 확인',
  op_material_prepare: '준비물 챙기기',
  op_document_export: '문서 내보내기',
  op_attendance_record: '출결 기록',
  op_notice_send: '알림 보내기',
  op_workspace_organize: '자료 정리',
  op_workspace_search: '자료 검색',
  op_workspace_delete: '자료 삭제',
  // REFLECTION
  refl_activity_review: '활동 돌아보기',
  refl_child_progress_review: '아이 성장 돌아보기',
  refl_milestone_check: '발달 이정표 점검',
  refl_goal_alignment_check: '목표 점검',
  refl_self_journal: '교사 성찰일지',
  refl_teaching_pattern_insight: '수업 패턴 살펴보기',
  refl_improvement_suggest: '개선점 제안',
  refl_support_need_scan: '지원 필요한 아이 찾기',
  refl_period_retrospective: '기간 회고',
  refl_child_guidance_consult: '아이 지도 상담',
}

/** 운영자가 PIN으로 고친 표시 이름(intent_display 오버레이) — 정적 라벨보다 우선 */
const LABEL_OVERRIDES: Record<string, string> = {}

/** 서버 오버레이 반영 — 의도 목록 로드 시 호출(이름 수정이 앱 전역에 즉시 보이게) */
export function setIntentLabelOverrides(overrides: Record<string, string>): void {
  for (const k of Object.keys(LABEL_OVERRIDES)) delete LABEL_OVERRIDES[k]
  Object.assign(LABEL_OVERRIDES, overrides)
}

/** 한글 라벨. 오버레이 > 정적 라벨 > 밑줄을 공백으로 바꾼 원 id(날조 없이 그대로) */
export function labelOf(intentId: string): string {
  return LABEL_OVERRIDES[intentId] ?? INTENT_LABEL_KO[intentId] ?? intentId.replace(/_/g, ' ')
}

/** Gym 3모드 한글 이름 (유아교사 톤) */
export const GYM_MODE_LABEL_KO: Record<string, string> = {
  guess_my_intent: '의도 알아맞히기',
  choose_right_meaning: '알맞은 의미 고르기',
  correction_drill: '바로잡기 연습',
}
