/**
 * 뇌 필드 렌더러 — particles.ts(유일 인코더)의 RegionField를 그리기만 한다.
 *
 * 뇌 모양 파티클 필드는 항상 존재(형태)하고, region 훈련 에너지에 따라
 * 채도·광량·알갱이 수가 커진다 — "학습될수록 그 영역이 화려해진다".
 * region별 그룹 렌더: 호버된 region은 재질 배수(HOVER_BOOST)로 그 입자들만 살짝
 * 밝아진다 — 별도 오버레이 없이 뇌 자체가 반응한다(2026-07-11 사용자 요청).
 * 입자는 비정형 감광 트윙클(twinkle.ts 전용 셰이더 — 장식, 광량 상한 불변)로 깜박인다.
 * 모든 색×배수는 블룸 임계 미만(particles.test.ts 강제) — 빛남은 Arena 정확도 전용.
 * 상호작용 없음(raycast 차단). region당 ≤4드로우(빈 레이어는 생략).
 */
import { useFrame } from '@react-three/fiber'
import { useEffect, useMemo } from 'react'
import * as THREE from 'three'

import type { PlacedNode } from './layout'
import {
  cachedShellField,
  HOVER_BOOST,
  regionEnergies,
  type ParticleMetrics,
  type RegionField,
  type ShellLayerBuffers,
} from './particles'
import { useBrainStore } from './store'
import { makeTwinkleMaterial, sharedPointScale, sharedTwinkleTime } from './twinkle'

function Cloud({ layer, size, opacity, tint }: {
  layer: ShellLayerBuffers
  size: number
  opacity: number
  tint: THREE.Color
}) {
  const material = useMemo(makeTwinkleMaterial, [])
  useEffect(() => () => material.dispose(), [material])
  useEffect(() => {
    material.uniforms.uSize.value = size
    material.uniforms.uOpacity.value = opacity
    ;(material.uniforms.uTint.value as THREE.Color).copy(tint)
  }, [material, size, opacity, tint])
  if (layer.positions.length === 0) return null
  return (
    <points raycast={() => null}>
      {/* key로 버퍼 교체 강제 — 에너지 변화(재조회) 시 지오메트리 재생성 */}
      <bufferGeometry key={`${layer.positions.length}-${layer.colors[0] ?? 0}`}>
        <bufferAttribute attach="attributes-position" args={[layer.positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[layer.colors, 3]} />
      </bufferGeometry>
      <primitive object={material} attach="material" />
    </points>
  )
}

const TINT_BASE = new THREE.Color(1, 1, 1)
const TINT_HOVER = new THREE.Color(HOVER_BOOST, HOVER_BOOST, HOVER_BOOST)
/** 다른 region 무언가가 호버 중일 때 비호버 region 톤 — 대비로 호버가 선명해진다 */
const TINT_REST = new THREE.Color(0.85, 0.85, 0.85)
const HOVER_OPACITY = 1.35 // 호버 불투명 배수 (cap 1)
const REST_OPACITY = 0.72 // 비호버 가라앉힘
const HOVER_SIZE = 1.4 // 호버 입자 크기 배수 — 광량 아닌 크기로 "선명함"을 더한다

function RegionFieldGroup({ field, hovered, anyHovered }: {
  field: RegionField
  hovered: boolean
  anyHovered: boolean
}) {
  const tint = hovered ? TINT_HOVER : anyHovered ? TINT_REST : TINT_BASE
  const op = (base: number) =>
    Math.min(1, base * (hovered ? HOVER_OPACITY : anyHovered ? REST_OPACITY : 1))
  const sz = (base: number) => base * (hovered ? HOVER_SIZE : 1)
  return (
    <group>
      <Cloud layer={field.volume} size={sz(0.012)} opacity={op(0.5)} tint={tint} />
      <Cloud layer={field.dust} size={sz(0.011)} opacity={op(0.8)} tint={tint} />
      <Cloud layer={field.beads} size={sz(0.024)} opacity={op(0.9)} tint={tint} />
      <Cloud layer={field.accents} size={sz(0.045)} opacity={op(0.95)} tint={tint} />
    </group>
  )
}

export function BrainFieldLayer({ nodes, metrics }: {
  nodes: PlacedNode[]
  metrics: ReadonlyMap<string, ParticleMetrics>
}) {
  const hoveredRegionId = useBrainStore((s) => s.hoveredRegionId)
  const field = useMemo(
    () => cachedShellField(regionEnergies(nodes, metrics)),
    [nodes, metrics],
  )
  // 트윙클 드라이버 — 전 재질이 공유하는 uniform 2개만 갱신 (CPU 비용 ≈ 0)
  useFrame(({ clock, gl }) => {
    sharedTwinkleTime.value = clock.elapsedTime
    sharedPointScale.value = gl.domElement.height / 2 // PointsMaterial sizeAttenuation 규칙
    if (import.meta.env.DEV) {
      // dev 계측 — 드라이버 생존 확인용 (프로덕션 번들에서 제거됨)
      ;(window as unknown as Record<string, unknown>).__twinkleTime = sharedTwinkleTime
    }
  })
  return (
    <group>
      {field.map((rf) => (
        <RegionFieldGroup
          key={rf.region}
          field={rf}
          hovered={hoveredRegionId === rf.region}
          anyHovered={hoveredRegionId !== null}
        />
      ))}
    </group>
  )
}
