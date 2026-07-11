/**
 * @vitest-environment jsdom
 *
 * BrainScreen 스모크: jsdom엔 WebGL이 없다 → §7-5 자동 2D fallback 경로가 실제 렌더로
 * 검증된다. Observatory API는 fetch 스텁 — live 경로(실 노드 렌더)와 error→명시적 MOCK
 * 경로(배지 필수)를 모두 확인한다. AC2의 라벨·색 축이 "렌더된 DOM"에서 확인되는 테스트.
 *
 * T5.4: §7-6 성장 스테이지 HUD + Persona Overlay(부가 채널 — 절대 규칙 3: 기본 노드
 * 렌더링은 오버레이 ON에서도 불변)도 2D fallback DOM에서 검증한다.
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type {
  GlobalConfusionEdges,
  ObservatoryBrain,
  PersonaOverlay,
} from '../api/observatory'
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

// Persona Discovery 미실행 기본값 — clusters 빈 배열(토글 비활성 + 정직한 안내가 AC)
const EMPTY_OVERLAY: PersonaOverlay = { state_version: null, prior_cap: 0.15, clusters: [] }

// §5-6 SKEPTIC 가설 edge 2개 — 전부 미측정(rate null)이 오늘의 실 DB 상태와 같은 모양
const FAKE_EDGES: GlobalConfusionEdges = {
  total: 2,
  measured_count: 0,
  edges: [
    { edge_id: 'CE_1', from_intent: 'play_intent_01', to_intent: 'play_intent_02',
      confusion_rate: null, state: 'hypothesized', origin: 'SKEPTIC' },
    { edge_id: 'CE_2', from_intent: 'visual_intent_01', to_intent: 'play_intent_01',
      confusion_rate: null, state: 'hypothesized', origin: 'SKEPTIC' },
  ],
}

function stubFetch(
  ok: boolean,
  brain: ObservatoryBrain = FAKE_BRAIN,
  overlay: PersonaOverlay = EMPTY_OVERLAY,
  edges: GlobalConfusionEdges = FAKE_EDGES,
) {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (!ok) throw new Error('connection refused')
    if (String(url).includes('persona-overlay')) {
      return { ok: true, json: async () => overlay } as Response
    }
    if (String(url).includes('confusion-edges')) {
      return { ok: true, json: async () => edges } as Response
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
    selectedNodeId: null, selectedRegionId: null, viewMode: '3d', brain: null,
    regionScores: {}, ktibGlobal: null, brainVersion: null, brainStage: null,
    brainStageName: null, dataSource: 'loading', personaOverlay: null,
    personaOverlayStatus: 'loading', overlayClusterId: null, pulsingNodeIds: new Set(),
    confusionEdges: null, confusionEdgesStatus: 'loading', edgeDisplayMode: 'focus',
    hoveredRegionId: null,
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
    // 빈 3D 뷰로 들어갈 길 자체가 없다 (HUD의 범례·edge 칩 버튼과는 무관)
    expect(screen.queryByRole('button', { name: /뇌로 보기|지도로 보기/ })).toBeNull()
    await waitFor(() => expect(useBrainStore.getState().dataSource).toBe('live'))
    expect(screen.queryByRole('button', { name: /뇌로 보기|지도로 보기/ })).toBeNull()
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

  it('live: 실 API 노드가 100+ 렌더되고 점 클릭 → 노드 선택 (MOCK 배지 없음)', async () => {
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
    // 선택은 이제 store로만 반영된다(노드 이름 표시는 우측 NodePanel 담당 — 중복 칩 제거)
    expect(useBrainStore.getState().selectedNodeId).toBeNull()
    fireEvent.click(dots[0])
    expect(useBrainStore.getState().selectedNodeId).toBeTruthy()
  })

  it('Arena 데이터가 오면 KTIB %·region 점수·버전이 그대로 흐른다 (지어내지도 잃지도 않음)', async () => {
    stubFetch(true, ARENA_BRAIN)
    render(<App />)
    // App 헤더: ktib 0.618 → "61.8%" (— 아님), 버전 표기
    expect(await screen.findByText('61.8%')).toBeTruthy()
    expect(screen.getByText(/v0\.21/)).toBeTruthy()
    // T5.4(§7-6): 뇌 전체 성장 스테이지가 KTIB 수치 곁에 그대로 뜬다
    expect(screen.getByText('Stage 3 · Region Online')).toBeTruthy()
    await waitFor(() => {
      const s = useBrainStore.getState()
      expect(s.ktibGlobal).toBe(0.618)
      expect(s.brainStage).toBe(3)
      expect(s.regionScores.PLAY).toBe(0.7) // 비null reliability 적재
      expect(s.regionScores.VISUAL).toBeNull() // 미측정 region은 여전히 null
    })
  })

  it('T5.4(§7-6): 미측정 뇌는 실패가 아니라 Dormant — 스테이지 칩 + KTIB "—%" + region 스테이지', async () => {
    stubFetch(true) // FAKE_BRAIN: brain_stage 0 "Dormant", ktib null, 전 region Dormant
    render(<App />)
    expect(await screen.findByText('Stage 0 · Dormant')).toBeTruthy()
    expect(screen.getByText('—%')).toBeTruthy() // null ktib는 0이 아니라 "—"
    // 좌 패널: region 목록 7개 전부 stage_name 표기 (+ 전체 배지 1)
    await waitFor(() => {
      expect(screen.getAllByText('Dormant').length).toBeGreaterThanOrEqual(7)
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

  it('§5-6 HUD: 혼동 edge 칩이 정직 카운트(가설 N · 측정 M)를 표시한다', async () => {
    stubFetch(true)
    render(<BrainScreen />)
    await waitFor(() => expect(useBrainStore.getState().confusionEdgesStatus).toBe('ready'))
    expect(screen.getByText(/가설 2 · 측정 0/)).toBeTruthy()
    // 토글: 기본 focus → '전체 보기' 클릭 시 all
    fireEvent.click(screen.getByRole('button', { name: '전체 보기' }))
    expect(useBrainStore.getState().edgeDisplayMode).toBe('all')
    expect(screen.getByRole('button', { name: '핵심만 보기' })).toBeTruthy()
  })

  it('범례: Arena 측정 전(live·ktib null)이면 "어두운 것이 정상" 상태줄 + 인코딩 행', async () => {
    stubFetch(true) // FAKE_BRAIN: ktib null
    render(<BrainScreen />)
    await waitFor(() => expect(useBrainStore.getState().dataSource).toBe('live'))
    expect(screen.getByText(/Arena 측정 전 — 뇌가 어두운 것이 정상이에요/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '펼치기' }))
    expect(screen.getByText('훈련량 (evidence 총량)')).toBeTruthy()
    expect(screen.getByText('정확도 — Arena 측정만')).toBeTruthy()
  })

  it('2D: 노드 선택 시 그 노드의 혼동 edge가 점선(미측정)으로 그려진다 (§5-6 parity)', async () => {
    stubFetch(true)
    const { container } = render(<BrainScreen />)
    await waitFor(() => expect(useBrainStore.getState().confusionEdgesStatus).toBe('ready'))
    expect(container.querySelectorAll('.confusion-2d-edge').length).toBe(0) // 미선택 = 없음
    // play_intent_01 노드 선택 → CE_1(출발) + CE_2(도착) 2개가 보인다
    useBrainStore.setState({ selectedNodeId: 'BN_play_intent_01' })
    await waitFor(() =>
      expect(container.querySelectorAll('.confusion-2d-edge').length).toBe(2),
    )
    // 전부 미측정(rate null) → 점선 표기
    for (const line of container.querySelectorAll('.confusion-2d-edge')) {
      expect(line.getAttribute('stroke-dasharray')).toBeTruthy()
    }
  })

  it('region 호버(2D): 원에 마우스 오버 → store 공유 + 시각 강조, 아웃 → 해제', async () => {
    stubFetch(true)
    const { container } = render(<BrainScreen />)
    await waitFor(() => expect(useBrainStore.getState().dataSource).toBe('live'))
    // region 원 = 큰 반지름 원(노드 점 r<0.1과 구분)
    const regionCircle = [...container.querySelectorAll('svg circle')].find(
      (c) => Number(c.getAttribute('r')) > 0.2,
    )!
    expect(regionCircle.getAttribute('fill-opacity')).toBe('0.08')
    fireEvent.mouseOver(regionCircle)
    expect(useBrainStore.getState().hoveredRegionId).not.toBeNull()
    await waitFor(() => expect(regionCircle.getAttribute('fill-opacity')).toBe('0.18'))
    fireEvent.mouseOut(regionCircle)
    await waitFor(() => expect(useBrainStore.getState().hoveredRegionId).toBeNull())
  })

  it('도움말: 헤더 버튼 → 오버레이(탭 4개), 탭 전환·닫기 동작', async () => {
    stubFetch(true)
    render(<App />) // 도움말 버튼은 헤더(App)에 있다
    expect(screen.queryByRole('dialog', { name: '도움말' })).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /도움말/ }))
    const dialog = screen.getByRole('dialog', { name: '도움말' })
    // 기본 탭 = 서비스 설명서 (핵심 개념 문구)
    expect(within(dialog).getByText(/말귀를 알아듣는 뇌/)).toBeTruthy()
    // 사용설명서 탭 전환 — 강화하기 안내가 보인다
    fireEvent.click(within(dialog).getByRole('button', { name: '사용설명서' }))
    expect(within(dialog).getByText(/뇌 가르치기 — 강화하기/)).toBeTruthy()
    // 시험 문항 만들기 탭 — 다운로드 링크 2개(YAML·PDF)
    fireEvent.click(within(dialog).getByRole('button', { name: '시험 문항 만들기' }))
    const csvSeed = within(dialog).getByRole('link', { name: /시작 양식 \(CSV/ }) as HTMLAnchorElement
    expect(csvSeed.getAttribute('href')).toBe('/ktib_seed_template.csv')
    const yaml = within(dialog).getByRole('link', { name: /시작 양식 \(YAML/ }) as HTMLAnchorElement
    expect(yaml.getAttribute('href')).toBe('/ktib_seed_template.yaml')
    expect(within(dialog).getByRole('link', { name: /안내서 PDF/ })).toBeTruthy()
    // 시험지 업로드 버튼 + 작성자/승인자 입력 (플로우는 브라우저에서 검증)
    expect(within(dialog).getByRole('button', { name: /시험지 파일 선택/ })).toBeTruthy()
    expect(within(dialog).getByPlaceholderText(/CSV 업로드 시 필요/)).toBeTruthy()
    // 공부 문항 보기 탭 — CSV 다운로드 + 의도별 실시간 개수(FAKE_BRAIN 노드에서)
    fireEvent.click(within(dialog).getByRole('button', { name: '공부 문항 보기' }))
    const csv = within(dialog).getByRole('link', { name: /전체 내려받기/ }) as HTMLAnchorElement
    expect(csv.getAttribute('href')).toBe('/study_pool_snapshot.csv')
    expect(within(dialog).getByText(/공부"를 하면/)).toBeTruthy() // 자동 증가 설명
    expect(within(dialog).getByText(/시험\(Arena\)/)).toBeTruthy()
    fireEvent.click(within(dialog).getByRole('button', { name: '닫기' }))
    expect(screen.queryByRole('dialog', { name: '도움말' })).toBeNull()
  })

  it('T4.3: bumpReload → 실제로 refetch가 한 번 더 나간다 (§6-7 [6] 갱신 배선 고정)', async () => {
    // reloadNonce가 effect deps에서 빠지는 회귀(린트 정리 등)를 잡는 테스트 — 카운터가 아니라
    // fetch 호출 수를 직접 센다 (T5.4부터 persona-overlay도 fetch하므로 brain URL만 센다)
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

describe('T5.4 Persona Overlay (§7-6·§4-2 — 부가 채널, 절대 규칙 3)', () => {
  // FAKE_BRAIN의 실 mock intent에 붙는 클러스터: 01=강조(0.9), 02=중립(0.5), 03=억제(0.1),
  // 나머지 intent들은 prior 부재 → 전부 중립(마크 없음 — 어둡게 그리면 값 날조다)
  const CLUSTER_OVERLAY: PersonaOverlay = {
    state_version: 'PS_1',
    prior_cap: 0.15,
    clusters: [
      {
        cluster_id: 'C_warm',
        member_count: 6,
        state_version: 'PS_1',
        priors: { play_intent_01: 0.9, play_intent_02: 0.5, play_intent_03: 0.1 },
      },
    ],
  }

  const dotSnapshot = (container: HTMLElement) =>
    [...container.querySelectorAll('circle.node-dot')].map((c) =>
      ['cx', 'cy', 'r', 'fill', 'fill-opacity', 'stroke'].map((a) => c.getAttribute(a)).join('|'),
    )

  it('오버레이 ON: 마크는 비중립 prior에만 추가되고, 기본 노드 점은 1속성도 안 변한다', async () => {
    stubFetch(true, FAKE_BRAIN, CLUSTER_OVERLAY)
    const { container } = render(<BrainScreen />)
    await waitFor(() => expect(useBrainStore.getState().dataSource).toBe('live'))
    const toggle = await screen.findByRole('button', { name: '오버레이 켜기' })
    expect((toggle as HTMLButtonElement).disabled).toBe(false)

    const before = dotSnapshot(container)
    expect(before.length).toBeGreaterThanOrEqual(100)
    expect(container.querySelectorAll('.persona-mark').length).toBe(0) // OFF = 마크 없음

    fireEvent.click(toggle)
    // 01(0.9)→boost, 03(0.1)→damp — 02(중립 0.5)와 prior 부재 노드는 마크가 없다(중립≠어두움)
    await waitFor(() => expect(container.querySelectorAll('.persona-mark').length).toBe(2))
    expect(container.querySelectorAll('.persona-mark-boost').length).toBe(1)
    expect(container.querySelectorAll('.persona-mark-damp').length).toBe(1)
    // 절대 규칙 3: 오버레이는 부가 채널 — §7-5 기본 인코딩(밝기 포함)을 싣는 기본 점은 불변
    expect(dotSnapshot(container)).toEqual(before)
    // 범례: prior_cap 명시(강조가 무한한 영향으로 읽히지 않게) + 사전 배수임을 표기
    expect(screen.getByText(/prior_cap\s*0\.15/)).toBeTruthy()
    expect(screen.getByText(/측정 정확도가 아니며/)).toBeTruthy()

    // OFF로 되돌리면 마크만 사라지고 기본 점은 그대로
    fireEvent.click(screen.getByRole('button', { name: '오버레이 끄기' }))
    await waitFor(() => expect(container.querySelectorAll('.persona-mark').length).toBe(0))
    expect(dotSnapshot(container)).toEqual(before)
  })

  it('clusters 비면(Persona Discovery 미실행): 토글은 보이되 비활성 + 정직한 안내 문구', async () => {
    stubFetch(true) // 기본 EMPTY_OVERLAY
    render(<BrainScreen />)
    await waitFor(() => expect(useBrainStore.getState().dataSource).toBe('live'))
    const toggle = await screen.findByRole('button', { name: '오버레이 켜기' })
    expect((toggle as HTMLButtonElement).disabled).toBe(true) // 숨기지 않고 비활성
    expect(screen.getByText(/Persona Discovery 미실행/)).toBeTruthy()
    fireEvent.click(toggle) // 비활성 — 오버레이가 켜질 길이 없다
    expect(useBrainStore.getState().overlayClusterId).toBeNull()
  })

  it('persona-overlay API만 실패해도 뇌 화면(live)은 유지 — 오버레이는 미연결 안내', async () => {
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      if (String(url).includes('persona-overlay')) throw new Error('overlay down')
      return { ok: true, json: async () => FAKE_BRAIN } as Response
    }))
    render(<BrainScreen />)
    await waitFor(() => expect(useBrainStore.getState().dataSource).toBe('live'))
    await waitFor(() =>
      expect(useBrainStore.getState().personaOverlayStatus).toBe('error'),
    )
    expect(screen.getByText(/성향 오버레이 미연결/)).toBeTruthy()
    expect(
      (screen.getByRole('button', { name: '오버레이 켜기' }) as HTMLButtonElement).disabled,
    ).toBe(true)
  })
})
