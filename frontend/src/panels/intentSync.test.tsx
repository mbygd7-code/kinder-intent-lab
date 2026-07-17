/**
 * @vitest-environment jsdom
 *
 * 의도 카탈로그 동기화 AC (2026-07-18 연결 점검) — 서버(/v1/ontology/intents)가
 * 검수·훈련·즉석 문답의 의도 라벨·목록 원천이고, 실패하면 정적 사전 폴백으로 계속 돈다.
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { labelOf, setIntentLabelOverrides } from './intentLabels'
import { syncIntentCatalog } from './intentSync'
import { LiveQuizPanel } from './LiveQuizPanel'

const CATALOG = {
  ontology_version: 'onto-2.1',
  total: 2,
  items: [
    { intent_id: 'op_notice_send', domain: 'OPERATION', definition: '', example_count: 2, name_ko: '알림장 발송(수정)', description_ko: null },
    { intent_id: 'comm_new_thing', domain: 'COMMUNICATION', definition: '', example_count: 2, name_ko: '새 소통 의도', description_ko: null },
  ],
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  setIntentLabelOverrides({}) // 전역 오버레이 누수 방지 — 테스트 간 격리
})

describe('syncIntentCatalog', () => {
  it('서버 이름(name_ko)이 전역 라벨에 반영되고 id 목록을 돌려준다', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => CATALOG }) as Response))
    const ids = await syncIntentCatalog()
    expect(ids).toEqual(['op_notice_send', 'comm_new_thing'])
    expect(labelOf('op_notice_send')).toBe('알림장 발송(수정)')
    expect(labelOf('comm_new_thing')).toBe('새 소통 의도')
  })

  it('실패하면 null — 기존 오버레이를 지우지 않는다(마지막 성공 상태 유지)', async () => {
    setIntentLabelOverrides({ op_notice_send: '이전 오버레이' })
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 500, json: async () => ({}) }) as Response))
    expect(await syncIntentCatalog()).toBeNull()
    expect(labelOf('op_notice_send')).toBe('이전 오버레이')
  })
})

describe('LiveQuizPanel — 직접 찾기 우주에 서버 카탈로그 병합', () => {
  it('노드 목록에 없는 새 의도도 검색에 나온다(추측 불가 발화 → 정답 찾기)', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const u = String(url)
      if (u.includes('/v1/ontology/intents'))
        return { ok: true, json: async () => CATALOG } as Response
      if (u.includes('/v1/intent/infer'))
        return {
          ok: true,
          json: async () => ({ request_id: 'REQ_1', top_intent: null, decision: 'abstain', intent_candidates: [] }),
        } as Response
      return { ok: false, status: 404, json: async () => ({}) } as Response
    }))
    render(<LiveQuizPanel onClose={() => {}} />)
    fireEvent.change(screen.getByPlaceholderText(/블록놀이 사진/), { target: { value: '완전 새로운 말' } })
    fireEvent.click(screen.getByRole('button', { name: '브레인에게 물어보기' }))
    fireEvent.click(await screen.findByRole('button', { name: '정답 의도 찾기' }))
    fireEvent.change(screen.getByPlaceholderText(/의도 이름 검색/), { target: { value: '새 소통' } })
    expect(await screen.findByRole('button', { name: /새 소통 의도/ })).toBeTruthy()
  })
})
