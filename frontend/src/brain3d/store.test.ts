/**
 * T3.4 — Observatory 뷰 상태(zustand): 노드 선택 + 3D/2D fallback 전환.
 * brightness 등 시각 인코딩 값은 이 store에 두지 않는다 — 인코딩 원천은 §7-5 표(T3.5).
 * T5.4 — Persona Overlay 선택 상태(§7-6): 여기도 인코딩 계산은 없다(personaOverlay.ts 소관).
 */
import { beforeEach, describe, expect, it } from 'vitest'

import type { PersonaOverlay } from '../api/observatory'
import { useBrainStore } from './store'

beforeEach(() => {
  useBrainStore.setState({
    selectedNodeId: null,
    selectedRegionId: null,
    viewMode: '3d',
    personaOverlay: null,
    personaOverlayStatus: 'loading',
    overlayClusterId: null,
  })
})

const OVERLAY: PersonaOverlay = {
  state_version: 'PS_1',
  prior_cap: 0.15,
  clusters: [
    { cluster_id: 'C_warm', member_count: 5, state_version: 'PS_1', priors: { play_a: 0.8 } },
  ],
}

describe('useBrainStore', () => {
  it('초기 상태: 선택 없음, 3D 모드', () => {
    expect(useBrainStore.getState().selectedNodeId).toBeNull()
    expect(useBrainStore.getState().viewMode).toBe('3d')
  })

  it('노드 선택·해제', () => {
    useBrainStore.getState().select('play_intent_03')
    expect(useBrainStore.getState().selectedNodeId).toBe('play_intent_03')
    useBrainStore.getState().select(null)
    expect(useBrainStore.getState().selectedNodeId).toBeNull()
  })

  it('2D fallback 전환 (저사양·WebGL 불가 대응, §7-5)', () => {
    useBrainStore.getState().setViewMode('2d')
    expect(useBrainStore.getState().viewMode).toBe('2d')
    useBrainStore.getState().setViewMode('3d')
    expect(useBrainStore.getState().viewMode).toBe('3d')
  })

  it('region 선택은 노드 선택을 지운다 (§7-2 — 좌 패널 포커스 전환)', () => {
    // 3D region 라벨/좌 패널 row가 부르는 액션 — jsdom이 R3F Canvas를 못 띄우므로 여기서 고정
    useBrainStore.getState().select('N_x')
    useBrainStore.getState().selectRegion('PLAY')
    expect(useBrainStore.getState().selectedRegionId).toBe('PLAY')
    expect(useBrainStore.getState().selectedNodeId).toBeNull() // 우 노드 패널 닫힘
    useBrainStore.getState().selectRegion(null)
    expect(useBrainStore.getState().selectedRegionId).toBeNull()
  })

  it('T5.4: persona overlay 적재 → ready, 클러스터 선택/해제', () => {
    useBrainStore.getState().setPersonaOverlay(OVERLAY)
    expect(useBrainStore.getState().personaOverlayStatus).toBe('ready')
    useBrainStore.getState().setOverlayCluster('C_warm')
    expect(useBrainStore.getState().overlayClusterId).toBe('C_warm')
    useBrainStore.getState().setOverlayCluster(null) // 오버레이 OFF = 기본 §7-5 인코딩
    expect(useBrainStore.getState().overlayClusterId).toBeNull()
  })

  it('T5.4: 재조회로 사라진 클러스터 선택은 해제된다 (유령 오버레이 방지)', () => {
    useBrainStore.getState().setPersonaOverlay(OVERLAY)
    useBrainStore.getState().setOverlayCluster('C_warm')
    useBrainStore.getState().setPersonaOverlay({ ...OVERLAY, clusters: [] })
    expect(useBrainStore.getState().overlayClusterId).toBeNull()
  })

  it('T5.4: 적재 후 재조회 실패는 기존 실데이터를 지우지 않는다 (live 유지 원칙)', () => {
    useBrainStore.getState().setPersonaOverlayError()
    expect(useBrainStore.getState().personaOverlayStatus).toBe('error') // 최초 실패 = error
    useBrainStore.getState().setPersonaOverlay(OVERLAY)
    useBrainStore.getState().setPersonaOverlayError() // 이후 일시 실패
    expect(useBrainStore.getState().personaOverlayStatus).toBe('ready')
    expect(useBrainStore.getState().personaOverlay).toEqual(OVERLAY)
  })
})
