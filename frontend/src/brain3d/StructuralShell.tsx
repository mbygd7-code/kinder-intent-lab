/**
 * 구조 스캐폴드 — 데이터 아님. 뇌 실루엣의 kNN 그물(와이어)만 그린다.
 *
 * 뇌 형태의 입자 질감은 BrainFieldLayer(dust — 에너지로 표정이 변하는 실데이터 필드)가
 * 담당하고, 여기는 형태를 잡아주는 정적 단색 그물뿐이다. 색·애니메이션 추가 금지 —
 * 단색 slate = 구조물이라는 색 규약(정보 정직성). 광량은 블룸 임계 미만
 * (StructuralShell.test.ts 강제). 1드로우, 정적 모듈 캐시.
 */
import { useMemo } from 'react'
import * as THREE from 'three'

import { buildWeb, sampleShell } from './brainShape'

export const SHELL_COLOR = '#5b6b85' // 단색 slate — region 7색과 뚜렷이 구분
export const SHELL_LINE_INTENSITY = 0.3 // luma 0.414 × 0.3 ≈ 0.124 < 0.18
const WEB_POINTS = 1400
const WEB_SEED = 0x0eb_51de
const WEB_K = 2
const WEB_MAX_DIST = 0.19

function buildLineBuffer(): Float32Array {
  const webPts = sampleShell(WEB_POINTS, WEB_SEED)
  const edges = buildWeb(webPts, WEB_K, WEB_MAX_DIST)
  const lines = new Float32Array(edges.length * 6)
  edges.forEach(([i, j], e) => {
    lines.set(
      [
        webPts[i * 3], webPts[i * 3 + 1], webPts[i * 3 + 2],
        webPts[j * 3], webPts[j * 3 + 1], webPts[j * 3 + 2],
      ],
      e * 6,
    )
  })
  return lines
}

// 정적 모듈 캐시 — 데이터 무관 구조물이라 2D↔3D 재마운트에도 1회만 계산
let lineCache: Float32Array | null = null

export function StructuralShell() {
  const lines = useMemo(() => (lineCache ??= buildLineBuffer()), [])
  const lineColor = useMemo(
    () => new THREE.Color(SHELL_COLOR).multiplyScalar(SHELL_LINE_INTENSITY),
    [],
  )
  return (
    <lineSegments raycast={() => null}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[lines, 3]} />
      </bufferGeometry>
      <lineBasicMaterial
        color={lineColor}
        transparent
        opacity={0.2}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        toneMapped={false}
      />
    </lineSegments>
  )
}
