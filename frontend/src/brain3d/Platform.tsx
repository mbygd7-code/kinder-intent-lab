/**
 * 홀로그램 플랫폼 — 뇌 아래 빛 풀 + 자연스러운 동심원 링 + radial 도트 + 이중 광기둥
 * (레퍼런스 이미지 하단 디테일). 순수 장식(§7-5): 데이터 인코딩 없음, 상호작용 없음.
 * 텍스처는 캔버스 그라디언트(결정론), 링 회전은 장식 모션.
 */
import { useFrame } from '@react-three/fiber'
import { useMemo, useRef } from 'react'
import * as THREE from 'three'

import { mulberry32 } from './hash'

const PLATFORM_Y = -1.27
const CYAN = '#22d3ee'

// 링 스펙: 반경/두께/불투명도 — 안쪽 하나가 밝은 주 링(레퍼런스), 바깥은 점점 옅게
const RING_SPECS: Array<{ r: number; w: number; o: number }> = [
  { r: 0.36, w: 0.007, o: 0.55 },
  { r: 0.58, w: 0.024, o: 0.9 }, // 주 링 — 밝고 두꺼움
  { r: 0.8, w: 0.005, o: 0.4 },
  { r: 1.0, w: 0.012, o: 0.3 },
  { r: 1.22, w: 0.005, o: 0.22 },
  { r: 1.45, w: 0.009, o: 0.12 },
]
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

export function Platform() {
  const rings = useRef<THREE.Group>(null)
  const glowTex = useMemo(makeGlowTexture, [])
  const dustPos = useMemo(floorDust, [])
  useFrame((_, delta) => {
    if (rings.current) rings.current.rotation.y += delta * 0.1 // 장식 모션
  })
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

      <group ref={rings} position={[0, PLATFORM_Y, 0]} rotation={[-Math.PI / 2, 0, 0]}>
        {RING_SPECS.map(({ r, w, o }, i) => (
          <mesh key={i}>
            <ringGeometry args={[r - w, r + w, 128]} />
            <meshBasicMaterial
              color={CYAN}
              transparent
              opacity={o}
              side={THREE.DoubleSide}
              blending={THREE.AdditiveBlending}
              depthWrite={false}
              toneMapped={false}
            />
          </mesh>
        ))}
      </group>

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
