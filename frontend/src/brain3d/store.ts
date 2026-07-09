/**
 * Observatory 뷰 상태 (zustand) — 선택 노드 + 3D/2D 뷰 전환 + region 점수(API 적재).
 *
 * regionScores: region reliability(§7-2, Arena heldout 원천). Arena 미실행이면 null/부재 —
 * 라벨은 "—"를 보여준다. 시각 인코딩 계산(brightness 등)은 여기 두지 않는다(encodings.ts 소관).
 */
import { create } from 'zustand'

import type { ObservatoryBrain } from '../api/observatory'
import type { RegionId } from './regions'

export type ViewMode = '3d' | '2d'

/** 데이터 소스 상태: live=실 API, mock=명시적 데모(배지 표시), error=미연결 */
export type DataSource = 'loading' | 'live' | 'mock' | 'error'

interface BrainViewState {
  selectedNodeId: string | null
  selectedRegionId: RegionId | null // §7-2 Zoom 1 — 선택된 region
  viewMode: ViewMode
  brain: ObservatoryBrain | null // 패널이 읽는 원본 응답(regions[]/nodes[])
  regionScores: Partial<Record<RegionId, number | null>>
  ktibGlobal: number | null // §7-1 중앙 수치 — 마지막 Arena run만 (null="—")
  brainVersion: string | null
  dataSource: DataSource
  /** 지금 추론에 개입 중인 노드(§7-5 Pulse) — infer/gym 이벤트가 채운다. 기본 비어 있음 */
  pulsingNodeIds: ReadonlySet<string>
  select: (nodeId: string | null) => void
  selectRegion: (regionId: RegionId | null) => void
  setViewMode: (mode: ViewMode) => void
  setBrain: (brain: ObservatoryBrain | null) => void
  setRegionScores: (scores: Partial<Record<RegionId, number | null>>) => void
  setBrainMeta: (meta: { ktibGlobal: number | null; brainVersion: string | null }) => void
  setDataSource: (source: DataSource) => void
  setPulsing: (ids: Iterable<string>) => void
}

export const useBrainStore = create<BrainViewState>()((set) => ({
  selectedNodeId: null,
  selectedRegionId: null,
  viewMode: '3d',
  brain: null,
  regionScores: {},
  ktibGlobal: null,
  brainVersion: null,
  dataSource: 'loading',
  pulsingNodeIds: new Set<string>(),
  // 노드 선택 시 region 선택은 유지(좌·우 패널 독립). region 선택은 노드 선택을 지운다.
  select: (nodeId) => set({ selectedNodeId: nodeId }),
  selectRegion: (regionId) => set({ selectedRegionId: regionId, selectedNodeId: null }),
  setViewMode: (mode) => set({ viewMode: mode }),
  setBrain: (brain) => set({ brain }),
  setRegionScores: (regionScores) => set({ regionScores }),
  setBrainMeta: ({ ktibGlobal, brainVersion }) => set({ ktibGlobal, brainVersion }),
  setDataSource: (dataSource) => set({ dataSource }),
  setPulsing: (ids) => set({ pulsingNodeIds: new Set(ids) }),
}))
