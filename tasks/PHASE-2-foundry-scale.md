# PHASE 2 — Foundry Scale (3~4주)

전제: Phase 1 Pilot 게이트 통과.

## T2.1 배치 러너 스케일화
- 산출: 체크포인트·재시작 가능한 배치 실행기, 실패 에피소드 격리 큐
- AC: 중단 후 재시작 시 중복 생성 0 (dedup_hash 기준) · 배치별 비용 단가 리포트

## T2.2 Atlas v1
- 산출: pattern coverage 지표, 미매핑 발화 → Atlas 확장 큐, Simulator 통계 재보정 훅
- AC: coverage 계산 테스트 · 확장 큐 적재 테스트
- 참조: §2-4

## T2.3 Persona 행동 벡터화 + 클러스터링
- 산출: trainer 행동 벡터 빌더, HDBSCAN(파라미터 config), 클러스터 리포트(8축 가설 대조표)
- AC: 합성 fixture로 클러스터 재현성 테스트 · persona_clusters·population_priors 적재
- 참조: §4-1·§4-2

## T2.4 Prior 테이블 + persona_state_version
- 산출: population/teacher prior CRUD, state_version 발급(변경 시 새 버전)
- AC: prior 조회가 항상 state_version과 함께 반환 · cap(`persona_prior_cap`) 적용 테스트
- 참조: §5-3, 절대 규칙 (replay)

## T2.5 10k~30k 생성 캠페인
- 산출: 캠페인 설정(도메인 배분 — DOCUMENT+VISUAL 우선), 주간 품질 리포트
- AC: reject율·consensus·단가가 Pilot 대비 악화되지 않음 (악화 시 자동 중단)
- 참조: §10-2 Phase 2

**Phase 2 완료 게이트:** Episode Bank ≥ 10k · Atlas coverage 상승 추세 · persona cluster v1 존재.
