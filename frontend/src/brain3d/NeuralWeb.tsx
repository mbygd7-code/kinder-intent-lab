/**
 * 장식 신경 웹 — 셸 점들의 kNN 삼각망 (레퍼런스 이미지의 와이어프레임 질감).
 *
 * **의미 없음**: §7-5의 Edge Thickness(연관)·Edge Flicker(혼동)는 §5-6 confusion_edges의
 * 의미 채널이며 이 웹과 무관하다. 이 레이어는 두께 균일·깜빡임 없음·상호작용 없음으로
 * 의미 edge와 시각적으로도 구분한다(정보 정직성). 단일 LineSegments 드로우콜.
 */
import { useMemo } from 'react'
import * as THREE from 'three'

import { buildWeb, nearestRegion, sampleShell } from './brainShape'
import { REGION_BY_ID } from './regions'

const WEB_POINTS = 2300 // 웹 정점 수(셸과 별도 시드/개수)
const WEB_SEED = 0x0eb_51de
const K = 3
const MAX_DIST = 0.19 // 촘촘한 삼각망 — 레퍼런스의 표면 그물 질감
const INTENSITY = 1.0

function buildWebBuffers(): { positions: Float32Array; colors: Float32Array } {
  const pts = sampleShell(WEB_POINTS, WEB_SEED)
  const edges = buildWeb(pts, K, MAX_DIST)
  const positions = new Float32Array(edges.length * 6)
  const colors = new Float32Array(edges.length * 6)
  const c = new THREE.Color()
  edges.forEach(([i, j], e) => {
    const pi = [pts[i * 3], pts[i * 3 + 1], pts[i * 3 + 2]] as const
    const pj = [pts[j * 3], pts[j * 3 + 1], pts[j * 3 + 2]] as const
    positions.set([...pi, ...pj], e * 6)
    for (const [slot, p] of [[0, pi], [1, pj]] as const) {
      c.set(REGION_BY_ID[nearestRegion(p)].color).multiplyScalar(INTENSITY)
      colors[e * 6 + slot * 3] = c.r
      colors[e * 6 + slot * 3 + 1] = c.g
      colors[e * 6 + slot * 3 + 2] = c.b
    }
  })
  return { positions, colors }
}

// 모듈 레벨 지연 캐시 — 결정론이므로(테스트 잠금) 2D↔3D 재마운트마다 O(n²) 웹을
// 다시 만들 이유가 없다. 첫 3D 진입 때 1회만 계산.
let webCache: { positions: Float32Array; colors: Float32Array } | null = null

export function NeuralWeb() {
  const { positions, colors } = useMemo(() => (webCache ??= buildWebBuffers()), [])

  return (
    <lineSegments raycast={() => null}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[colors, 3]} />
      </bufferGeometry>
      <lineBasicMaterial
        vertexColors
        transparent
        opacity={0.42}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        toneMapped={false}
      />
    </lineSegments>
  )
}
