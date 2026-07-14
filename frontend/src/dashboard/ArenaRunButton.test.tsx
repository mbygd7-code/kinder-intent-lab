/**
 * @vitest-environment jsdom
 *
 * 채점 실행 버튼 AC — 사전 판정(회색+안내)과 PIN 입력 잔류 금지.
 *
 * - 서버가 runnable:false를 주면: 버튼은 보이되 회색(dash-btn-blocked), 클릭 시
 *   PIN 팝오버 대신 blocked_reason 안내만 뜬다.
 * - runnable이면: 팝오버는 열릴 때마다 빈 입력. 취소/ESC로 닫고 다시 열어도
 *   이전에 입력한 비밀번호가 남지 않는다.
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ArenaRunButton } from './ArenaRunButton'

function stubStatus(over: Record<string, unknown> = {}) {
  vi.stubGlobal(
    'fetch',
    vi.fn(async () => ({
      ok: true,
      json: async () => ({
        running: false,
        started_at: null,
        error: null,
        last_run: null,
        runnable: true,
        blocked_reason: null,
        ...over,
      }),
    })),
  )
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('ArenaRunButton — 사전 판정', () => {
  it('실행 불가면 회색으로 서고, 클릭은 PIN 대신 안내 문구를 띄운다', async () => {
    stubStatus({ runnable: false, blocked_reason: 'LLM_PROVIDER가 mock이라 채점하지 않아요' })
    render(<ArenaRunButton />)
    const btn = await screen.findByRole('button', { name: /채점 실행/ })
    await waitFor(() => expect(btn.className).toContain('dash-btn-blocked'))
    expect(btn.getAttribute('aria-disabled')).toBe('true')

    fireEvent.click(btn)
    expect(screen.queryByLabelText('채점 비밀번호')).toBeNull() // PIN 팝오버 없음
    expect(screen.getByRole('status').textContent).toContain('mock이라 채점하지 않아요')
  })

  it('구 서버 응답(runnable 부재)은 기존처럼 활성', async () => {
    stubStatus({ runnable: undefined, blocked_reason: undefined })
    render(<ArenaRunButton />)
    const btn = await screen.findByRole('button', { name: /채점 실행/ })
    fireEvent.click(btn)
    expect(screen.getByLabelText('채점 비밀번호')).toBeTruthy()
  })
})

describe('ArenaRunButton — PIN 입력 잔류 금지', () => {
  it('취소로 닫고 다시 열면 입력창이 비어 있다', async () => {
    stubStatus()
    render(<ArenaRunButton />)
    const btn = await screen.findByRole('button', { name: /채점 실행/ })

    fireEvent.click(btn)
    const input = screen.getByLabelText('채점 비밀번호') as HTMLInputElement
    fireEvent.change(input, { target: { value: '2341' } })
    expect(input.value).toBe('2341')

    fireEvent.click(screen.getByRole('button', { name: '취소' }))
    expect(screen.queryByLabelText('채점 비밀번호')).toBeNull()

    fireEvent.click(btn) // 다시 열기 — 이전 비밀번호가 남아 있으면 안 된다
    const reopened = screen.getByLabelText('채점 비밀번호') as HTMLInputElement
    expect(reopened.value).toBe('')
  })

  it('ESC로 닫아도 다시 열면 비어 있다', async () => {
    stubStatus()
    render(<ArenaRunButton />)
    const btn = await screen.findByRole('button', { name: /채점 실행/ })

    fireEvent.click(btn)
    const input = screen.getByLabelText('채점 비밀번호') as HTMLInputElement
    fireEvent.change(input, { target: { value: '9999' } })
    fireEvent.keyDown(input, { key: 'Escape' })
    expect(screen.queryByLabelText('채점 비밀번호')).toBeNull()

    fireEvent.click(btn)
    expect((screen.getByLabelText('채점 비밀번호') as HTMLInputElement).value).toBe('')
  })
})

describe('ArenaRunButton — 사전 판정 자가 회복 (마운트 1회로 끝내지 않는다)', () => {
  const BLOCKED = {
    running: false, started_at: null, error: null, last_run: null,
    runnable: false, blocked_reason: 'LLM_PROVIDER가 mock이라 채점하지 않아요',
  }

  it('마운트 때 상태 조회가 실패해도, 클릭 시 재판정으로 회색+안내로 정정한다', async () => {
    let first = true
    vi.stubGlobal('fetch', vi.fn(async () => {
      if (first) { first = false; throw new Error('backend 재시작 중') } // 마운트 시점 실패
      return { ok: true, json: async () => BLOCKED }
    }))
    render(<ArenaRunButton />)
    const btn = await screen.findByRole('button', { name: /채점 실행/ })

    fireEvent.click(btn) // 판정을 놓친 상태 — 일단 열리지만 백그라운드 재판정이 정정한다
    await waitFor(() => expect(screen.queryByLabelText('채점 비밀번호')).toBeNull())
    expect(btn.className).toContain('dash-btn-blocked')
    expect(screen.getByRole('status').textContent).toContain('mock이라 채점하지 않아요')
  })

  it('PIN 제출이 409(실행 불가)면 팝오버를 닫고 버튼을 회색으로 전환한다', async () => {
    let runnableNow = true
    vi.stubGlobal('fetch', vi.fn(async (_url: string, init?: { method?: string }) => {
      if (init?.method === 'POST') {
        runnableNow = false // 서버 상태가 바뀐 상황 재현 — 이후 status가 blocked를 알린다
        return { ok: false, status: 409,
                 json: async () => ({ detail: BLOCKED.blocked_reason }) }
      }
      return { ok: true, json: async () => (runnableNow
        ? { ...BLOCKED, runnable: true, blocked_reason: null } : BLOCKED) }
    }))
    render(<ArenaRunButton />)
    const btn = await screen.findByRole('button', { name: /채점 실행/ })

    fireEvent.click(btn)
    const input = await screen.findByLabelText('채점 비밀번호')
    fireEvent.change(input, { target: { value: '2341' } })
    fireEvent.click(screen.getByRole('button', { name: '확인' }))

    await waitFor(() => expect(screen.queryByLabelText('채점 비밀번호')).toBeNull())
    expect(btn.className).toContain('dash-btn-blocked')
    expect(screen.getByRole('status').textContent).toContain('mock이라 채점하지 않아요')
  })
})
