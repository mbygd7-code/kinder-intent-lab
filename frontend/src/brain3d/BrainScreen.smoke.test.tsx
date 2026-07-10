/**
 * @vitest-environment jsdom
 *
 * BrainScreen 스모크: jsdom엔 WebGL이 없다 → §7-5 자동 2D fallback 경로가 실제 렌더로
 * 검증된다. Observatory API는 fetch 스텁 — live 경로(실 노드 렌더)와 error→명시적 MOCK
 * 경로(배지 필수)를 모두 확인한다. AC2의 라벨·색 축이 "렌더된 DOM"에서 확인되는 테스트.
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ObservatoryBrain } from '../api/observatory'
import App from '../App'
import { BrainScreen } from './BrainScreen'
import { makeMockNodes } from './mockNodes'
import { REGIONS } from './regions'
import { useBrainStore } from './store'

const FAKE_BRAIN: ObservatoryBrain = {
  brain_version: 'seed-v0',
  ontology_version: 'onto-1.0',
  ktib_global: null,
  brain_stage: 0,
  brain_stage_name: 'Dormant',
  regions: REGIONS.map((r) => ({
    region: r.id, reliability: null, node_count: 15, gold_evidence: 2, synthetic_evidence: 40,
    stage: 0, stage_name: 'Dormant', measured_count: 0,
  })),
  nodes: makeMockNodes().map((s, i) => ({
    node_id: s.nodeId, intent_id: s.intentId, region: s.region,
    evidence_total: i, evidence_diversity: 0.3, gold_count: 1, exemplar_count: 1,
    heldout_accuracy: null, pending_evaluation: false,
  })),
}

function stubFetch(ok: boolean, brain: ObservatoryBrain = FAKE_BRAIN) {
  vi.stubGlobal('fetch', vi.fn(async () => {
    if (!ok) throw new Error('connection refused')
    return { ok: true, json: async () => brain } as Response
  }))
}

// Arena가 돈 뒤의 상태 시뮬레이션 — 숫자 흐름(포맷·store 적재) 검증용
const ARENA_BRAIN: ObservatoryBrain = {
  ...FAKE_BRAIN,
  brain_version: 'v0.21',
  ktib_global: 0.618,
  brain_stage: 3,
  brain_stage_name: 'Region Online',
  regions: FAKE_BRAIN.regions.map((r) =>
    r.region === 'PLAY'
      ? { ...r, reliability: 0.7, stage: 3, stage_name: 'Region Online', measured_count: 15 }
      : r,
  ),
}

beforeEach(() => {
  useBrainStore.setState({
    selectedNodeId: null, viewMode: '3d', regionScores: {}, ktibGlobal: null,
    brainVersion: null, dataSource: 'loading', pulsingNodeIds: new Set(),
  })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('BrainScreen (WebGL 없음 = jsdom, API 스텁)', () => {
  it('WebGL 미지원이면 store가 3d여도 2D map을 렌더하고, 3D 진입 토글을 숨긴다', async () => {
    stubFetch(true)
    render(<BrainScreen />)
    expect(screen.getByRole('img', { name: /2d fallback/i })).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull() // 빈 3D 뷰로 들어갈 길 자체가 없다
    await waitFor(() => expect(useBrainStore.getState().dataSource).toBe('live'))
  })

  it('AC2: 7개 region 라벨이 각자의 region 색으로 렌더된다 (색+라벨 축)', () => {
    stubFetch(true)
    const { container } = render(<BrainScreen />)
    const texts = [...container.querySelectorAll('svg text')]
    const rendered = new Map(texts.map((t) => [t.textContent, t.getAttribute('fill')]))
    for (const r of REGIONS) {
      expect(rendered.get(r.label)).toBe(r.color)
    }
  })

  it('live: 실 API 노드가 100+ 렌더되고 점 클릭 → 선택 칩 (MOCK 배지 없음)', async () => {
    stubFetch(true)
    const { container } = render(<BrainScreen />)
    await waitFor(() => {
      const dots = [...container.querySelectorAll('svg circle')].filter(
        (c) => Number(c.getAttribute('r')) < 0.1,
      )
      expect(dots.length).toBeGreaterThanOrEqual(100)
    })
    expect(container.querySelector('.badge-mock')).toBeNull()
    const dots = [...container.querySelectorAll('svg circle')].filter(
      (c) => Number(c.getAttribute('r')) < 0.1,
    )
    fireEvent.click(dots[0])
    const chip = container.querySelector('.selected-chip')
    expect(chip).toBeTruthy()
    expect(chip!.querySelector('strong')!.textContent).toMatch(/_intent_/)
  })

  it('Arena 데이터가 오면 KTIB %·region 점수·버전이 그대로 흐른다 (지어내지도 잃지도 않음)', async () => {
    stubFetch(true, ARENA_BRAIN)
    render(<App />)
    // App 헤더: ktib 0.618 → "61.8%" (— 아님), 버전 표기
    expect(await screen.findByText('61.8%')).toBeTruthy()
    expect(screen.getByText(/v0\.21/)).toBeTruthy()
    await waitFor(() => {
      const s = useBrainStore.getState()
      expect(s.ktibGlobal).toBe(0.618)
      expect(s.regionScores.PLAY).toBe(0.7) // 비null reliability 적재
      expect(s.regionScores.VISUAL).toBeNull() // 미측정 region은 여전히 null
    })
  })

  it('API 미연결: 에러 칩 → "데모 노드 보기" 클릭 시에만 mock + MOCK 배지 표시', async () => {
    stubFetch(false)
    const { container } = render(<BrainScreen />)
    const demoBtn = await screen.findByText('데모 노드 보기')
    // 에러 상태에선 노드 없음(지어내지 않음)
    expect(
      [...container.querySelectorAll('svg circle')].filter(
        (c) => Number(c.getAttribute('r')) < 0.1,
      ).length,
    ).toBe(0)
    fireEvent.click(demoBtn)
    await waitFor(() => {
      expect(container.querySelector('.badge-mock')).toBeTruthy() // 데모는 반드시 배지
    })
    const dots = [...container.querySelectorAll('svg circle')].filter(
      (c) => Number(c.getAttribute('r')) < 0.1,
    )
    expect(dots.length).toBeGreaterThanOrEqual(100)
  })

  it('T4.3: bumpReload → 실제로 refetch가 한 번 더 나간다 (§6-7 [6] 갱신 배선 고정)', async () => {
    // reloadNonce가 effect deps에서 빠지는 회귀(린트 정리 등)를 잡는 테스트 — 카운터가 아니라
    // fetch 호출 수를 직접 센다
    stubFetch(true)
    const fetchMock = vi.mocked(fetch)
    render(<BrainScreen />)
    await waitFor(() => expect(useBrainStore.getState().dataSource).toBe('live'))
    const callsAfterMount = fetchMock.mock.calls.length
    useBrainStore.getState().bumpReload()
    await waitFor(() => expect(fetchMock.mock.calls.length).toBe(callsAfterMount + 1))
  })

  it('T4.3: 라이브 표시 중 재조회 실패 → 에러 화면으로 뒤집히지 않고 라이브 유지 (정직성)', async () => {
    // 제출 직후 일시 장애가 '백엔드 미연결'+데모 버튼으로 뒤집히면, 실데이터 위에 mock 진입로가
    // 열린다 — 기존 라이브 상태를 유지해야 한다
    let fail = false
    vi.stubGlobal('fetch', vi.fn(async () => {
      if (fail) throw new Error('refetch blip')
      return { ok: true, json: async () => FAKE_BRAIN } as Response
    }))
    const { container } = render(<BrainScreen />)
    await waitFor(() => expect(useBrainStore.getState().dataSource).toBe('live'))
    fail = true
    useBrainStore.getState().bumpReload()
    // 실패 응답이 처리될 시간을 준 뒤에도 dataSource는 live, 에러 칩 없음
    await waitFor(() => {
      expect(vi.mocked(fetch).mock.results.length).toBeGreaterThanOrEqual(2)
    })
    expect(useBrainStore.getState().dataSource).toBe('live')
    expect(container.querySelector('.error-chip')).toBeNull()
  })
})
