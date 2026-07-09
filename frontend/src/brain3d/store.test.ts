/**
 * T3.4 — Observatory 뷰 상태(zustand): 노드 선택 + 3D/2D fallback 전환.
 * brightness 등 시각 인코딩 값은 이 store에 두지 않는다 — 인코딩 원천은 §7-5 표(T3.5).
 */
import { beforeEach, describe, expect, it } from 'vitest'

import { useBrainStore } from './store'

beforeEach(() => {
  useBrainStore.setState({ selectedNodeId: null, selectedRegionId: null, viewMode: '3d' })
})

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
})
