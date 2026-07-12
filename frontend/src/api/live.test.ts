/**
 * 즉석 문답 API 순수 로직 — Core 요청 빌더(규칙 5 무오염)와 후보 상위 선별.
 */
import { describe, expect, it } from 'vitest'

import { buildInferRequest, topCandidates } from './live'

describe('buildInferRequest', () => {
  it('mode=gym 최소 Core 요청 — 필수 필드 전부, 훈련 메타(정답류) 없음', () => {
    const req = buildInferRequest('사진 좀 정리해줘', 'TR_test') as Record<string, unknown>

    expect(req.mode).toBe('gym')
    expect(req.schema_version).toBe('core-1.0')
    expect(String(req.request_id)).toMatch(/^REQ_LIVEQ_/)
    expect(req.session).toMatchObject({ surface_type: 'workspace', conversation_history: [] })
    expect(req.prompt).toEqual({ text: '사진 좀 정리해줘', lang: 'ko', input_method: 'typed' })
    expect(req.workspace_context).toEqual({ objects: [], selection: [] })
    expect(req.recent_actions).toEqual([])
    expect(req.teacher_context).toMatchObject({ teacher_ref: 'TR_test' })

    // 절대 규칙 5: Core에 정답·훈련 메타가 들어갈 자리 자체가 없다
    const keys = Object.keys(req)
    for (const banned of ['chosen_intent', 'ground_truth', 'scenario_id', 'target_confusion']) {
      expect(keys).not.toContain(banned)
    }
    expect(req.gym_extension).toBeUndefined()
  })

  it('호출마다 고유 request_id/session_id (멱등 추적 가능)', () => {
    const a = buildInferRequest('x', 'TR') as { request_id: string; session: { session_id: string } }
    const b = buildInferRequest('x', 'TR') as { request_id: string; session: { session_id: string } }
    expect(a.request_id).not.toBe(b.request_id)
    expect(a.session.session_id).not.toBe(b.session.session_id)
  })
})

describe('topCandidates', () => {
  it('점수 내림차순 상위 4개만 — 화면엔 3~4 후보(§7-4 톤)', () => {
    const raw = [
      { intent_id: 'a', score: 0.1 },
      { intent_id: 'b', score: 0.5 },
      { intent_id: 'c', score: 0.3 },
      { intent_id: 'd', score: 0.2 },
      { intent_id: 'e', score: 0.4 },
    ]
    const top = topCandidates(raw)
    expect(top.map((c) => c.intent_id)).toEqual(['b', 'e', 'c', 'd'])
  })

  it('빈/부재 입력은 빈 배열 — abstain을 지어내지 않고 그대로 표현', () => {
    expect(topCandidates(undefined)).toEqual([])
    expect(topCandidates([])).toEqual([])
  })
})
