/**
 * @vitest-environment jsdom
 *
 * INSIGHT · 애매 발화 카드 AC (투트랙 B′) — 출처 분리 표시·한글 라벨·빈 상태 정직성·CSV 버튼.
 */
import { cleanup, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { AmbiguityReport } from '../api/observatory'
import { useBrainStore } from '../brain3d/store'
import { AmbiguityCard } from './AmbiguityCard'

const REPORT: AmbiguityReport = {
  thresholds: { clarify_margin: 0.15, clarify_confidence: 0.4 },
  sources: [
    {
      source: 'gym', total: 12, ambiguous: 5,
      top_ambiguous_intents: [{ intent_id: 'obs_set_watchpoint', count: 3 }],
    },
  ],
  corrections: [
    {
      utterance: '관찰 포인트 잡아줘', chosen: 'obs_set_watchpoint',
      guessed: 'refl_goal_alignment_check', origin_channel: 'GYM_HUMAN', created_at: null,
    },
  ],
  unclassified: [{ utterance: '분류 안 되는 말', status: 'PENDING', created_at: null }],
}

const EMPTY: AmbiguityReport = {
  thresholds: { clarify_margin: 0.15, clarify_confidence: 0.4 },
  sources: [], corrections: [], unclassified: [],
}

function stub(report: AmbiguityReport) {
  vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => report }) as Response))
}

beforeEach(() => {
  useBrainStore.setState({ reloadNonce: 0 })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('AmbiguityCard', () => {
  it('출처(오픈 전/실험실)별 집계와 애매 의도가 한글 라벨로 보인다', async () => {
    stub(REPORT)
    render(<AmbiguityCard />)
    expect(await screen.findByText(/오픈 전 · 실험실/)).toBeTruthy()
    expect(screen.getByText(/12건 중/)).toBeTruthy()
    expect(screen.getByText(/관찰 포인트 설정 3건|3건/)).toBeTruthy()
    expect(screen.getByRole('button', { name: /CSV 내려받기/ })).toBeTruthy()
  })

  it('사람 교정 사례에 뇌 추측 → 사람 정답이 그대로 보인다', async () => {
    stub(REPORT)
    render(<AmbiguityCard />)
    expect(await screen.findByText(/"관찰 포인트 잡아줘"/)).toBeTruthy()
  })

  it('빈 상태: 지어내지 않고 안내만 — CSV 버튼도 없다', async () => {
    stub(EMPTY)
    render(<AmbiguityCard />)
    expect(await screen.findByText(/아직 애매 발화 데이터가 없어요/)).toBeTruthy()
    expect(screen.queryByRole('button', { name: /CSV/ })).toBeNull()
  })

  it('형식이 아닌 응답(다른 JSON)이 오면 카드를 그리지 않는다 (부분 렌더 금지)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, json: async () => ({ nodes: [] }) }) as Response))
    const { container } = render(<AmbiguityCard />)
    await waitFor(() => expect(vi.mocked(fetch).mock.calls.length).toBeGreaterThan(0))
    expect(container.querySelector('section')).toBeNull()
  })
})
