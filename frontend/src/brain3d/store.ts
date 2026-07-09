/**
 * Observatory 뷰 상태 (zustand) — 선택 노드 + 3D/2D 뷰 전환.
 * 시각 인코딩 값(brightness 등)은 여기 두지 않는다 — 원천은 §7-5 표(encodings.ts, T3.5).
 */
import { create } from 'zustand'

export type ViewMode = '3d' | '2d'

interface BrainViewState {
  selectedNodeId: string | null
  viewMode: ViewMode
  select: (nodeId: string | null) => void
  setViewMode: (mode: ViewMode) => void
}

export const useBrainStore = create<BrainViewState>()((set) => ({
  selectedNodeId: null,
  viewMode: '3d',
  select: (nodeId) => set({ selectedNodeId: nodeId }),
  setViewMode: (mode) => set({ viewMode: mode }),
}))
