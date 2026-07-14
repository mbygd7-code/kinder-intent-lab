/**
 * Brain 뷰 진입점 — Observatory API에서 실 노드를 받아 §7-5 인코딩으로 렌더.
 *
 * 데이터 정직성: 실 데이터(live)만 무배지로 보여준다. 백엔드 미연결이면 에러 칩 +
 * 명시적 "데모 노드 보기" 버튼 — 데모(mock)는 MOCK 배지를 계속 띄운다(실데이터로 오인 방지).
 * WebGL 판정은 store 초기값(webglOk, brain3d/webgl.ts) — 미지원이면 대시보드 강제.
 * BrainCanvas는 lazy import(three 분리 청크).
 *
 * 2026-07-14: "2D 지도" 뷰를 브레인 운영실 대시보드(DashboardView)로 완전 교체.
 * 대시보드도 여기(BrainScreen 안)서 렌더한다 — /brain fetch가 계속 돌아야
 * KtibReviewModal 등 store.brain 소비자가 의도 목록을 잃지 않는다.
 * 뷰 독·MOCK/에러 배지는 3D 전용(대시보드는 자체 헤더·연결 상태를 가진다).
 */
import { lazy, Suspense, useEffect, useMemo, useState } from 'react'

import {
  fetchBrainState,
  fetchConfusionEdges,
  fetchPersonaOverlay,
  type ObservatoryBrain,
} from '../api/observatory'
import { DashboardView } from '../dashboard/DashboardView'
import { ConfusionEdgeControl } from './ConfusionEdgeControl'
import { visualFromNode, type NodeVisual } from './encodings'
import { layoutNodes, type NodeSeed, type PlacedNode } from './layout'
import { LegendChip } from './LegendChip'
import { makeMockNodes } from './mockNodes'
import type { ParticleMetrics } from './particles'
import { PersonaOverlayControl } from './PersonaOverlayControl'
import { effectiveViewMode, useBrainStore } from './store'

const BrainCanvas = lazy(() =>
  import('./BrainCanvas').then((m) => ({ default: m.BrainCanvas })),
)

interface BrainData {
  nodes: PlacedNode[]
  visuals: ReadonlyMap<string, NodeVisual>
  /** evidence 파티클 원천(particles.ts) — 노드별 훈련 근거 지표 */
  metrics: ReadonlyMap<string, ParticleMetrics>
}

function fromApi(brain: ObservatoryBrain): BrainData {
  const seeds: NodeSeed[] = brain.nodes.map((n) => ({
    nodeId: n.node_id,
    intentId: n.intent_id,
    region: n.region,
  }))
  const visuals = new Map(brain.nodes.map((n) => [n.node_id, visualFromNode(n)]))
  const metrics = new Map<string, ParticleMetrics>(
    brain.nodes.map((n) => [
      n.node_id,
      {
        evidence_total: n.evidence_total,
        evidence_diversity: n.evidence_diversity,
        gold_count: n.gold_count,
        expert_count: n.evidence_buckets?.expert ?? 0,
      },
    ]),
  )
  return { nodes: layoutNodes(seeds), visuals, metrics }
}

/** 하단 뷰 독의 팝오버 종류 — 한 번에 하나만 연다 */
type DockKey = 'persona' | 'edges' | 'legend'

export function BrainScreen() {
  const webglOk = useBrainStore((s) => s.webglOk) // 마운트 전 1회 동기 판정(store 초기값)
  const [data, setData] = useState<BrainData>({
    nodes: [],
    visuals: new Map(),
    metrics: new Map(),
  })
  const viewMode = useBrainStore((s) => s.viewMode)
  const setViewMode = useBrainStore((s) => s.setViewMode)
  const dataSource = useBrainStore((s) => s.dataSource)
  const setDataSource = useBrainStore((s) => s.setDataSource)
  const setRegionScores = useBrainStore((s) => s.setRegionScores)
  const setBrainMeta = useBrainStore((s) => s.setBrainMeta)
  const setBrain = useBrainStore((s) => s.setBrain)
  const setPersonaOverlay = useBrainStore((s) => s.setPersonaOverlay)
  const setPersonaOverlayError = useBrainStore((s) => s.setPersonaOverlayError)
  const setConfusionEdges = useBrainStore((s) => s.setConfusionEdges)
  const setConfusionEdgesError = useBrainStore((s) => s.setConfusionEdgesError)
  const personaOverlay = useBrainStore((s) => s.personaOverlay)
  const overlayClusterId = useBrainStore((s) => s.overlayClusterId)
  const confusionEdges = useBrainStore((s) => s.confusionEdges) // 독 칩의 정직 카운트
  const reloadNonce = useBrainStore((s) => s.reloadNonce) // Gym 제출 후 bump → 재조회
  const [dockOpen, setDockOpen] = useState<DockKey | null>(null)

  // reloadNonce가 오르면 refetch — 노드 배치는 node_id 결정론(layoutNodes)이라 자리 유지,
  // 훈련된 노드의 size/density/pending ring만 갱신된다(§6-7 [6] 즉시 반영)
  useEffect(() => {
    const ctrl = new AbortController()
    fetchBrainState(ctrl.signal)
      .then((brain) => {
        setData(fromApi(brain))
        setBrain(brain) // 패널이 읽는 원본
        setRegionScores(
          Object.fromEntries(brain.regions.map((r) => [r.region, r.reliability])),
        )
        setBrainMeta({
          ktibGlobal: brain.ktib_global,
          brainVersion: brain.brain_version,
          brainStage: brain.brain_stage, // §7-6 — Arena 산출 그대로
          brainStageName: brain.brain_stage_name,
        })
        setDataSource('live')
      })
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return
        // 제출 후 재조회(bump)의 일시 실패는 '백엔드 미연결' 화면으로 뒤집지 않는다 —
        // 이미 라이브 데이터를 그리는 중이면 실데이터(다소 이전 상태)를 유지하는 게 정직하다
        if (useBrainStore.getState().dataSource === 'live') {
          console.warn('brain 재조회 실패 — 기존 라이브 상태 유지:', err)
          return
        }
        console.warn('observatory API 미연결:', err)
        setDataSource('error')
      })
    return () => ctrl.abort()
  }, [reloadNonce, setBrain, setBrainMeta, setDataSource, setRegionScores])

  // T5.4 persona-overlay(§7-6·§4-2) — 부가 채널이라 실패해도 dataSource(뇌 화면)는 안 건드린다
  useEffect(() => {
    const ctrl = new AbortController()
    fetchPersonaOverlay(ctrl.signal)
      .then((overlay) => {
        if (!Array.isArray(overlay?.clusters)) throw new Error('persona overlay 형식 아님')
        setPersonaOverlay(overlay)
      })
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return
        console.warn('persona overlay 미연결:', err)
        setPersonaOverlayError() // 이미 ready면 store가 기존 실데이터를 유지한다
      })
    return () => ctrl.abort()
  }, [reloadNonce, setPersonaOverlay, setPersonaOverlayError])

  // §5-6 혼동 edge(§7-5 Thickness/Flicker 원천) — 부가 채널: 실패해도 뇌 화면은 유지
  useEffect(() => {
    const ctrl = new AbortController()
    fetchConfusionEdges(ctrl.signal)
      .then((payload) => {
        if (!Array.isArray(payload?.edges)) throw new Error('confusion edges 형식 아님')
        setConfusionEdges(payload)
      })
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return
        console.warn('confusion edges 미연결:', err)
        setConfusionEdgesError() // 이미 ready면 store가 기존 실데이터를 유지한다
      })
    return () => ctrl.abort()
  }, [reloadNonce, setConfusionEdges, setConfusionEdgesError])

  // 선택된 클러스터의 intent_id → prior 맵 — OFF(null 선택)면 null → 기본 §7-5 인코딩 그대로
  const overlayPriors = useMemo<ReadonlyMap<string, number> | null>(() => {
    if (overlayClusterId == null || !personaOverlay) return null
    const cluster = personaOverlay.clusters.find((c) => c.cluster_id === overlayClusterId)
    return cluster ? new Map(Object.entries(cluster.priors)) : null
  }, [personaOverlay, overlayClusterId])

  const loadMock = () => {
    // 명시적 데모 — MOCK 배지가 계속 표시된다 (실데이터 오인 방지).
    // metrics는 비운다: 데모에 evidence 파티클을 지어내지 않는다.
    setData({ nodes: layoutNodes(makeMockNodes()), visuals: new Map(), metrics: new Map() })
    setDataSource('mock')
  }

  const effectiveMode = effectiveViewMode({ viewMode, webglOk })
  const lensOn = overlayClusterId != null
  const toggleDock = (key: DockKey) => setDockOpen((v) => (v === key ? null : key))

  // 대시보드 모드 — 전폭 페이지. /brain 등 fetch effect는 위에서 계속 돈다(store.brain 소비자 유지).
  if (effectiveMode === 'dashboard') {
    return (
      <div className="brain-screen">
        <DashboardView />
      </div>
    )
  }

  return (
    <div className="brain-screen">
      <Suspense fallback={<p className="rotate-hint">3D 로딩…</p>}>
        <BrainCanvas
          nodes={data.nodes}
          visuals={data.visuals}
          metrics={data.metrics}
          overlayPriors={overlayPriors}
        />
      </Suspense>

      {/* 데이터 출처 배지 — 상단 중앙: 정상(live)일 땐 아무것도 띄우지 않는다(정직성 표기만) */}
      {(dataSource === 'mock' || dataSource === 'error') && (
        <div className="brain-status">
          {dataSource === 'mock' && <span className="badge-mock">MOCK</span>}
          {dataSource === 'error' && (
            <div className="error-chip">
              <span>백엔드 미연결 — 실 노드를 불러올 수 없습니다</span>
              <button type="button" className="view-toggle" onClick={loadMock}>
                데모 노드 보기
              </button>
            </div>
          )}
        </div>
      )}

      {/* 뷰 독 — 하단 중앙: 보기 전환 + 렌즈·연결·범례 팝오버 (뇌를 "어떻게 볼지"의 단일 거점) */}
      {(dataSource === 'live' || dataSource === 'mock') && (
        <>
          {dockOpen != null && (
            <div className="view-popover">
              {dockOpen === 'persona' && <PersonaOverlayControl />}
              {/* §5-6 실 edge — 데모 노드와 실 edge는 짝이 안 맞으므로 live에서만 */}
              {dockOpen === 'edges' && dataSource === 'live' && <ConfusionEdgeControl />}
              {dockOpen === 'legend' && <LegendChip />}
            </div>
          )}
          <div className="view-dock">
            <button type="button" className="dock-chip" onClick={() => setViewMode('dashboard')}>
              📊 대시보드
            </button>
            <span className="dock-divider" aria-hidden />
            {/* T5.4 Persona Overlay(§7-6) — 렌즈가 켜져 있으면 칩에도 상태 표시 */}
            <button
              type="button"
              className={`dock-chip${dockOpen === 'persona' ? ' dock-chip-open' : ''}${lensOn ? ' dock-chip-on' : ''}`}
              aria-expanded={dockOpen === 'persona'}
              onClick={() => toggleDock('persona')}
            >
              성향 렌즈{lensOn ? ' · 켜짐' : ''}
            </button>
            {dataSource === 'live' && (
              <button
                type="button"
                className={`dock-chip${dockOpen === 'edges' ? ' dock-chip-open' : ''}`}
                aria-expanded={dockOpen === 'edges'}
                onClick={() => toggleDock('edges')}
              >
                헷갈림 연결{confusionEdges ? ` · ${confusionEdges.total}` : ''}
              </button>
            )}
            <button
              type="button"
              className={`dock-chip${dockOpen === 'legend' ? ' dock-chip-open' : ''}`}
              aria-expanded={dockOpen === 'legend'}
              onClick={() => toggleDock('legend')}
            >
              그림 읽는 법
            </button>
          </div>
        </>
      )}
    </div>
  )
}
