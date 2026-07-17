/**
 * @vitest-environment jsdom
 *
 * 공부 검수(2인 → GOLD) 웹 플로우 AC — blind 큐·표 제출·확정 결과 표기 (투트랙 세트 ④).
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { GoldReviewPanel } from './GoldReviewPanel'

const QUEUE = {
  reviewer: '명배영',
  total_reviewable: 2,
  my_done: 0,
  items: [
    {
      episode_id: 'EP_1', teacher_prompt: '알림장 지금 보내줘', lang: 'ko',
      origin_channel: 'FOUNDRY_SYNTHETIC',
      situation: {
        surface_type: 'play_board',
        selection: { type: 'photo', count: 1 },
        recent_actions: ['move_object'],
        objects_summary: { photo: 2, text: 1 },
      },
      same_text_total: 3,
      same_text_index: 2,
    },
  ],
}
const STATUS = { reviewable_total: 2, ready_total: 0, reviewers: [] }

// 추천 코퍼스(정적 예문 사전) 스텁 — 큐 발화("알림장 지금 보내줘")와 겹치는 예문 1행
const CORPUS_CSV = [
  '의도 id,의도,뜻,구분,예시,X',
  'op_notice_send,알림 보내기,,기존1,알림장 지금 바로 보내줘요,',
  'visual_naturalize,사진 자연스럽게 보정,,기존1,역광이라 얼굴이 어두운데 살려줘,',
].join('\n')

function stub(overrides: Record<string, unknown> = {}) {
  const calls: Array<{ url: string; body?: unknown }> = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const u = String(url)
    calls.push({ url: u, body: init?.body ? JSON.parse(String(init.body)) : undefined })
    if (u.includes('ontology_examples_draft.csv'))
      return { ok: true, text: async () => CORPUS_CSV } as Response
    if (u.includes('/review/queue')) return { ok: true, json: async () => QUEUE } as Response
    if (u.includes('/review/status')) return { ok: true, json: async () => STATUS } as Response
    if (u.includes('/review/vote'))
      return { ok: true, json: async () => ({ ok: true, vote_id: 'RV_1', updated: false }) } as Response
    if (u.includes('/review/apply'))
      return {
        ok: true,
        json: async () => ({
          labeled: 3, rejected: 0, unchanged: 1, kappa: 0.72, exemplars_added: 3,
          message: '확정 3건(GOLD) · 폐기 0건 · 보류 1건 · 대표 예문 +3',
          ...overrides,
        }),
      } as Response
    return { ok: false, status: 404, json: async () => ({}) } as Response
  }))
  return calls
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('GoldReviewPanel', () => {
  it('이름 입력 → 시작 → blind 발화 카드(제안 없음) → 의도 선택이 표로 저장된다', async () => {
    const calls = stub()
    render(<GoldReviewPanel onClose={() => {}} onApplied={() => {}} />)

    fireEvent.change(screen.getByPlaceholderText(/예: 명배영/), { target: { value: '명배영' } })
    fireEvent.click(screen.getByRole('button', { name: '검수 시작' }))

    expect(await screen.findByText(/"알림장 지금 보내줘"/)).toBeTruthy()
    // blind — 앵커링 힌트(집계 제안·추천 의도·다른 검수자 표)가 화면에 없어야 한다
    expect(screen.queryByText(/집계 제안|추천 의도|다른 검수자/)).toBeNull()

    fireEvent.change(screen.getByPlaceholderText(/의도 검색/), { target: { value: '알림' } })
    const option = await screen.findByRole('button', { name: /알림 보내기/ })
    fireEvent.click(option)

    await waitFor(() => {
      const vote = calls.find((c) => c.url.includes('/review/vote'))
      expect(vote).toBeTruthy()
      expect((vote!.body as { episode_id: string }).episode_id).toBe('EP_1')
    })
  })

  it('타이핑 없이 추천이 뜨고(발화와 겹치는 의도 1순위) [더 보기]로 계속 늘어난다', async () => {
    stub()
    const { container } = render(<GoldReviewPanel onClose={() => {}} onApplied={() => {}} />)
    fireEvent.change(screen.getByPlaceholderText(/예: 명배영/), { target: { value: '명배영' } })
    fireEvent.click(screen.getByRole('button', { name: '검수 시작' }))
    await screen.findByText(/"알림장 지금 보내줘"/)

    // 검색어 없이 추천 목록 — 발화와 예문이 겹치는 '알림 보내기'가 첫 옵션
    const first = await waitFor(() => {
      const opts = container.querySelectorAll('.gym-option:not(.gym-option-more)')
      expect(opts.length).toBe(6) // 첫 페이지
      return opts[0] as HTMLElement
    })
    expect(first.textContent).toContain('알림 보내기')
    expect(screen.getByText(/글자 유사도예요/)).toBeTruthy() // 정직 캡션(뇌 판단 아님)

    fireEvent.click(screen.getByRole('button', { name: /더 보기/ }))
    await waitFor(() => {
      expect(container.querySelectorAll('.gym-option:not(.gym-option-more)').length).toBe(12)
    })
  })

  it('내 몫이 끝나면 확정 섹션 — 결과 메시지(백엔드 그대로)와 kappa가 보인다', async () => {
    stub()
    const onApplied = vi.fn()
    render(<GoldReviewPanel onClose={() => {}} onApplied={onApplied} />)
    fireEvent.change(screen.getByPlaceholderText(/예: 명배영/), { target: { value: '명배영' } })
    fireEvent.click(screen.getByRole('button', { name: '검수 시작' }))
    // 1건 처리(폐기) → 큐 소진 → 확정 화면
    fireEvent.click(await screen.findByRole('button', { name: /못 쓰는 발화/ }))
    expect(await screen.findByText(/내 몫의 검수가 끝났어요/)).toBeTruthy()

    fireEvent.change(screen.getByPlaceholderText(/예: 원장님/), { target: { value: '원장' } })
    fireEvent.click(screen.getByRole('button', { name: /GOLD 확정/ }))
    expect(await screen.findByText(/확정 3건\(GOLD\)/)).toBeTruthy()
    expect(screen.getByText(/kappa 0.72/)).toBeTruthy()
    expect(onApplied).toHaveBeenCalled()
  })
})

describe('GoldReviewPanel — 상황 라벨은 씨드 어휘가 원천', () => {
  it('어휘 관리에서 등록한 새 화면(photo_editor)이 검수 화면에 한글로 보인다', async () => {
    const queue = {
      ...QUEUE,
      items: [{
        ...QUEUE.items[0],
        situation: { ...QUEUE.items[0].situation, surface_type: 'photo_editor' },
      }],
    }
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const u = String(url)
      if (u.endsWith('/v1/situation-seeds'))
        return {
          ok: true,
          json: async () => ({
            vocabulary: {
              surface_types: { photo_editor: '사진 편집 화면' },
              object_kinds: {}, actions: {},
            },
          }),
        } as Response
      if (u.includes('ontology_examples_draft.csv'))
        return { ok: true, text: async () => CORPUS_CSV } as Response
      if (u.includes('/review/queue')) return { ok: true, json: async () => queue } as Response
      if (u.includes('/review/status')) return { ok: true, json: async () => STATUS } as Response
      return { ok: false, status: 404, json: async () => ({}) } as Response
    }))
    render(<GoldReviewPanel onClose={() => {}} onApplied={() => {}} />)
    fireEvent.change(screen.getByPlaceholderText(/예: 명배영/), { target: { value: '명배영' } })
    fireEvent.click(screen.getByRole('button', { name: '검수 시작' }))
    await screen.findByText(/"알림장 지금 보내줘"/)

    expect(await screen.findByText(/보고 있던 화면: 사진 편집 화면/)).toBeTruthy()
  })
})

describe('GoldReviewPanel — 상황 표시 (A+B)', () => {
  it('상황 박스: 화면·선택·직전 행동이 한글로 보이고, 같은 문장 배지(k/N)가 뜬다', async () => {
    stub()
    render(<GoldReviewPanel onClose={() => {}} onApplied={() => {}} />)
    fireEvent.change(screen.getByPlaceholderText(/예: 명배영/), { target: { value: '명배영' } })
    fireEvent.click(screen.getByRole('button', { name: '검수 시작' }))
    await screen.findByText(/"알림장 지금 보내줘"/)

    expect(screen.getByText(/이 말이 나온 상황/)).toBeTruthy()
    expect(screen.getByText(/보고 있던 화면: 놀이 보드 화면/)).toBeTruthy()
    expect(screen.getByText(/선택 중: 사진 1개/)).toBeTruthy()
    expect(screen.getByText(/직전 행동: 카드를 옮김/)).toBeTruthy()
    expect(screen.getByText(/같은 문장 2\/3/)).toBeTruthy() // 건너뛰지 않고 상황별 판단 안내
  })
})
