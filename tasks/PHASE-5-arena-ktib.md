# PHASE 5 — Arena / KTIB (2주~)

## T5.1 KTIB 구성기
- 산출: `BENCHMARK_HOLDOUT ∧ GOLD ∧ LABELED ∧ 비합성`만 선별, ktib_version 발급, visual_semantics extractor 동결
- AC: 합성 에피소드 유입 시도가 DB constraint로 차단됨을 통합 테스트로 재확인 · extractor 재추출 시 새 ktib_version 강제
- 참조: §8-2, 절대 규칙 2

## T5.2 Zero-shot 베이스라인
- 산출: 범용 LLM zero-shot 러너 + 리포트 — **이 결과로 80% 목표·Stage 게이트 수치 재확정 제안서 생성**
- AC: 베이스라인 리포트에 노드/도메인별 분해 포함
- 참조: §8-2 베이스라인 규칙

## T5.3 Arena 러너
- 산출: 노드/region/global heldout accuracy, 방향성 confusion matrix, calibration(ECE), replay 4버전 기록(model/ontology/persona_state/extractor)
- AC: 동일 입력·동일 4버전으로 재실행 시 결과 재현 · confusion matrix가 confusion_edges(state=confirmed) 갱신
- 참조: §8-2, §5-6

## T5.4 Arena → Observatory 반영
- 산출: arena 결과만 brightness·edge flicker 갱신하는 반영 잡, Persona Overlay(클러스터별 활성 분포)
- AC: arena 외 코드 경로에서 brightness UPDATE 시도 시 실패(권한/가드) 테스트
- 참조: §7-5·§7-6, 절대 규칙 3

## T5.5 최종 통합: End-to-End Trace [0]~[9]
- 산출: **문서 §6-7 전체 체인의 자동 통합 테스트** — 어두운 노드 클릭부터 promote 후 노드가 밝아지고 Resonance가 발동하기까지
- AC: [0]~[9] 각 단계의 산출물(pack, evidence, aggregation, candidate, arena run, promote)이 DB에 계보로 남고 체인이 무중단 통과
- 참조: §6-7

**Phase 5 완료 게이트 = 프로젝트 1차 목표:** KTIB First Intent Accuracy 80% 도전 사이클 가동. 80% + 안전 지표 2주 유지 시 runtime 문서(v0.2) live 경로 부활 논의.

---

참고: Shadow 0a(Distribution Capture)는 거버넌스 7항목(runtime §2) 충족 시 Phase 2~3 중에도 별도 트랙으로 병행 가능 — 킨더버스 팀 협의 필요(TBD-1·5·6).
