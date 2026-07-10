/**
 * 2D region map fallback — WebGL 불가·저사양 기기 대응 (§7-5).
 *
 * 3중 인코딩(색+라벨+위치)은 2D에서도 유지 — 고정 좌표·산포 규칙은 brain2dLayout.ts
 * (테스트로 잠금). 노드 점은 소속 region 원 안 결정론 배치(같은 nodeId → 같은 자리).
 *
 * T5.4 Persona Overlay(§7-6): overlayPriors가 오면 노드 점 **밑에** 부가 링을 깐다.
 * 절대 규칙 3 — 기본 노드 점의 속성(fill/opacity/r)은 오버레이 ON에서도 불변이고,
 * 마크 계산은 personaOverlay.markFromPrior(3D 레이어와 동일 원천)만 쓴다.
 */
import { dot2d, DOT_R, DOT_R_SELECTED, POS_2D, REGION_R } from './brain2dLayout'
import type { PlacedNode } from './layout'
import { BOOST_COLOR, DAMP_COLOR, markFromPrior } from './personaOverlay'
import { REGION_BY_ID, type RegionId } from './regions'
import { useBrainStore } from './store'

interface Props {
  nodes: PlacedNode[]
  /** T5.4 — 선택 클러스터의 intent_id → prior. null/부재 = 오버레이 OFF */
  overlayPriors?: ReadonlyMap<string, number> | null
}

export function Brain2DFallback({ nodes, overlayPriors }: Props) {
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
      {/* T5.4 persona 마크 — 노드 점 밑의 부가 링. 중립/부재 prior는 마크 자체가 없다 */}
      {overlayPriors && (
        <g className="persona-marks" pointerEvents="none">
          {nodes.map((n) => {
            const mark = markFromPrior(overlayPriors.get(n.intentId))
            if (mark.strength === 0) return null
            const [x, y] = dot2d(n.nodeId, n.region)
            return (
              <circle
                key={`pm-${n.nodeId}`}
                className={`persona-mark ${mark.boost ? 'persona-mark-boost' : 'persona-mark-damp'}`}
                cx={x}
                cy={y}
                r={DOT_R + 0.012 + 0.02 * mark.strength}
                fill="none"
                stroke={mark.boost ? BOOST_COLOR : DAMP_COLOR}
                strokeOpacity={0.35 + 0.55 * mark.strength}
                strokeWidth={0.005 + 0.006 * mark.strength}
              />
            )
          })}
        </g>
      )}
      {nodes.map((n) => {
        const [x, y] = dot2d(n.nodeId, n.region)
        const sel = n.nodeId === selectedNodeId
        return (
          <circle
            key={n.nodeId}
            className="node-dot"
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
