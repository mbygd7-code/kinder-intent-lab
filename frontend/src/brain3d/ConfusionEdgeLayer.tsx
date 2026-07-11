/**
 * 혼동 edge 렌더러 — edges.ts(유일 인코더)가 정한 시각만 그린다 (§7-5·§5-6).
 *
 * 미측정(점선 slate): state·선택여부 버킷별 배치 draw(LineSegments2) — 오늘 147개 전부 여기.
 * 측정(실선 amber): edge별 개별 draw — flicker(불투명 진동, Hz ∝ rate)는 재질 단위라
 * 개별이어야 한다. 측정 edge는 희소(중요)해서 개별 draw 비용이 정당하다. 오늘은 0개.
 *
 * 전파 효과(선택 시): 선택 노드에 닿은 edge는 ① 점선이 edge 의미 방향(from→to)으로
 * 흐르고(dashOffset 애니) ② 펄스 입자가 같은 방향으로 곡선을 따라 이동한다 — 신호가
 * 전파되는 느낌. 방향은 장식이 아니라 §5-6 혼동 방향 그대로다(유출=밖으로, 유입=안으로).
 * 상호작용 없음(raycast는 Line2 기본 무시 — 클릭은 노드만). 데이터 없으면 아무것도 안 그린다.
 */
import { Line } from '@react-three/drei'
import { useFrame } from '@react-three/fiber'
import { useMemo, useRef } from 'react'
import * as THREE from 'three'
import type { Line2 } from 'three-stdlib'

import {
  buildEdgeCurves,
  EDGE_SELECT_BOOST,
  samplePolyline,
  visibleEdges,
  type EdgeCurve,
} from './edges'
import type { PlacedNode } from './layout'
import { useBrainStore } from './store'

const DASH_FLOW_SPEED = 0.12 // dashOffset 초당 이동량 — 점선이 방향대로 흐른다
const PULSES_PER_EDGE = 2
const PULSE_SPEED = 0.3 // 곡선 1회 주행 ≈ 3.3초
const PULSE_COLOR = '#9fd8ff' // 전파 스파크 — 선택 링과 같은 인터랙션 피드백 등급

function gradientColors(
  curve: EdgeCurve,
  boost: number,
): Array<[number, number, number]> {
  const from = new THREE.Color(curve.visual.colorFrom)
  const to = new THREE.Color(curve.visual.colorTo)
  const out: Array<[number, number, number]> = []
  const last = curve.points.length - 1
  for (let i = 0; i < curve.points.length; i++) {
    const c = from.clone().lerp(to, i / last).multiplyScalar(boost)
    out.push([c.r, c.g, c.b])
  }
  return out
}

/** 폴리라인(13점) → segment 쌍(12×2) — 여러 curve를 한 draw로 배치 */
function toSegments(curves: EdgeCurve[], boost: number): {
  points: Array<[number, number, number]>
  colors: Array<[number, number, number]>
} {
  const points: Array<[number, number, number]> = []
  const colors: Array<[number, number, number]> = []
  for (const curve of curves) {
    const grad = gradientColors(curve, boost)
    for (let i = 0; i < curve.points.length - 1; i++) {
      points.push([...curve.points[i]] as [number, number, number])
      points.push([...curve.points[i + 1]] as [number, number, number])
      colors.push(grad[i], grad[i + 1])
    }
  }
  return { points, colors }
}

interface DashedBucketData {
  key: string
  points: Array<[number, number, number]>
  colors: Array<[number, number, number]>
  width: number
  opacity: number
}

/** 점선 버킷 — 선택 버킷(flow)은 dashOffset을 흘려 전파 방향을 보여준다 */
function DashedBucket({ bucket, flow }: { bucket: DashedBucketData; flow: boolean }) {
  const ref = useRef<Line2 | null>(null)
  useFrame((_, delta) => {
    const mat = ref.current?.material
    if (!flow || !mat) return
    // lineDistance 증가 방향(from→to)으로 대시가 진행하도록 음의 오프셋
    mat.dashOffset -= delta * DASH_FLOW_SPEED
  })
  return (
    <Line
      ref={ref}
      points={bucket.points}
      vertexColors={bucket.colors}
      color="white"
      segments
      lineWidth={bucket.width}
      dashed
      dashSize={0.03}
      gapSize={0.022}
      transparent
      opacity={bucket.opacity}
      depthWrite={false}
    />
  )
}

/** 측정 edge 1개 — flicker(§7-5)는 재질 불투명 진동, Hz ∝ confusion_rate */
function MeasuredEdge({ curve }: { curve: EdgeCurve }) {
  const ref = useRef<Line2 | null>(null)
  const base =
    curve.visual.opacity * (curve.touchesSelected ? EDGE_SELECT_BOOST : 1)
  useFrame(({ clock }) => {
    const mat = ref.current?.material
    if (!mat || curve.visual.flickerHz === 0) return
    mat.opacity = Math.min(
      0.95,
      base * (0.55 + 0.45 * Math.sin(clock.elapsedTime * 2 * Math.PI * curve.visual.flickerHz)),
    )
  })
  return (
    <Line
      ref={ref}
      points={curve.points as Array<[number, number, number]>}
      vertexColors={gradientColors(curve, 1)}
      color="white"
      lineWidth={curve.visual.width}
      transparent
      opacity={Math.min(0.95, base)}
      depthWrite={false}
    />
  )
}

/** 전파 펄스 — 선택 노드에 닿은 곡선들을 따라 이동하는 스파크(방향 = §5-6 혼동 방향) */
function SelectedEdgePulses({ curves }: { curves: EdgeCurve[] }) {
  const geomRef = useRef<THREE.BufferGeometry | null>(null)
  const positions = useMemo(
    () => new Float32Array(curves.length * PULSES_PER_EDGE * 3),
    [curves],
  )
  useFrame(({ clock }) => {
    const t = clock.elapsedTime
    let k = 0
    for (let e = 0; e < curves.length; e++) {
      for (let p = 0; p < PULSES_PER_EDGE; p++) {
        // edge별 위상차(e·0.13)로 펄스가 일제히 겹치지 않는다 — 장식 위상, 데이터 아님
        const phase = (t * PULSE_SPEED + p / PULSES_PER_EDGE + e * 0.13) % 1
        const pos = samplePolyline(curves[e].points, phase)
        positions[k++] = pos[0]
        positions[k++] = pos[1]
        positions[k++] = pos[2]
      }
    }
    const attr = geomRef.current?.attributes.position as THREE.BufferAttribute | undefined
    if (attr) attr.needsUpdate = true
  })
  if (curves.length === 0) return null
  return (
    // 위치가 매 프레임 변해 바운딩이 낡는다 — 컬링 끄기
    <points raycast={() => null} frustumCulled={false}>
      <bufferGeometry key={curves.length} ref={geomRef}>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial
        color={PULSE_COLOR}
        size={0.024}
        transparent
        opacity={0.9}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        sizeAttenuation
        toneMapped={false}
      />
    </points>
  )
}

export function ConfusionEdgeLayer({ nodes }: { nodes: PlacedNode[] }) {
  const payload = useBrainStore((s) => s.confusionEdges)
  const mode = useBrainStore((s) => s.edgeDisplayMode)
  const selectedNodeId = useBrainStore((s) => s.selectedNodeId)

  const selectedIntent = useMemo(
    () => nodes.find((n) => n.nodeId === selectedNodeId)?.intentId ?? null,
    [nodes, selectedNodeId],
  )

  const { dashedBuckets, measured, selCurves } = useMemo(() => {
    if (!payload || nodes.length === 0) {
      return {
        dashedBuckets: [] as DashedBucketData[],
        measured: [] as EdgeCurve[],
        selCurves: [] as EdgeCurve[],
      }
    }
    const posByIntent = new Map(nodes.map((n) => [n.intentId, n.position]))
    const visible = visibleEdges(payload.edges, mode, selectedIntent)
    const { curves } = buildEdgeCurves(visible, posByIntent, selectedIntent)

    const measuredCurves = curves.filter((c) => !c.visual.dashed)
    const dashed = curves.filter((c) => c.visual.dashed)
    // 버킷 = state × 선택여부 (불투명·두께는 state, 강조는 색 배수)
    const grouped = new Map<string, EdgeCurve[]>()
    for (const c of dashed) {
      const key = `${c.edge.state}-${c.touchesSelected ? 'sel' : 'base'}`
      grouped.set(key, [...(grouped.get(key) ?? []), c])
    }
    const buckets: DashedBucketData[] = [...grouped.entries()].sort().map(([key, group]) => {
      const isSel = key.endsWith('sel')
      return {
        key,
        ...toSegments(group, isSel ? EDGE_SELECT_BOOST : 1),
        // 선택 부채꼴은 탐색의 핵심 — 배경 가설 지형(전체 보기)보다 뚜렷하게 3배 불투명
        width: group[0].visual.width * (isSel ? 1.6 : 1),
        opacity: Math.min(0.85, group[0].visual.opacity * (isSel ? 3 : 1)),
      }
    })
    return {
      dashedBuckets: buckets,
      measured: measuredCurves,
      selCurves: curves.filter((c) => c.touchesSelected),
    }
  }, [payload, nodes, mode, selectedIntent])

  if (dashedBuckets.length === 0 && measured.length === 0) return null
  return (
    <group>
      {dashedBuckets.map((b) => (
        <DashedBucket key={b.key} bucket={b} flow={b.key.endsWith('sel')} />
      ))}
      {measured.map((c) => (
        <MeasuredEdge key={c.edge.edge_id} curve={c} />
      ))}
      <SelectedEdgePulses curves={selCurves} />
    </group>
  )
}
