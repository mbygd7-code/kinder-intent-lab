/**
 * @vitest-environment jsdom
 *
 * BrainScreen 스모크: jsdom엔 WebGL이 없다 → 대시보드 강제 경로(2D 지도 대체, 2026-07-14)가
 * 실제 렌더로 검증된다. Observatory API는 fetch 스텁.
 *
 * 2D SVG 전용이던 검증(region 라벨·노드 클릭·혼동 점선·호버·데모 노드)은 3D 캔버스 전용이
 * 되어 여기서 뺐다 — 독 팝오버(성향 렌즈·헷갈림 연결·범례)는 dockControls.test.tsx에서
 * 컴포넌트 단위로, 대시보드 자체 AC는 dashboard/dashboard.test.tsx에서 검증한다.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { GlobalConfusionEdges, ObservatoryBrain, PersonaOverlay } from '../api/observatory'
import App from '../App'
import { makeDashboard } from '../dashboard/fixtures'
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

const EMPTY_OVERLAY: PersonaOverlay = { state_version: null, prior_cap: 0.15, clusters: [] }
const FAKE_EDGES: GlobalConfusionEdges = { total: 2, measured_count: 0, edges: [] }
const FAKE_DASHBOARD = makeDashboard()

function stubFetch(ok: boolean, brain: ObservatoryBrain = FAKE_BRAIN) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (!ok) throw new Error('connection refused')
    if (String(url).includes('persona-overlay')) {
      return { ok: true, json: async () => EMPTY_OVERLAY } as Response
    }
    if (String(url).includes('confusion-edges')) {
      return { ok: true, json: async () => FAKE_EDGES } as Response
    }
    if (String(url).includes('/dashboard')) {
      return { ok: true, json: async () => FAKE_DASHBOARD } as Response
    }
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
    selectedNodeId: null, selectedRegionId: null, viewMode: '3d', webglOk: false,
    brain: null, regionScores: {}, ktibGlobal: null, brainVersion: null, brainStage: null,
    brainStageName: null, dataSource: 'loading', personaOverlay: null,
    personaOverlayStatus: 'loading', overlayClusterId: null, pulsingNodeIds: new Set(),
    reloadNonce: 0, confusionEdges: null, confusionEdgesStatus: 'loading',
    edgeDisplayMode: 'focus', hoveredRegionId: null,
    reviewOpen: false, liveQuizOpen: false, helpOpen: false, helpTab: 'service',
  })
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('BrainScreen (WebGL 없음 = jsdom → 대시보드 강제)', () => {
  it('WebGL 미지원이면 store가 3d여도 대시보드를 렌더하고, 3D 진입 버튼을 숨긴다', async () => {
    stubFetch(true)
    render(<BrainScreen />)
    expect(await screen.findByRole('region', { name: '브레인 운영실' })).toBeTruthy()
    // 빈 3D 뷰로 들어갈 길 자체가 없다 (대시보드 헤더의 3D 버튼은 webglOk일 때만)
    expect(screen.queryByRole('button', { name: /3D 뇌로 보기/ })).toBeNull()
    await waitFor(() => expect(useBrainStore.getState().dataSource).toBe('live'))
    expect(screen.queryByRole('button', { name: /3D 뇌로 보기/ })).toBeNull()
  })

  it('API 미연결(최초): 대시보드는 지어내지 않고 미연결 카드를 띄운다', async () => {
    stubFetch(false)
    render(<BrainScreen />)
    expect(await screen.findByText(/운영실 데이터를 불러오지 못했어요/)).toBeTruthy()
  })

  it('Arena 데이터가 오면 KTIB %·스테이지·버전이 그대로 흐른다 (지어내지도 잃지도 않음)', async () => {
    stubFetch(true, ARENA_BRAIN)
    render(<App />)
    // 톱바 + 대시보드 실력 카드가 같은 store 원천을 그린다 — 둘 다 61.8%
    expect((await screen.findAllByText('61.8%')).length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText(/v0\.21/)).toBeTruthy()
    expect(screen.getAllByText('3단계 · 영역이 깨어남').length).toBeGreaterThanOrEqual(1)
    await waitFor(() => {
      const s = useBrainStore.getState()
      expect(s.ktibGlobal).toBe(0.618)
      expect(s.brainStage).toBe(3)
      expect(s.regionScores.PLAY).toBe(0.7) // 비null reliability 적재
      expect(s.regionScores.VISUAL).toBeNull() // 미측정 region은 여전히 null
    })
  })

  it('T5.4(§7-6): 미측정 뇌는 실패가 아니라 Dormant — "—%"와 0단계가 그대로 표기', async () => {
    stubFetch(true) // FAKE_BRAIN: brain_stage 0 "Dormant", ktib null
    render(<App />)
    expect((await screen.findAllByText('0단계 · 잠자는 중')).length).toBeGreaterThanOrEqual(1)
    expect(screen.getAllByText('—%').length).toBeGreaterThanOrEqual(1) // null은 0이 아니라 "—"
  })

  it('도움말: 헤더 버튼 → 오버레이(탭 4개), 탭 전환·닫기 동작', async () => {
    stubFetch(true)
    render(<App />) // 도움말 버튼은 헤더(App)에 있다
    expect(screen.queryByRole('dialog', { name: '도움말' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /도움말/ }))
    const dialog = screen.getByRole('dialog', { name: '도움말' })
    expect(within(dialog).getByText(/말귀를 알아듣는 뇌/)).toBeTruthy()
    fireEvent.click(within(dialog).getByRole('button', { name: '사용설명서' }))
    expect(within(dialog).getByText(/강화하기 — 약한 점 집중 과외/)).toBeTruthy()
    fireEvent.click(within(dialog).getByRole('button', { name: '시험 문항 만들기' }))
    const csvTpl = within(dialog).getByRole('link', { name: /전체 양식 받기/ }) as HTMLAnchorElement
    expect(csvTpl.getAttribute('href')).toBe('/ktib_exam_template.csv')
    expect(within(dialog).getByRole('link', { name: /안내서 PDF/ })).toBeTruthy()
    expect(within(dialog).getByRole('button', { name: /작성한 양식 올리기/ })).toBeTruthy()
    expect(within(dialog).getByPlaceholderText(/김유아/)).toBeTruthy()
    fireEvent.click(within(dialog).getByRole('button', { name: '공부 문항 보기' }))
    const csv = within(dialog).getByRole('link', { name: /전체 내려받기/ }) as HTMLAnchorElement
    expect(csv.getAttribute('href')).toBe('/study_pool_snapshot.csv')
    fireEvent.click(within(dialog).getByRole('button', { name: '닫기' }))
    expect(screen.queryByRole('dialog', { name: '도움말' })).toBeNull()
  })

  it('T4.3: bumpReload → 실제로 refetch가 한 번 더 나간다 (§6-7 [6] 갱신 배선 고정)', async () => {
    stubFetch(true)
    const fetchMock = vi.mocked(fetch)
    const brainCalls = () =>
      fetchMock.mock.calls.filter(([url]) => String(url).includes('/v1/observatory/brain'))
        .length
    render(<BrainScreen />)
    await waitFor(() => expect(useBrainStore.getState().dataSource).toBe('live'))
    const callsAfterMount = brainCalls()
    useBrainStore.getState().bumpReload()
    await waitFor(() => expect(brainCalls()).toBe(callsAfterMount + 1))
  })

  it('T4.3: 라이브 표시 중 재조회 실패 → 에러 화면으로 뒤집히지 않고 라이브 유지 (정직성)', async () => {
    let fail = false
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (fail) throw new Error('refetch blip')
      if (String(url).includes('/dashboard')) {
        return { ok: true, json: async () => FAKE_DASHBOARD } as Response
      }
      return { ok: true, json: async () => FAKE_BRAIN } as Response
    }))
    const { container } = render(<BrainScreen />)
    await waitFor(() => expect(useBrainStore.getState().dataSource).toBe('live'))
    fail = true
    useBrainStore.getState().bumpReload()
    await waitFor(() => {
      expect(vi.mocked(fetch).mock.results.length).toBeGreaterThanOrEqual(2)
    })
    expect(useBrainStore.getState().dataSource).toBe('live')
    expect(container.querySelector('.error-chip')).toBeNull()
  })
})
