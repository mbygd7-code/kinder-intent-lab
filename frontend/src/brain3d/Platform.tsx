/**
 * 홀로그램 플랫폼 — 뇌 아래 빛 풀 + radial 도트 링 + 바닥 먼지 (레퍼런스 이미지 하단 디테일).
 * 순수 장식(§7-5): 데이터 인코딩 없음, 상호작용 없음. 텍스처는 캔버스 그라디언트(결정론).
 * 동심원 실선 링은 제거(뇌와 다른 방향으로 도는 게 부자연스러웠음) — 도트 링만 남긴다.
 */
import { useMemo } from 'react'
import * as THREE from 'three'

import { mulberry32 } from './hash'

const PLATFORM_Y = -1.27
const CYAN = '#22d3ee'

const DUST_COUNT = 420
const DUST_SEED = 0xd0_57ed
const DOT_RINGS = [0.47, 0.69, 0.9, 1.12] // 점선 원 — radial 도트 링
const DOTS_PER_RING = 72

/** 부드러운 방사형 빛 풀 텍스처 (결정론 — 그라디언트만) */
function makeGlowTexture(): THREE.Texture {
  const size = 256
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')!
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  g.addColorStop(0, 'rgba(140, 235, 255, 0.85)')
  g.addColorStop(0.25, 'rgba(56, 189, 248, 0.4)')
  g.addColorStop(0.6, 'rgba(34, 211, 238, 0.12)')
  g.addColorStop(1, 'rgba(34, 211, 238, 0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, size, size)
  const tex = new THREE.CanvasTexture(canvas)
  tex.needsUpdate = true
  return tex
}

function floorDust(): Float32Array {
  const rng = mulberry32(DUST_SEED)
  const out = new Float32Array(DUST_COUNT * 3)
  for (let i = 0; i < DUST_COUNT; i++) {
    const ang = rng() * Math.PI * 2
    const r = 0.3 + Math.sqrt(rng()) * 1.3
    out[i * 3] = Math.cos(ang) * r
    out[i * 3 + 1] = PLATFORM_Y + rng() * 0.05
    out[i * 3 + 2] = Math.sin(ang) * r
  }
  return out
}

function dotRings(): Float32Array {
  const out = new Float32Array(DOT_RINGS.length * DOTS_PER_RING * 3)
  let i = 0
  for (const r of DOT_RINGS) {
    for (let k = 0; k < DOTS_PER_RING; k++) {
      const ang = (k / DOTS_PER_RING) * Math.PI * 2
      out[i * 3] = Math.cos(ang) * r
      out[i * 3 + 1] = PLATFORM_Y + 0.005
      out[i * 3 + 2] = Math.sin(ang) * r
      i++
    }
  }
  return out
}

export function Platform() {
  const glowTex = useMemo(makeGlowTexture, [])
  const dustPos = useMemo(floorDust, [])
  const dotPos = useMemo(dotRings, [])
  return (
    <group raycast={() => null}>
      {/* 빛 풀 — 부드러운 방사형 광 (레퍼런스의 바닥 발광면) */}
      <mesh position={[0, PLATFORM_Y - 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        <circleGeometry args={[1.6, 64]} />
        <meshBasicMaterial
          map={glowTex}
          transparent
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          toneMapped={false}
        />
      </mesh>

      {/* radial 도트 링 — 정적(회전 없음) */}
      <points raycast={() => null}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[dotPos, 3]} />
        </bufferGeometry>
        <pointsMaterial color={CYAN} size={0.016} transparent opacity={0.65}
          depthWrite={false} blending={THREE.AdditiveBlending} sizeAttenuation toneMapped={false} />
      </points>

      {/* 뇌간 하단 접점 글로우 */}
      <sprite position={[0, -1.02, -0.42]} scale={[0.5, 0.5, 1]}>
        <spriteMaterial map={glowTex} transparent opacity={0.7} depthWrite={false}
          blending={THREE.AdditiveBlending} />
      </sprite>

      <points raycast={() => null}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[dustPos, 3]} />
        </bufferGeometry>
        <pointsMaterial color={CYAN} size={0.012} transparent opacity={0.5}
          depthWrite={false} blending={THREE.AdditiveBlending} sizeAttenuation toneMapped={false} />
      </points>
    </group>
  )
}
