/**
 * Evidence 파티클 렌더러 — particles.ts(유일 인코더)가 만든 버퍼를 그리기만 한다.
 *
 * 베이스(작음, region 색) + 스파크(큼, 금색 = GOLD·전문가 evidence) 2드로우.
 * 전 색상 luma < 블룸 임계(particles.test.ts 강제) — 빛남은 Arena 정확도 전용.
 * 베이스는 비정형 감광 트윙클(twinkle.ts — 장식, 광량 상한 불변)로 깜박이고,
 * 스파크는 자체 opacity 호흡(±10%)만 갖는다(이중 효과 방지). 둘 다 데이터 인코딩 아님.
 * 상호작용 없음(raycast 차단) — 클릭은 의미 노드(NodesMesh)만 받는다.
 */
import { useFrame } from '@react-three/fiber'
import { useEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'

import type { PlacedNode } from './layout'
import { cachedEvidenceClouds, type ParticleMetrics } from './particles'
import { makeTwinkleMaterial } from './twinkle'

/** 트윙클 베이스 입자 — twinkle.ts 전용 셰이더 재질 */
function TwinkleCloud({ positions, colors, size, opacity }: {
  positions: Float32Array
  colors: Float32Array
  size: number
  opacity: number
}) {
  const material = useMemo(makeTwinkleMaterial, [])
  useEffect(() => () => material.dispose(), [material])
  useEffect(() => {
    material.uniforms.uSize.value = size
    material.uniforms.uOpacity.value = opacity
  }, [material, size, opacity])
  if (positions.length === 0) return null
  return (
    <points raycast={() => null}>
      {/* key로 버퍼 교체를 강제 — 데이터 갱신(gym 제출) 시 지오메트리 재생성 */}
      <bufferGeometry key={`${positions.length}-${positions[0] ?? 0}`}>
        <bufferAttribute attach="attributes-position" args={[positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[colors, 3]} />
      </bufferGeometry>
      <primitive object={material} attach="material" />
    </points>
  )
}

export function EvidenceParticleLayer({ nodes, metrics }: {
  nodes: PlacedNode[]
  metrics: ReadonlyMap<string, ParticleMetrics>
}) {
  const clouds = useMemo(() => cachedEvidenceClouds(nodes, metrics), [nodes, metrics])
  const sparkMat = useRef<THREE.PointsMaterial | null>(null)

  // 장식 호흡 — 데이터 인코딩 아님(주기·진폭 고정), 스파크가 살아있는 느낌만 준다
  useFrame(({ clock }) => {
    if (sparkMat.current) {
      sparkMat.current.opacity = 0.85 + 0.1 * Math.sin(clock.elapsedTime * 1.4)
    }
  })

  return (
    <group>
      <TwinkleCloud
        positions={clouds.basePositions}
        colors={clouds.baseColors}
        size={0.01}
        opacity={0.5}
      />
      {clouds.sparkPositions.length > 0 && (
        <points raycast={() => null}>
          <bufferGeometry key={`${clouds.sparkPositions.length}-${clouds.sparkPositions[0] ?? 0}`}>
            <bufferAttribute attach="attributes-position" args={[clouds.sparkPositions, 3]} />
            <bufferAttribute attach="attributes-color" args={[clouds.sparkColors, 3]} />
          </bufferGeometry>
          <pointsMaterial
            ref={sparkMat}
            size={0.026}
            vertexColors
            transparent
            opacity={0.9}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
            sizeAttenuation
            toneMapped={false}
          />
        </points>
      )}
    </group>
  )
}
