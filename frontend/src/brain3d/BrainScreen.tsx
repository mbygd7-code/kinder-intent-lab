/**
 * Brain 뷰 진입점 — WebGL 가용성 판단 → 3D 캔버스 또는 2D region map (§7-5 fallback).
 *
 * WebGL 판정은 첫 렌더 전에 동기로 한다(useState initializer): 미지원 기기에서 R3F Canvas를
 * 마운트하면 렌더러 생성이 비동기로 실패해 빈 화면 + unhandled rejection이 남기 때문.
 * 미지원이면 토글도 숨겨 "빈 3D 뷰"로 들어갈 길 자체를 없앤다.
 * BrainCanvas는 lazy import — three(번들 대부분)를 3D 경로에서만 내려받는다(2D 사용자 절약).
 * 노드 데이터: Observatory API 전까지 mock(~105 노드).
 */
import { lazy, Suspense, useMemo, useState } from 'react'

import { Brain2DFallback } from './Brain2DFallback'
import { layoutNodes } from './layout'
import { makeMockNodes } from './mockNodes'
import { REGION_BY_ID } from './regions'
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

export function BrainScreen() {
  const nodes = useMemo(() => layoutNodes(makeMockNodes()), [])
  const [webglOk] = useState(webglAvailable) // 마운트 전 1회 동기 판정 — 재검사 불필요
  const viewMode = useBrainStore((s) => s.viewMode)
  const setViewMode = useBrainStore((s) => s.setViewMode)
  const selectedNodeId = useBrainStore((s) => s.selectedNodeId)

  // WebGL 미지원이면 store 값과 무관하게 항상 2D — 빈 3D 뷰 진입 자체가 불가능
  const effectiveMode = webglOk ? viewMode : '2d'
  const selected = nodes.find((n) => n.nodeId === selectedNodeId) ?? null

  return (
    <div className="brain-screen">
      {effectiveMode === '3d' ? (
        <Suspense fallback={<p className="rotate-hint">3D 로딩…</p>}>
          <BrainCanvas nodes={nodes} />
        </Suspense>
      ) : (
        <Brain2DFallback nodes={nodes} />
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
        {selected && (
          <div className="selected-chip" style={{ borderColor: REGION_BY_ID[selected.region].color }}>
            <span className="region-dot" style={{ backgroundColor: REGION_BY_ID[selected.region].color }} />
            <strong>{selected.intentId}</strong>
            <span className="selected-region">{REGION_BY_ID[selected.region].label}</span>
          </div>
        )}
      </div>

      {effectiveMode === '3d' && <p className="rotate-hint">↻ Drag to rotate brain</p>}
    </div>
  )
}
