/**
 * @vitest-environment jsdom
 *
 * 브레인 운영실 대시보드 AC — 정직성이 곧 AC다:
 * - run 0 → "채점 전" 카드(0점 위장 금지) · shadow 0 → "아직 없음"
 * - 기준선은 payload.config 원천 — 스텁 config를 바꾸면 표시도 바뀐다(하드코딩 회귀 방지)
 * - 액션은 기존 흐름(store 모달) 연결 · 즉석 문답은 live 게이트 · 재조회 실패는 데이터 유지
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { Dashboard } from '../api/dashboard'
import { useBrainStore } from '../brain3d/store'
import { DashboardView } from './DashboardView'
import { emptyStream, makeDashboard } from './fixtures'

function stubDashboard(payload: Dashboard) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (String(url).includes('/dashboard')) {
      return { ok: true, json: async () => payload } as Response
    }
    throw new Error(`unexpected fetch: ${url}`)
  }))
}

beforeEach(() => {
  useBrainStore.setState({
    viewMode: 'dashboard', webglOk: false, dataSource: 'live',
    ktibGlobal: null, brainStage: 0, brainStageName: 'Dormant', brainVersion: 'seed-v0',
    reloadNonce: 0, reviewOpen: false, liveQuizOpen: false, helpOpen: false,
    helpTab: 'service',
  })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('DashboardView — 정직한 빈 상태', () => {
  it('run 0: "채점 전" 카드가 뜨고 실력은 —%(0 아님), 다음 행동을 안내한다', async () => {
    stubDashboard(makeDashboard())
    render(<DashboardView />)
    expect(await screen.findByText(/아직 채점 전이에요/)).toBeTruthy()
    expect(screen.getAllByText('—%').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByRole('button', { name: /시험 문항 더 만들기/ })).toBeTruthy()
  })

  it('shadow 스트림 0: "아직 없음"을 지어내지 않고 그대로 말한다', async () => {
    stubDashboard(makeDashboard())
    render(<DashboardView />)
    expect(await screen.findByText(/아직 없음 — 킨더버스 연결\(Shadow\) 전이에요/)).toBeTruthy()
  })

  it('run 1개: 차트는 그리되 "귀속 측정 전" 안내 — 두 번째 채점부터 원인 분석', async () => {
    stubDashboard(makeDashboard({
      performance: {
        axis: { ktib_version: 'ktib-1', model_version: 'seed-v0' },
        runs: [{
          run_id: 'AR_1', created_at: '2026-07-14T00:00:00Z', accuracy: 0.55,
          item_count: 100, ece: 0.1, delta_pp: null, inflow_since_prev: null,
          region_regressions: [], critical_worse: [], critical: null,
        }],
        attribution_ready: false,
      },
    }))
    render(<DashboardView />)
    expect(await screen.findByText(/귀속 측정 전/)).toBeTruthy()
    expect(screen.getByText(/— 기준 없음/)).toBeTruthy() // 첫 run delta는 0이 아니라 '없음'
  })
})

describe('DashboardView — 기준선은 payload.config 원천 (하드코딩 회귀 방지)', () => {
  it('config 값을 바꾸면 표시 하한도 바뀐다', async () => {
    const payload = makeDashboard()
    payload.config = { ...payload.config, critical_surface_min_items: 42 }
    stubDashboard(payload)
    render(<DashboardView />)
    expect(await screen.findByText(/의도당 42문항/)).toBeTruthy()
    expect(screen.queryByText(/의도당 30문항/)).toBeNull()
  })
})

describe('DashboardView — 액션은 기존 흐름 연결', () => {
  it('검수함 행 클릭 → 검수 모달 열림(store) + 동결 고지 존재', async () => {
    stubDashboard(makeDashboard({
      review_inbox: [{
        batch_id: 'B_1', created_by: '김검수', status: 'AWAITING_SECOND',
        item_count: 3, agreement_kappa: null, ktib_version: null,
        created_at: '2026-07-14T00:00:00Z',
      }],
    }))
    render(<DashboardView />)
    fireEvent.click(await screen.findByText('김검수'))
    expect(useBrainStore.getState().reviewOpen).toBe(true)
    // 고지 문구는 <strong>동결</strong>로 텍스트 노드가 갈라진다 — 이어지는 노드로 확인
    expect(screen.getByText(/수정할 수 없어요/)).toBeTruthy()
    expect(screen.getByText('동결')).toBeTruthy()
  })

  it('즉석 문답 버튼은 live에서만 — 미연결(error)이면 비노출', async () => {
    stubDashboard(makeDashboard())
    useBrainStore.setState({ dataSource: 'error' })
    render(<DashboardView />)
    await screen.findByText(/아직 채점 전이에요/)
    expect(screen.queryByRole('button', { name: /즉석 문답/ })).toBeNull()
    cleanup()

    stubDashboard(makeDashboard())
    useBrainStore.setState({ dataSource: 'live' })
    render(<DashboardView />)
    expect(await screen.findByRole('button', { name: /즉석 문답/ })).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: /즉석 문답/ }))
    expect(useBrainStore.getState().liveQuizOpen).toBe(true)
  })
})

describe('DashboardView — 재조회 실패의 정직성', () => {
  it('이미 그린 실데이터는 일시 실패로 지우지 않는다', async () => {
    let fail = false
    const payload = makeDashboard({
      inflow: {
        foundry: { ...emptyStream(), total: 2200 },
        human_teaching: emptyStream(), exam: emptyStream(), shadow: emptyStream(),
      },
    })
    vi.stubGlobal('fetch', vi.fn(async () => {
      if (fail) throw new Error('blip')
      return { ok: true, json: async () => payload } as Response
    }))
    render(<DashboardView />)
    expect((await screen.findAllByText(/2,200/)).length).toBeGreaterThanOrEqual(1)

    fail = true
    useBrainStore.getState().bumpReload()
    await waitFor(() =>
      expect(vi.mocked(fetch).mock.results.length).toBeGreaterThanOrEqual(2),
    )
    // 기존 데이터 유지 — 미연결 카드로 뒤집히지 않는다
    expect(screen.getAllByText(/2,200/).length).toBeGreaterThanOrEqual(1)
    expect(screen.queryByText(/불러오지 못했어요/)).toBeNull()
  })
})
