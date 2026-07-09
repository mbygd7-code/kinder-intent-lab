/**
 * 장식 파티클 레이어 — 의미 노드와 분리 (§7-5).
 *
 * "수천 개 점은 장식 파티클 레이어로 분리 — 성능(단일 points 드로우콜)과 정보 정직성
 * (의미 있는 것처럼 보이지 않게) 둘 다를 위해." 클릭·호버 불가(raycast 차단), 상태 없음.
 * region 구름 주변에 결정론적으로 뿌려 뇌 실루엣을 만든다 — Math.random 금지(리로드 불변).
 */
import { useMemo } from 'react'
import * as THREE from 'three'

import { mulberry32 } from './hash'
import { REGIONS } from './regions'

const PARTICLE_COUNT = 2400
const SPREAD = 2.1 // region radius 대비 산포 배율 — 노드 구름을 감싸는 안개
const DIMNESS = 0.4

function buildParticles(): { positions: Float32Array; colors: Float32Array } {
  const rng = mulberry32(0x5eed_b4a1)
  const positions = new Float32Array(PARTICLE_COUNT * 3)
  const colors = new Float32Array(PARTICLE_COUNT * 3)
  const color = new THREE.Color()
  for (let i = 0; i < PARTICLE_COUNT; i++) {
    const region = REGIONS[i % REGIONS.length]
    const theta = 2 * Math.PI * rng()
    const phi = Math.acos(2 * rng() - 1)
    const r = region.radius * SPREAD * Math.cbrt(rng())
    positions[i * 3] = region.center[0] + r * Math.sin(phi) * Math.cos(theta)
    positions[i * 3 + 1] = region.center[1] + r * Math.sin(phi) * Math.sin(theta)
    positions[i * 3 + 2] = region.center[2] + r * Math.cos(phi)
    color.set(region.color).multiplyScalar(DIMNESS)
    colors[i * 3] = color.r
    colors[i * 3 + 1] = color.g
    colors[i * 3 + 2] = color.b
  }
  return { positions, colors }
}

export function ParticleLayer() {
  const { positions, colors } = useMemo(buildParticles, [])
  return (
    // raycast 차단 — 장식은 어떤 상호작용도 갖지 않는다 (정보 정직성)
    <points raycast={() => null}>
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[colors, 3]} />
      </bufferGeometry>
      <pointsMaterial
        size={0.012}
        vertexColors
        transparent
        opacity={0.55}
        depthWrite={false}
        blending={THREE.AdditiveBlending}
        sizeAttenuation
      />
    </points>
  )
}
