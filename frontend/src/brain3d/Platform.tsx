/**
 * 홀로그램 플랫폼 — 원형 점선 링의 홀로그램 룩(초기 디자인) + 상태 게이지.
 *
 * 링 5개는 항상 청록 점선으로 보인다(홀로그램 크롬 — 2026-07-11 사용자 요청 복원).
 * 상태는 그 위에 얹힌다:
 * - 도달한 성장 스테이지(§7-6) 수만큼 링이 **더 밝고 굵게** 점등된다 (Stage 0 = 전부 기본 룩)
 * - 외곽 호 = KTIB global(§7-1). **미측정(null)이면 호가 아예 없다** — 0%로 그리지 않는다.
 * 빛 풀·바닥 먼지·뇌간 접점 글로우는 순수 크롬(데이터 아님, 뇌와 공간 분리된 바닥광).
 * statusEncodings.ts(litRings/ktibArc)가 유일 인코더.
 */
import { useMemo } from 'react'
import * as THREE from 'three'

import { mulberry32 } from './hash'
import { useBrainStore } from './store'
import { ktibArc, litRings, STAGE_RING_RADII } from './statusEncodings'

const PLATFORM_Y = -1.27
const RING_COLOR = '#22d3ee' // 홀로그램 기본 링 — 항상 보인다 (크롬)
const LIT_COLOR = '#a5f3fc' // 도달 스테이지 링 — 기본보다 밝게 점등
const KTIB_COLOR = '#67e8f9'
const DOTS_PER_RING = 72
const DUST_COUNT = 420
const DUST_SEED = 0xd0_57ed

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

/** 바닥 먼지 — 순수 크롬(초기 디자인의 홀로그램 질감) */
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

function ringDots(radii: readonly number[]): Float32Array {
  const out = new Float32Array(radii.length * DOTS_PER_RING * 3)
  let i = 0
  for (const r of radii) {
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

function DotRing({ positions, color, size, opacity }: {
  positions: Float32Array
  color: string
  size: number
  opacity: number
}) {
  if (positions.length === 0) return null
  return (
    <points raycast={() => null}>
      <bufferGeometry key={positions.length}>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
      </bufferGeometry>
      <pointsMaterial color={color} size={size} transparent opacity={opacity}
        depthWrite={false} blending={THREE.AdditiveBlending} sizeAttenuation toneMapped={false} />
    </points>
  )
}

export function Platform() {
  const brainStage = useBrainStore((s) => s.brainStage)
  const ktibGlobal = useBrainStore((s) => s.ktibGlobal)
  const glowTex = useMemo(makeGlowTexture, [])
  const dustPos = useMemo(floorDust, [])

  // 링은 전부 홀로그램 기본 룩으로 항상 그리고, 도달 스테이지만 밝게 겹쳐 점등한다
  const { basePos, litPos } = useMemo(() => {
    const lit = litRings(brainStage)
    return {
      basePos: ringDots(STAGE_RING_RADII.filter((_, i) => !lit[i])),
      litPos: ringDots(STAGE_RING_RADII.filter((_, i) => lit[i])),
    }
  }, [brainStage])

  const arc = ktibArc(ktibGlobal) // §7-1 — null이면 호를 그리지 않는다

  return (
    <group raycast={() => null}>
      {/* 빛 풀 — 크롬 (뇌와 공간 분리된 바닥광, 데이터 아님) */}
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

      {/* 홀로그램 점선 링 — 항상 청록(초기 룩). 도달 스테이지 링만 더 밝고 굵게 */}
      <DotRing positions={basePos} color={RING_COLOR} size={0.016} opacity={0.65} />
      <DotRing positions={litPos} color={LIT_COLOR} size={0.022} opacity={0.95} />

      {/* KTIB 호 게이지 — 측정 전(null)엔 존재하지 않는다 */}
      {arc && arc.thetaLength > 0 && (
        <mesh
          position={[0, PLATFORM_Y + 0.006, 0]}
          rotation={[-Math.PI / 2, 0, Math.PI / 2]}
        >
          <ringGeometry args={[1.18, 1.21, 96, 1, 0, arc.thetaLength]} />
          <meshBasicMaterial
            color={KTIB_COLOR}
            transparent
            opacity={0.85}
            side={THREE.DoubleSide}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
            toneMapped={false}
          />
        </mesh>
      )}

      {/* 바닥 먼지 — 크롬 (초기 홀로그램 질감 복원) */}
      <points raycast={() => null}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[dustPos, 3]} />
        </bufferGeometry>
        <pointsMaterial color={RING_COLOR} size={0.012} transparent opacity={0.5}
          depthWrite={false} blending={THREE.AdditiveBlending} sizeAttenuation toneMapped={false} />
      </points>

      {/* 뇌간 하단 접점 글로우 — 크롬 */}
      <sprite position={[0, -1.02, -0.42]} scale={[0.5, 0.5, 1]}>
        <spriteMaterial map={glowTex} transparent opacity={0.7} depthWrite={false}
          blending={THREE.AdditiveBlending} />
      </sprite>
    </group>
  )
}
