# PHASE 4 — Growth Loop (3주)

목표: 클릭 → 진단 → 전략 → 훈련 → 검증 → 성장 루프 완성. 나침반은 문서 §6-7.

## T4.1 Weakness 진단 엔진 (4축 실계산)
- 산출: Ambiguous Language(Atlas 경쟁 intent 수) / Screen Context Coverage / Persona Diversity(엔트로피) / Gold Data — 노드별 계산 배치
- AC: §7-3 표의 계산 정의와 1:1 · fixture 노드로 4축 값 검증
- 참조: §7-3

## T4.2 Challenge Pack 생성기
- 산출: 진단→전략 매핑(§6-1: A/B/C/D, 복합 조합), 우선순위 샘플링(§6-3), contrast exemplar 활용(C형)
- AC: COVERAGE_LOW → A형은 사람 세션 없이 Foundry 작업 큐로 발행 · CONFUSION_HIGH → target_edges 포함 pack · pack 스키마 검증
- 참조: §6-1·§6-3·§6-4

## T4.3 클릭-투-트레인 E2E
- 산출: "강화하기" 버튼 → pack 브리핑 화면(§7-4 목업) → Gym 세션 → evidence → aggregator → 노드 size/density 갱신 + pending ring
- AC: **§6-7 Trace [0]~[6] 재현 통합 테스트** (brightness 불변 포함)
- 참조: §6-7, 절대 규칙 3

## T4.4 Fast Update 안전 규칙
- 산출: teacher prior 미세 조정 — `fast_min_samples`·`fast_delta_cap`·`weekly_decay`·버전 롤백
- AC: 표본 미달 시 no-op · 상한 초과 조정 거부 · 롤백 후 state_version 복원
- 참조: §6-5

## T4.5 Version Gate + Candidate Build
- 산출: 후보 생성 조건(`min_new_gold` 등) 감시, candidate 빌드(exemplar/prior/edge 갱신본), brain_versions 기록
- AC: 조건 미달 시 candidate 미생성 · candidate가 현행 버전을 건드리지 않음(불변성)
- 참조: §6-6

## T4.6 Promote / Reject 파이프라인
- 산출: Arena 결과 기반 promote 규칙 평가, promote 시 노드 brightness 갱신 + ring 소등 + Resonance 이벤트, reject 시 evidence 보존 + 원인 리포트
- AC: region 회귀 존재 시 promote 차단 테스트 · reject 후 evidence 카운트 불변
- 참조: §6-6, §8-2

**Phase 4 완료 게이트:** Trace [0]~[6] 통합 테스트 상시 green + Version Gate 1회전(candidate→arena→판정) 성공.
