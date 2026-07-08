# Kinder Intent Lab — 개발 시작 가이드

Kinder Intent Brain(교사 의도 추론 엔진 + 3D Brain 훈련 조종석)의 개발 패키지.
설계 배경: `docs/01-foundry/` 참조. 이 폴더 그대로 Claude Code로 개발을 시작할 수 있다.

## 시작 순서

```bash
# 1. 이 폴더를 저장소로
git init && git add -A && git commit -m "chore: kinder-intent-lab seed package"

# 2. Claude Code 실행
claude
```

첫 프롬프트 추천:

```text
CLAUDE.md를 읽고, tasks/PHASE-1-foundation.md의 T1.1부터 시작해줘.
티켓마다 Acceptance Criteria를 테스트로 먼저 작성하고 구현해.
티켓 하나 끝날 때마다 결과를 보고하고 멈춰.
```

이후 세션: `다음 티켓 진행해줘` 만으로 이어진다 (Claude Code가 tasks/ 순서를 따른다).

## 패키지 내용물

| 경로 | 역할 |
|---|---|
| `CLAUDE.md` | Claude Code가 자동으로 읽는 프로젝트 지침 — 절대 규칙 10개 포함 |
| `docs/` | 설계 문서 (진실의 원천) |
| `schemas/` | 계약 JSON Schema 7종 — 코드보다 먼저 존재하는 계약 |
| `config/experiments.yaml` | 모든 임계값 (코드 하드코딩 금지) |
| `db/migrations/001_init.sql` | 테이블 + 핵심 무결성 CHECK |
| `tasks/PHASE-1~5` | 티켓 백로그 (산출물·AC·문서 § 참조) |

## 개발 순서 개요

1. **Phase 1** Foundation — 스캐폴드, DB, 계약, Ontology 시드, Foundry S1~S10, Pilot 500
2. **Phase 2** Foundry Scale — 10~30k 생성, Atlas v1, Persona 클러스터링
3. **Phase 3** Seed Brain + 3D Brain MVP + Gym 3모드
4. **Phase 4** Growth Loop — 진단 엔진, Challenge Pack, Version Gate
5. **Phase 5** Arena/KTIB — 베이스라인 측정, 80% 도전

최종 검증 기준은 설계 문서 §6-7 End-to-End Trace: **어두운 노드 클릭 → … → Arena 통과 → 노드가 밝아진다**의 [0]~[9] 체인이 끊김 없이 동작하는 것.

## 주의

- 킨더버스 live 연동 코드는 이 단계에서 작성하지 않는다 (runtime 문서는 PARTIAL HOLD)
- `docs/`를 수정하면 반드시 해당 문서 상단 Change Log에 항목을 추가한다
