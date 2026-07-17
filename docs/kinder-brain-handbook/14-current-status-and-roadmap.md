# 14. 현재 상태와 로드맵 — 2026-07-17 실측 스냅샷

> **한눈에 보기** — 파이프라인(설계·구현·테스트)은 사실상 완비 상태이고, 병목은 단 하나 — **사람 검수(2인 → GOLD)** 다. 이 관문이 열리면 대표 예문 → 첫 유효 점수 → 승격 루프가 연쇄로 켜진다. 11월 기준 Must는 "일반 의도 시험 확충·유효 점수·개인정보 절차·연결 리허설" 4묶음이다.

---

## 1. 영역별 상태 표 (실측)

| 영역 | 설계 | 구현 | 데이터 | 테스트 | 현재 병목 | 다음 액션 | 11월 필수 | 담당 |
|---|---|---|---|---|---|---|---|---|
| 온톨로지(70의도) | v1.5 | IMPLEMENTED | onto-2.1 활성 | ✅ | 62의도 시험 0 | 일반 의도 출제 | **Must** | 기획+검수자 |
| 추론 API(mode=gym) | §3 | IMPLEMENTED | inference_logs 764 | ✅(21) | — | 유지 | Must(이미 충족) | 개발 |
| 즉석 문답·evidence | §6-7 | IMPLEMENTED | GYM_HUMAN 33 | ✅(19+) | 사용량 | 직원 사용 확대 | Should | 훈련자 |
| 증산(campaign) | §1 | IMPLEMENTED | 진행 중(+400·+340) | ✅ | 과금·시간 | 완주 확인 | Should | 운영자 |
| 2인 검수(GOLD) | §3-3 | IMPLEMENTED(웹+CLI) | **TRAIN GOLD 0** · 대기 91+ | ✅(6+) | **사람 시간** ← 전체 병목 | 두 검수자 실행 | **Must** | 검수자 2인 |
| 대표 예문·임베딩 | §5 | IMPLEMENTED(자동 체인) | **0개** | ✅ | GOLD 종속 | 검수 후 자동 | **Must** | 자동 |
| 시험지(KTIB) | §8-2 | IMPLEMENTED | ktib-3 386문항(8/70 의도) | ✅ | 커버리지 | 62의도 문항 | **Must** | 검수자 |
| Arena 채점·반영 | §8 | IMPLEMENTED | brain 3run(0.0%)·baseline 88.1% | ✅(12) | 대표 예문 0 가드 | 첫 유효 채점 | **Must** | 운영자 |
| version gate·승격 | §6-6 | IMPLEMENTED | brain_versions 0행 | ✅ | GOLD 200 | 자동 대기 | Should | 자동 |
| 혼동 edge | §5-6 | IMPLEMENTED | 629 전부 가설 | ✅ | 실측 0 | 채점 후 확정 시작 | Should | 자동 |
| 관측실(3D·대시보드·TODO) | §7 | IMPLEMENTED | live | ✅(177) | — | 유지 | Should | 개발 |
| 애매 발화 리포트 | 투트랙 B′ | IMPLEMENTED | 교정 13건 등 | ✅(5) | — | 운영 활용 | Should | 운영자 |
| 의도 관리(표시·제안) | 07-17 | IMPLEMENTED | display 1·제안 0 | ✅(6) | — | 직원 사용 | Could | 운영자 |
| 킨더버스 연동(서빙) | runtime | **HOLD(설계)** | — | — | 게이트 전 금지 | 계약 동결·리허설 | **Must(준비)** | 개발+킨더버스 |
| Shadow 0a 거버넌스 | runtime §2 | DESIGNED | — | — | 문서·절차 없음 | 7항목 작성 | **Must** | 기획+법무 |
| 개인정보·동의·보존 | — | **GAP** | — | — | 정책 부재 | 정책 수립 | **Must** | 법무+기획 |
| 실사용 지표 | 트랙2 | PLANNED | — | — | 오픈 전 불가 | 설계만 선행 | Later | 데이터 |

## 2. 스냅샷 수치 (읽기 전용 쿼리, 2026-07-17)

episodes 2,729(TRAIN 2,343 / BENCHMARK 386) · states: REJECTED 2,229(모의 정리 포함)·LABELED 386·LABEL_CANDIDATE 91·ACCUMULATING 23 · GOLD 386(전부 시험지) · evidence 3,529(사람 확인 50·교정 13) · exemplar 0 · KTIB ktib-3 386문항(8/70) · arena 4run(brain 0.0%×3, baseline 88.1%) · confusion 629(전부 hypothesized) · brain_versions 0 · review_votes 10 · atlas 큐 0 · governance 43건.

## 3. 로드맵

| 시기 | 내용 |
|---|---|
| **지금(7월)** | 증산 완주 → **2인 검수 스프린트** → 첫 TRAIN GOLD·대표 예문 → 채점 버튼 자동 점등 → **첫 유효 점수**(>0) — 성장 사이클 개통 |
| **11월 전** | 일반 62의도 시험 문항 확충(의도당 10~30) · GOLD 200 → 첫 candidate·promote · 삼각지대 최소대립 문항 실측 · Shadow 0a 거버넌스 7항목 · 개인정보/동의/보존 정책 · 계약 동결·스테이징 리허설 · 롤백 리허설 1회 |
| **11월 오픈** | Seed Brain API 탑재 · 의도별 단계 개시(대부분 Shadow/Suggest, CRITICAL은 Confirm) · 오픈 최소 기준 9항목 통과 확인 |
| **오픈 직후** | 실발화 수집(0a→0b) · 애매 발화 리포트의 live/shadow 축 가동 · 실사용 지표 첫 측정 |
| **실데이터 축적 후** | 현장형 candidate 승격 반복 · 삼각지대 등 경계의 실교사 검증 · 커버리지 확대 |
| **장기** | first intent accuracy **96%** · CWAR ≤2% 실측 유지 · 자연어 단일 인터페이스(slot·action 층) |

## 4. 11월 우선순위 — Must / Should / Could / Later

- **Must**: ① 2인 검수 → 유효 점수 개통 ② 일반 의도 KTIB 확충(현 8/70) ③ 개인정보·동의·보존 정책 + Shadow 0a 거버넌스 ④ 계약 동결·연동 리허설·롤백 리허설 ⑤ 오픈 기준 9항목 판정
- **Should**: GOLD 200·첫 promote / 혼동 edge 첫 confirmed / 삼각지대 실측 / 애매 리포트 운영 정착 / 직원 훈련 사용 확대
- **Could**: 의도 표시명 정비(웹 도구) / macro accuracy 병행 보고 / top-k recall 지표
- **Later**: slot·action plan 층 / 실사용 성공지표 대시보드 / 웹서치 소스 인제스트(S1 실연결)

## 점검 리스트 (요청 항목별 한 줄 판정)
인간 앵커 **없음(0)** → 최우선 / KTIB **386(8의도)** → 확충 / GOLD **시험지용만** / exemplar·임베딩 **0** / Arena **체계 완비·유효점수 0** / ambiguity report **가동** / confusion triangle **가설 1쌍뿐 — 문항·교정으로 실측 필요** / API 안정성 **테스트 746+·재연결 자가치유** / rollback **구조 있음·리허설 필요** / 개인정보 **GAP** / Shadow 통합 **문서 단계** / 실사용 지표 **미착수(정상)**.

## 주의사항
- 이 표의 "병목=사람"은 비난이 아니라 설계다 — 자가 채점을 막는 대가로 사람의 시간이 관문이 된다. 관문 통과를 쉽게 만드는 도구(웹 검수·추천·TODO)는 이미 배치됐다.

## 다음 단계
- 실무 절차: [11-operations-guide.md](11-operations-guide.md) · 갭 상세: [17-open-questions-and-gaps.md](17-open-questions-and-gaps.md)
