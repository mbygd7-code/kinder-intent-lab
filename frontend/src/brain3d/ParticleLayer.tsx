/**
 * 장식 파티클 레이어 — 의미 노드와 분리 (§7-5 정보 정직성).
 *
 * 뇌 실루엣(brainShape)의 표면 셸 + 내부 볼륨에 결정론적으로 뿌린 점들.
 * 색은 최근접 region 앵커(보로노이) → 단일 뇌 안에 7색 로브가 자연 경계로 나뉜다.
 * 셸은 밝게(블룸 대상), 볼륨은 어둡게(내부 성운). 클릭·호버 불가(raycast 차단), 상태 없음.
 * 의미 노드의 brightness 인코딩과 무관 — 이 밝기는 순수 장식이다.
 */
import { useMemo } from 'react'
import * as THREE from 'three'

import { nearestRegion, sampleShell, sampleVolume } from './brainShape'
import { REGION_BY_ID } from './regions'

// 3계층 셸(더스트/비드/글로우 비드) — 레퍼런스의 "크기가 섞인 빛 알갱이" 질감. 전부 장식.
export const DUST_COUNT = 3200
export const BEAD_COUNT = 950
export const GLOW_BEAD_COUNT = 280
export const VOLUME_COUNT = 1400
const DUST_INTENSITY = 1.0
const BEAD_INTENSITY = 1.5
const GLOW_INTENSITY = 2.0 // 블룸 강타 — 큰 알갱이가 별처럼 빛난다
const VOLUME_INTENSITY = 0.34

function colorize(positions: Float32Array, intensity: number): Float32Array {
  const n = positions.length / 3
  const colors = new Float32Array(n * 3)
  const c = new THREE.Color()
  for (let i = 0; i < n; i++) {
    const p = [positions[i * 3], positions[i * 3 + 1], positions[i * 3 + 2]] as const
    c.set(REGION_BY_ID[nearestRegion(p)].color).multiplyScalar(intensity)
    colors[i * 3] = c.r
    colors[i * 3 + 1] = c.g
    colors[i * 3 + 2] = c.b
  }
  return colors
}

function Cloud({ positions, colors, size, opacity }: {
  positions: Float32Array
  colors: Float32Array
  size: number
  opacity: number
}) {
  return (
    // raycast 차단 — 장식은 어떤 상호작용도 갖지 않는다
    <points raycast={() => null}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[colors, 3]} />
      </bufferGeometry>
      <pointsMaterial
        size={size}
        vertexColors
        transparent
        opacity={opacity}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        sizeAttenuation
        toneMapped={false}
      />
    </points>
  )
}

interface CloudSpec {
  positions: Float32Array
  colors: Float32Array
  size: number
  opacity: number
}

function buildLayers(): CloudSpec[] {
  const dust = sampleShell(DUST_COUNT, 0xb2a1_c3d4)
  const beads = sampleShell(BEAD_COUNT, 0xbead_0001)
  const glow = sampleShell(GLOW_BEAD_COUNT, 0x610_44ea)
  const volume = sampleVolume(VOLUME_COUNT)
  return [
    { positions: dust, colors: colorize(dust, DUST_INTENSITY), size: 0.013, opacity: 0.85 },
    { positions: beads, colors: colorize(beads, BEAD_INTENSITY), size: 0.028, opacity: 0.95 },
    { positions: glow, colors: colorize(glow, GLOW_INTENSITY), size: 0.05, opacity: 1.0 },
    { positions: volume, colors: colorize(volume, VOLUME_INTENSITY), size: 0.013, opacity: 0.5 },
  ]
}

// 모듈 레벨 지연 캐시 — 결정론 샘플이라 2D↔3D 재마운트마다 재계산할 이유가 없다
let layersCache: CloudSpec[] | null = null

export function ParticleLayer() {
  const layers = useMemo(() => (layersCache ??= buildLayers()), [])
  return (
    <group>
      {layers.map((l, i) => (
        <Cloud key={i} positions={l.positions} colors={l.colors} size={l.size} opacity={l.opacity} />
      ))}
    </group>
  )
}
