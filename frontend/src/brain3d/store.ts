/**
 * Observatory 뷰 상태 (zustand) — 선택 노드 + 3D/2D 뷰 전환 + region 점수(API 적재).
 *
 * regionScores: region reliability(§7-2, Arena heldout 원천). Arena 미실행이면 null/부재 —
 * 라벨은 "—"를 보여준다. 시각 인코딩 계산(brightness 등)은 여기 두지 않는다(encodings.ts 소관).
 */
import { create } from 'zustand'

import type {
  GlobalConfusionEdges,
  GrowthStage,
  ObservatoryBrain,
  PersonaOverlay,
} from '../api/observatory'
import type { RegionId } from './regions'

export type ViewMode = '3d' | '2d'

/** 데이터 소스 상태: live=실 API, mock=명시적 데모(배지 표시), error=미연결 */
export type DataSource = 'loading' | 'live' | 'mock' | 'error'

/** T5.4 persona-overlay 적재 상태 — 뇌 화면(dataSource)과 독립(부가 채널은 실패해도 뇌는 그린다) */
export type PersonaOverlayStatus = 'loading' | 'ready' | 'error'

/** 혼동 edge 표시 모드(§5-6): focus = 확정 ∪ 측정 ∪ 선택 노드 인접, all = 전체 */
export type EdgeDisplayMode = 'focus' | 'all'

interface BrainViewState {
  selectedNodeId: string | null
  selectedRegionId: RegionId | null // §7-2 Zoom 1 — 선택된 region
  /** 호버 중인 region — 3D 스피어·라벨·좌 패널·2D 원이 공유(활성화 하이라이트) */
  hoveredRegionId: RegionId | null
  viewMode: ViewMode
  brain: ObservatoryBrain | null // 패널이 읽는 원본 응답(regions[]/nodes[])
  regionScores: Partial<Record<RegionId, number | null>>
  ktibGlobal: number | null // §7-1 중앙 수치 — 마지막 Arena run만 (null="—")
  brainVersion: string | null
  /** §7-6 성장 스테이지 — 전부 Arena 산출. null = API 도착 전("—") */
  brainStage: GrowthStage | null
  brainStageName: string | null
  dataSource: DataSource
  /** T5.4 Persona Overlay(§7-6·§4-2) 원본 응답 — prior는 §5-5 사전 배수, 측정 정확도 아님 */
  personaOverlay: PersonaOverlay | null
  personaOverlayStatus: PersonaOverlayStatus
  /** 오버레이 ON = 선택된 cluster_id(비null). 시각 인코딩 계산은 personaOverlay.ts 소관 */
  overlayClusterId: string | null
  /** 지금 추론에 개입 중인 노드(§7-5 Pulse) — infer/gym 이벤트가 채운다. 기본 비어 있음 */
  pulsingNodeIds: ReadonlySet<string>
  /** Gym 제출 완료 후 뇌 상태 refetch 트리거(§6-7 [6] 즉시 반영) — BrainScreen이 구독 */
  reloadNonce: number
  /** §5-6 전체 혼동 edge 응답 — 부가 채널(실패해도 뇌는 그린다). null = 도착 전 */
  confusionEdges: GlobalConfusionEdges | null
  confusionEdgesStatus: PersonaOverlayStatus
  edgeDisplayMode: EdgeDisplayMode
  select: (nodeId: string | null) => void
  selectRegion: (regionId: RegionId | null) => void
  setHoveredRegion: (regionId: RegionId | null) => void
  setViewMode: (mode: ViewMode) => void
  setBrain: (brain: ObservatoryBrain | null) => void
  setRegionScores: (scores: Partial<Record<RegionId, number | null>>) => void
  setBrainMeta: (meta: {
    ktibGlobal: number | null
    brainVersion: string | null
    brainStage: GrowthStage | null
    brainStageName: string | null
  }) => void
  setDataSource: (source: DataSource) => void
  setPersonaOverlay: (overlay: PersonaOverlay) => void
  setPersonaOverlayError: () => void
  setOverlayCluster: (clusterId: string | null) => void
  setPulsing: (ids: Iterable<string>) => void
  bumpReload: () => void
  setConfusionEdges: (edges: GlobalConfusionEdges) => void
  setConfusionEdgesError: () => void
  setEdgeDisplayMode: (mode: EdgeDisplayMode) => void
}

export const useBrainStore = create<BrainViewState>()((set) => ({
  selectedNodeId: null,
  selectedRegionId: null,
  hoveredRegionId: null,
  viewMode: '3d',
  brain: null,
  regionScores: {},
  ktibGlobal: null,
  brainVersion: null,
  brainStage: null,
  brainStageName: null,
  dataSource: 'loading',
  personaOverlay: null,
  personaOverlayStatus: 'loading',
  overlayClusterId: null,
  pulsingNodeIds: new Set<string>(),
  reloadNonce: 0,
  confusionEdges: null,
  confusionEdgesStatus: 'loading',
  edgeDisplayMode: 'focus',
  // 노드 선택 시 region 선택은 유지(좌·우 패널 독립). region 선택은 노드 선택을 지운다.
  select: (nodeId) => set({ selectedNodeId: nodeId }),
  selectRegion: (regionId) => set({ selectedRegionId: regionId, selectedNodeId: null }),
  setHoveredRegion: (hoveredRegionId) => set({ hoveredRegionId }),
  setViewMode: (mode) => set({ viewMode: mode }),
  setBrain: (brain) => set({ brain }),
  setRegionScores: (regionScores) => set({ regionScores }),
  setBrainMeta: ({ ktibGlobal, brainVersion, brainStage, brainStageName }) =>
    set({ ktibGlobal, brainVersion, brainStage, brainStageName }),
  setDataSource: (dataSource) => set({ dataSource }),
  // 재조회로 클러스터 구성이 바뀌면 사라진 클러스터 선택은 해제(유령 오버레이 방지)
  setPersonaOverlay: (overlay) =>
    set((s) => ({
      personaOverlay: overlay,
      personaOverlayStatus: 'ready',
      overlayClusterId: overlay.clusters.some((c) => c.cluster_id === s.overlayClusterId)
        ? s.overlayClusterId
        : null,
    })),
  // 재조회 일시 실패가 이미 적재된 실데이터를 지우지 않는다(BrainScreen의 live 유지와 동일 원칙)
  setPersonaOverlayError: () =>
    set((s) => (s.personaOverlayStatus === 'ready' ? {} : { personaOverlayStatus: 'error' })),
  setOverlayCluster: (overlayClusterId) => set({ overlayClusterId }),
  setPulsing: (ids) => set({ pulsingNodeIds: new Set(ids) }),
  // 훈련된 노드의 size/density/pending ring이 화면에 반영되게 재조회만 유도(§7-5 인코딩 불변)
  bumpReload: () => set((s) => ({ reloadNonce: s.reloadNonce + 1 })),
  setConfusionEdges: (confusionEdges) =>
    set({ confusionEdges, confusionEdgesStatus: 'ready' }),
  // persona 패턴: 재조회 일시 실패가 이미 적재된 실데이터를 지우지 않는다
  setConfusionEdgesError: () =>
    set((s) => (s.confusionEdgesStatus === 'ready' ? {} : { confusionEdgesStatus: 'error' })),
  setEdgeDisplayMode: (edgeDisplayMode) => set({ edgeDisplayMode }),
}))
