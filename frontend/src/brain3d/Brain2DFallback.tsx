/**
 * 2D region map fallback — WebGL 불가·저사양 기기 대응 (§7-5).
 *
 * 3중 인코딩(색+라벨+위치)은 2D에서도 유지 — 고정 좌표·산포 규칙은 brain2dLayout.ts
 * (테스트로 잠금). 노드 점은 소속 region 원 안 결정론 배치(같은 nodeId → 같은 자리).
 */
import { dot2d, DOT_R, DOT_R_SELECTED, POS_2D, REGION_R } from './brain2dLayout'
import type { PlacedNode } from './layout'
import { REGION_BY_ID, type RegionId } from './regions'
import { useBrainStore } from './store'

interface Props {
  nodes: PlacedNode[]
}

export function Brain2DFallback({ nodes }: Props) {
  const selectedNodeId = useBrainStore((s) => s.selectedNodeId)
  const select = useBrainStore((s) => s.select)
  return (
    <svg
      className="brain-2d"
      viewBox="-1.45 -1.25 2.9 2.65"
      role="img"
      aria-label="Brain region map (2D fallback)"
      onClick={() => select(null)}
    >
      {Object.entries(POS_2D).map(([id, [x, y]]) => {
        const region = REGION_BY_ID[id as RegionId]
        return (
          <g key={id}>
            <circle cx={x} cy={y} r={REGION_R} fill={region.color} fillOpacity={0.08}
              stroke={region.color} strokeOpacity={0.5} strokeWidth={0.008} />
            <text x={x} y={y + REGION_R + 0.09} textAnchor="middle" fill={region.color}
              fontSize={0.085} fontWeight={600}>
              {region.label}
            </text>
          </g>
        )
      })}
      {nodes.map((n) => {
        const [x, y] = dot2d(n.nodeId, n.region)
        const sel = n.nodeId === selectedNodeId
        return (
          <circle
            key={n.nodeId}
            cx={x}
            cy={y}
            r={sel ? DOT_R_SELECTED : DOT_R}
            fill={REGION_BY_ID[n.region].color}
            fillOpacity={sel ? 1 : 0.45}
            stroke={sel ? '#ffffff' : 'none'}
            strokeWidth={sel ? 0.006 : 0}
            style={{ cursor: 'pointer' }}
            onClick={(e) => {
              e.stopPropagation()
              select(n.nodeId)
            }}
          />
        )
      })}
    </svg>
  )
}
