/**
 * @vitest-environment jsdom
 *
 * 뷰 독 팝오버 컨트롤(성향 렌즈·헷갈림 연결·범례) — 컴포넌트 단위 검증.
 * 대시보드 도입(2026-07-14)으로 독이 3D 전용이 되어 jsdom의 BrainScreen 스모크로는
 * 접근 불가 — 기존 AC(정직 카운트·비활성+안내·prior_cap 표기)를 여기서 그대로 보존한다.
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import type { GlobalConfusionEdges, PersonaOverlay } from '../api/observatory'
import { ConfusionEdgeControl } from './ConfusionEdgeControl'
import { LegendChip } from './LegendChip'
import { PersonaOverlayControl } from './PersonaOverlayControl'
import { useBrainStore } from './store'

const EDGES: GlobalConfusionEdges = {
  total: 2,
  measured_count: 0,
  edges: [
    { edge_id: 'CE_1', from_intent: 'a', to_intent: 'b',
      confusion_rate: null, state: 'hypothesized', origin: 'SKEPTIC' },
    { edge_id: 'CE_2', from_intent: 'c', to_intent: 'a',
      confusion_rate: null, state: 'hypothesized', origin: 'SKEPTIC' },
  ],
}

const CLUSTER_OVERLAY: PersonaOverlay = {
  state_version: 'PS_1',
  prior_cap: 0.15,
  clusters: [
    { cluster_id: 'C_warm', member_count: 6, state_version: 'PS_1', priors: { play_a: 0.9 } },
  ],
}

beforeEach(() => {
  useBrainStore.setState({
    personaOverlay: null, personaOverlayStatus: 'loading', overlayClusterId: null,
    confusionEdges: null, confusionEdgesStatus: 'loading', edgeDisplayMode: 'focus',
  })
})

afterEach(() => cleanup())

describe('ConfusionEdgeControl (§5-6 정직 카운트)', () => {
  it('가설 N · 측정 M 정직 표기 + 전체/핵심 토글', () => {
    useBrainStore.setState({ confusionEdges: EDGES, confusionEdgesStatus: 'ready' })
    render(<ConfusionEdgeControl />)
    expect(screen.getByText(/추측 2개 · 시험으로 확인 0개/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '전체 보기' }))
    expect(useBrainStore.getState().edgeDisplayMode).toBe('all')
    expect(screen.getByRole('button', { name: '핵심만 보기' })).toBeTruthy()
  })
})

describe('LegendChip (§7-5 인코딩 범례)', () => {
  it('크기=공부량 · 밝기=시험 정답률 행이 있다', () => {
    render(<LegendChip />)
    expect(screen.getByText('공부한 양 — 많이 배울수록 커져요')).toBeTruthy()
    expect(screen.getByText('시험 정답률 — 시험을 봐야만 밝아져요')).toBeTruthy()
  })
})

describe('PersonaOverlayControl (T5.4 — 부가 채널의 정직성)', () => {
  it('clusters 비면(Persona Discovery 미실행): 토글 비활성 + 정직한 안내', () => {
    useBrainStore.setState({
      personaOverlay: { state_version: null, prior_cap: 0.15, clusters: [] },
      personaOverlayStatus: 'ready',
    })
    render(<PersonaOverlayControl />)
    const toggle = screen.getByRole('button', { name: '렌즈 켜기' }) as HTMLButtonElement
    expect(toggle.disabled).toBe(true)
    expect(screen.getByText(/아직 성향 분석 전이에요/)).toBeTruthy()
    fireEvent.click(toggle)
    expect(useBrainStore.getState().overlayClusterId).toBeNull()
  })

  it('오버레이 API 실패: 미연결 안내 + 토글 비활성 (뇌 화면과 독립)', () => {
    useBrainStore.setState({ personaOverlayStatus: 'error' })
    render(<PersonaOverlayControl />)
    expect(screen.getByText(/성향 정보를 못 불러왔어요/)).toBeTruthy()
    expect(
      (screen.getByRole('button', { name: '렌즈 켜기' }) as HTMLButtonElement).disabled,
    ).toBe(true)
  })

  it('클러스터가 있으면 렌즈 ON → overlayClusterId 설정 + prior_cap·"정확도 아님" 표기', () => {
    useBrainStore.setState({ personaOverlay: CLUSTER_OVERLAY, personaOverlayStatus: 'ready' })
    render(<PersonaOverlayControl />)
    const toggle = screen.getByRole('button', { name: '렌즈 켜기' }) as HTMLButtonElement
    expect(toggle.disabled).toBe(false)
    fireEvent.click(toggle)
    expect(useBrainStore.getState().overlayClusterId).toBe('C_warm')
    expect(screen.getByText(/0\.15까지로 제한/)).toBeTruthy()
    expect(screen.getByText(/정확도\(밝기\)가 아니에요/)).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: '렌즈 끄기' }))
    expect(useBrainStore.getState().overlayClusterId).toBeNull()
  })
})
