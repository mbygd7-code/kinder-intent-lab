/**
 * Brain 뷰 진입점 — Observatory API에서 실 노드를 받아 §7-5 인코딩으로 렌더.
 *
 * 데이터 정직성: 실 데이터(live)만 무배지로 보여준다. 백엔드 미연결이면 에러 칩 +
 * 명시적 "데모 노드 보기" 버튼 — 데모(mock)는 MOCK 배지를 계속 띄운다(실데이터로 오인 방지).
 * WebGL 판정은 첫 렌더 전에 동기(useState initializer) — 미지원이면 2D 강제 + 토글 숨김.
 * BrainCanvas는 lazy import(three 분리 청크).
 */
import { lazy, Suspense, useEffect, useMemo, useState } from 'react'

import { fetchBrainState, type ObservatoryBrain } from '../api/observatory'
import { Brain2DFallback } from './Brain2DFallback'
import { visualFromNode, type NodeVisual } from './encodings'
import { layoutNodes, type NodeSeed, type PlacedNode } from './layout'
import { makeMockNodes } from './mockNodes'
import { REGION_BY_ID, type RegionId } from './regions'
import { useBrainStore } from './store'

const BrainCanvas = lazy(() =>
  import('./BrainCanvas').then((m) => ({ default: m.BrainCanvas })),
)

function webglAvailable(): boolean {
  try {
    const canvas = document.createElement('canvas')
    return Boolean(canvas.getContext('webgl2') ?? canvas.getContext('webgl'))
  } catch {
    return false
  }
}

interface BrainData {
  nodes: PlacedNode[]
  visuals: ReadonlyMap<string, NodeVisual>
}

function fromApi(brain: ObservatoryBrain): BrainData {
  const seeds: NodeSeed[] = brain.nodes.map((n) => ({
    nodeId: n.node_id,
    intentId: n.intent_id,
    region: n.region,
  }))
  const visuals = new Map(brain.nodes.map((n) => [n.node_id, visualFromNode(n)]))
  return { nodes: layoutNodes(seeds), visuals }
}

export function BrainScreen() {
  const [webglOk] = useState(webglAvailable) // 마운트 전 1회 동기 판정
  const [data, setData] = useState<BrainData>({ nodes: [], visuals: new Map() })
  const viewMode = useBrainStore((s) => s.viewMode)
  const setViewMode = useBrainStore((s) => s.setViewMode)
  const selectedNodeId = useBrainStore((s) => s.selectedNodeId)
  const dataSource = useBrainStore((s) => s.dataSource)
  const setDataSource = useBrainStore((s) => s.setDataSource)
  const setRegionScores = useBrainStore((s) => s.setRegionScores)
  const setBrainMeta = useBrainStore((s) => s.setBrainMeta)

  useEffect(() => {
    const ctrl = new AbortController()
    fetchBrainState(ctrl.signal)
      .then((brain) => {
        setData(fromApi(brain))
        setRegionScores(
          Object.fromEntries(brain.regions.map((r) => [r.region, r.reliability])),
        )
        setBrainMeta({ ktibGlobal: brain.ktib_global, brainVersion: brain.brain_version })
        setDataSource('live')
      })
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return
        console.warn('observatory API 미연결:', err)
        setDataSource('error')
      })
    return () => ctrl.abort()
  }, [setBrainMeta, setDataSource, setRegionScores])

  const loadMock = () => {
    // 명시적 데모 — MOCK 배지가 계속 표시된다 (실데이터 오인 방지)
    setData({ nodes: layoutNodes(makeMockNodes()), visuals: new Map() })
    setDataSource('mock')
  }

  const effectiveMode = webglOk ? viewMode : '2d'
  const selected = useMemo(
    () => data.nodes.find((n) => n.nodeId === selectedNodeId) ?? null,
    [data.nodes, selectedNodeId],
  )

  return (
    <div className="brain-screen">
      {effectiveMode === '3d' ? (
        <Suspense fallback={<p className="rotate-hint">3D 로딩…</p>}>
          <BrainCanvas nodes={data.nodes} visuals={data.visuals} />
        </Suspense>
      ) : (
        <Brain2DFallback nodes={data.nodes} />
      )}

      <div className="brain-hud">
        {webglOk && (
          <button
            type="button"
            className="view-toggle"
            onClick={() => setViewMode(effectiveMode === '3d' ? '2d' : '3d')}
          >
            {effectiveMode === '3d' ? '2D 지도로 보기' : '3D 뇌로 보기'}
          </button>
        )}
        {dataSource === 'mock' && <span className="badge badge-mock">MOCK</span>}
        {dataSource === 'error' && (
          <div className="error-chip">
            <span>백엔드 미연결 — 실 노드를 불러올 수 없습니다</span>
            <button type="button" className="view-toggle" onClick={loadMock}>
              데모 노드 보기
            </button>
          </div>
        )}
        {selected && (
          <div className="selected-chip" style={{ borderColor: REGION_BY_ID[selected.region as RegionId].color }}>
            <span className="region-dot" style={{ backgroundColor: REGION_BY_ID[selected.region as RegionId].color }} />
            <strong>{selected.intentId}</strong>
            <span className="selected-region">{REGION_BY_ID[selected.region as RegionId].label}</span>
          </div>
        )}
      </div>

      {effectiveMode === '3d' && <p className="rotate-hint">↻ Drag to rotate brain</p>}
    </div>
  )
}
