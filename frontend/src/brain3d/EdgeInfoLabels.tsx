/**
 * 연결 사유 칩 — 노드 선택 시, 혼동 edge로 연결된 상대 노드 위에 "왜 연결됐는지"를 띄운다.
 *
 * 내용은 §5-6 실 필드만: 방향(선택 노드 기준 유출/유입) · 상태(가설/관측/확정) ·
 * 출처(SKEPTIC 가설/합의 불일치/훈련 교정/Arena 측정) · 혼동률(미측정이면 "측정 전").
 * 텍스트는 edges.ts edgeInfo(유일 인코더)가 만든다 — 여기선 배치만.
 * 상호작용 없음(pointer-events none) — 클릭은 노드가 받는다.
 */
import { Html } from '@react-three/drei'
import { useMemo } from 'react'

import { edgeInfo } from './edges'
import { labelOf } from '../panels/intentLabels'
import type { PlacedNode } from './layout'
import { useBrainStore } from './store'

const LIFT = 0.075 // 노드 위로 띄우는 높이

export function EdgeInfoLabels({ nodes }: { nodes: PlacedNode[] }) {
  const payload = useBrainStore((s) => s.confusionEdges)
  const selectedNodeId = useBrainStore((s) => s.selectedNodeId)

  const chips = useMemo(() => {
    if (!payload || !selectedNodeId) return []
    const selected = nodes.find((n) => n.nodeId === selectedNodeId)
    if (!selected) return []
    const byIntent = new Map(nodes.map((n) => [n.intentId, n]))
    const out: Array<{
      key: string
      position: readonly [number, number, number]
      title: string
      info: ReturnType<typeof edgeInfo>
    }> = []
    for (const e of payload.edges) {
      const outgoing = e.from_intent === selected.intentId
      if (!outgoing && e.to_intent !== selected.intentId) continue
      const otherIntent = outgoing ? e.to_intent : e.from_intent
      const other = byIntent.get(otherIntent)
      if (!other) continue // 미배치 intent — 허공 칩 금지
      out.push({
        key: e.edge_id,
        position: [
          other.position[0],
          other.position[1] + LIFT,
          other.position[2],
        ],
        title: labelOf(otherIntent),
        info: edgeInfo(e, selected.intentId),
      })
    }
    return out
  }, [payload, selectedNodeId, nodes])

  if (chips.length === 0) return null
  return (
    <>
      {chips.map((c) => (
        <Html
          key={c.key}
          position={c.position as [number, number, number]}
          center
          wrapperClass="edge-info-wrap"
          zIndexRange={[1, 0]}
        >
          <div className={`edge-info-chip${c.info.measured ? ' edge-info-measured' : ''}`}>
            <strong className="edge-info-title">{c.title}</strong>
            <span className="edge-info-line">{c.info.direction}</span>
            <span className="edge-info-line edge-info-reason">
              {c.info.reason} · {c.info.rate}
            </span>
          </div>
        </Html>
      ))}
    </>
  )
}
