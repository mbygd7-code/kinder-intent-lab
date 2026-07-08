# PHASE 3 — Seed Brain + 3D Brain MVP + Gym (3~4주)

주의: 3D Brain은 별도 대시보드가 아니라 **시스템의 첫 화면**이다. Gym보다 먼저 붙인다.

## T3.1 Seed Brain Backfill (S13)
- 산출: 노드별 exemplar 선정(diversity 기준 `exemplar_min_dist`), evidence_stats 집계, pgvector 인덱스
- AC: 분포 라벨(BRONZE/SILVER)은 exemplar 채택 안 됨(가중 귀속만) 테스트
- 참조: §5-7

## T3.2 추론 파이프라인 4단계
- 산출: `app/brain/` — [1] retrieval(≤`retrieval_top_k`, exemplar+Atlas 매치) [2] LLM scorer(신호 명시 프롬프트) [3] prior 재정렬(**LLM 밖에서** 곱, cap) [4] 정규화+margin
- AC: 4단계 각각의 기여가 inference_log에 분리 기록 · persona 조회 실패 시 default prior + `fallback_used` · 응답에 `persona_state_version` 포함
- 참조: §5-4·§5-5, 절대 규칙 5

## T3.3 `POST /v1/intent/infer` (mode=gym)
- 산출: infer 라우터 + decision 정책 엔진(clarify/abstain — config `decision.*`)
- AC: **훈련 메타데이터가 Core 필드에 들어오면 400** · margin<`clarify_margin` 시 decision=clarify · 스키마 왕복 테스트
- 참조: runtime §3-0·§3-1·§4 (계약만 차용 — live 서빙 코드 아님)

## T3.4 3D Brain 뼈대 (R3F)
- 산출: `frontend/src/brain3d/` — 노드=intent 수(instanced mesh), region 7 고정 좌표, 회전/줌, 장식 파티클 분리 레이어, 2D fallback
- AC: 노드 수 100 기준 상호작용 프레임 유지(개발 머신) · region 색+라벨+위치 3중 인코딩
- 참조: §7-1·§7-5, §5-10

## T3.5 시각 인코딩 바인딩
- 산출: size=evidence 총량, density=diversity, pulse=추론 활성, pending ring, brightness=`heldout_accuracy`(**null이면 Dormant 어둡게**)
- AC: brightness 값의 유일한 소스가 arena 결과 필드임을 프론트 코드 리뷰 체크리스트로 고정 · 훈련 이벤트로 brightness 변화 없음 테스트(모킹)
- 참조: §7-5·§7-6, 절대 규칙 3

## T3.6 Zoom 1·2 패널
- 산출: Region 패널(Reliability/Coverage/Gold·Synthetic 분리 표기/Top Weak Nodes), Node 패널(방향성 혼동 목록 + WHY WEAK 4축 — 이 단계는 계산값 mock)
- AC: 문서 §7-2·§7-3 목업과 필드 1:1 대응
- 참조: §7-2·§7-3

## T3.7 Gym 3모드
- 산출: Guess My Intent / Choose the Right Meaning / Correction Drill — 세션 기록 → evidence 적재(actor_type=TEACHER_TRAINER 등)
- AC: 교정 세션이 HUMAN_CORRECTION evidence 생성 · recovery_turns 기록 · adversarial 기본 false
- 참조: §8-1

**Phase 3 완료 게이트:** 뇌 화면에서 노드 클릭 → 패널 → (mock pack) 훈련 세션 → evidence 적재까지 클릭 한 줄로 이어짐.
