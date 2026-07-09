/**
 * @vitest-environment jsdom
 *
 * T3.7 Gym UI: 강화하기 → 모드 선택 → 세션(API 스텁) → 응답 → 제출 → evidence 적재 표시.
 * Phase 3 게이트의 프론트 절반(노드→패널→훈련→적재)을 fetch 스텁으로 고정.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import type { GymSessionStart } from '../api/gym'
import { GymOverlay } from './GymOverlay'

const SESSION: GymSessionStart = {
  session_id: 'GS_1',
  pack_id: 'CP_1',
  mode: 'correction_drill',
  items: [
    { item_id: 'GI_0', utterance: '이거 자연스럽게 해줘', candidate_intents: ['visual_naturalize', 'text_naturalize'], brain_guess: 'text_naturalize' },
  ],
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('GymOverlay — 바로잡기 연습', () => {
  it('예시 오답 선택은 교정이 아니라 다시 시도(recovery_turns++), 올바른 교정만 제출된다', async () => {
    const submitted: unknown[] = []
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init: RequestInit) => {
      submitted.push(JSON.parse(init.body as string))
      return { ok: true, json: async () => ({ session_id: 'GS_1', episodes_created: 1, evidence_created: 1, by_type: { HUMAN_CORRECTION: 1 } }) } as Response
    }))
    render(<GymOverlay session={SESSION} onClose={() => {}} />)

    // 예시 오답을 실측으로 오인하지 않게 "연습용 예시" 표기 (정직성)
    expect(screen.getByText('연습용 예시')).toBeTruthy()
    // intent는 한글 라벨로 표시됨 (text_naturalize → "글 자연스럽게 다듬기")
    // 예시 오답과 같은 걸 고르면 다시 시도(제출 아님)
    fireEvent.click(screen.getByRole('button', { name: '글 자연스럽게 다듬기' }))
    expect(screen.getByText(/다시 시도 1번/)).toBeTruthy()
    // 올바른 의도로 교정 → 마지막이라 제출 화면
    fireEvent.click(screen.getByRole('button', { name: '사진 자연스럽게 보정' }))
    fireEvent.click(screen.getByText('제출하기'))

    await waitFor(() => expect(screen.getByText('개의 학습 근거를 쌓았어요')).toBeTruthy())
    expect(screen.getByText('1')).toBeTruthy() // evidence_created
    // 제출 페이로드: 교정된 intent(id) + recovery_turns=2(오답1 + 정답1)
    const body = submitted[0] as { results: Array<{ chosen_intent: string; recovery_turns: number }> }
    expect(body.results[0].chosen_intent).toBe('visual_naturalize')
    expect(body.results[0].recovery_turns).toBe(2)
  })
})

describe('GymOverlay — Guess My Intent', () => {
  it('의도 선택 즉시 제출 대상, recovery_turns=0', async () => {
    const submitted: Array<{ results: Array<{ recovery_turns: number }> }> = []
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init: RequestInit) => {
      submitted.push(JSON.parse(init.body as string))
      return { ok: true, json: async () => ({ session_id: 'GS_1', episodes_created: 1, evidence_created: 1, by_type: { HUMAN_CONFIRMATION: 1 } }) } as Response
    }))
    const s: GymSessionStart = {
      ...SESSION, mode: 'guess_my_intent',
      // 미등록 id는 fallback으로 id 그대로 표시 → 버튼 이름으로 클릭 가능
      items: [{ item_id: 'GI_0', utterance: '발화', candidate_intents: ['a', 'b'], brain_guess: null }],
    }
    render(<GymOverlay session={s} onClose={() => {}} />)
    fireEvent.click(screen.getByRole('button', { name: 'a' }))
    fireEvent.click(screen.getByText('제출하기'))
    await waitFor(() => expect(screen.getByText('개의 학습 근거를 쌓았어요')).toBeTruthy())
    expect(submitted[0].results[0].recovery_turns).toBe(0)
  })

  it('닫기 버튼은 onClose 호출', () => {
    const onClose = vi.fn()
    render(<GymOverlay session={SESSION} onClose={onClose} />)
    fireEvent.click(within(screen.getByRole('dialog')).getByLabelText('닫기'))
    expect(onClose).toHaveBeenCalled()
  })
})
