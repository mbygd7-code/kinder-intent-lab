/**
 * 의미 노드 레이어 — instanced mesh 1드로우콜 (§7-5 성능 규칙).
 *
 * 인코딩 바인딩은 encodings.visualFromNode(§7-5 표)가 유일한 원천이다. 이 파일은
 * NodeVisual을 **읽기만** 한다(encodings.test의 소스 스캔이 강제):
 *   size ← visual.size · 색 ← region 색 × visual.brightness · halo ← density ·
 *   pending ring ← visual.pendingRing · pulse ← store.pulsingNodeIds(§5-4 활성)
 */
import { Billboard } from '@react-three/drei'
import { useFrame, type ThreeEvent } from '@react-three/fiber'
import { useLayoutEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'

import { SKELETON_VISUAL, type NodeVisual } from './encodings'
import type { PlacedNode } from './layout'
import { REGION_BY_ID } from './regions'
import { useBrainStore } from './store'

interface Props {
  nodes: PlacedNode[]
  /** nodeId → §7-5 시각 속성. 없으면 스켈레톤 기본(Dormant) */
  visuals?: ReadonlyMap<string, NodeVisual>
}

const PULSE_SPEED = 3.2 // 장식 아님 — §5-4 활성 표시의 표현 상수
const PULSE_AMP = 0.35

export function NodesMesh({ nodes, visuals }: Props) {
  const ref = useRef<THREE.InstancedMesh>(null)
  const selectedNodeId = useBrainStore((s) => s.selectedNodeId)
  const pulsing = useBrainStore((s) => s.pulsingNodeIds)
  const select = useBrainStore((s) => s.select)

  const visualOf = useMemo(
    () => (n: PlacedNode) => visuals?.get(n.nodeId) ?? SKELETON_VISUAL,
    [visuals],
  )

  useLayoutEffect(() => {
    const mesh = ref.current
    if (!mesh) return
    const m = new THREE.Matrix4()
    const color = new THREE.Color()
    nodes.forEach((node, i) => {
      const v = visualOf(node)
      m.makeScale(v.size, v.size, v.size)
      m.setPosition(node.position[0], node.position[1], node.position[2])
      mesh.setMatrixAt(i, m)
      color.set(REGION_BY_ID[node.region].color).multiplyScalar(v.brightness)
      mesh.setColorAt(i, color)
    })
    mesh.instanceMatrix.needsUpdate = true
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
    // pulsing 의존성: 집합이 줄어들 때 베이스 행렬을 재스탬프해 확대 스케일이 잔류하지 않게
    // 한다 — size는 §7-5 Training Volume 의미 채널이라 잔류 확대는 데이터 왜곡이다.
  }, [nodes, visualOf, pulsing])

  // Pulse(§5-4): 활성 노드만 스케일 진동 — pulsing이 비면 프레임 작업 없음
  useFrame(({ clock }) => {
    const mesh = ref.current
    if (!mesh || pulsing.size === 0) return
    const m = new THREE.Matrix4()
    const t = clock.getElapsedTime()
    nodes.forEach((node, i) => {
      if (!pulsing.has(node.nodeId)) return
      const v = visualOf(node)
      const s = v.size * (1 + PULSE_AMP * (0.5 + 0.5 * Math.sin(t * PULSE_SPEED)))
      m.makeScale(s, s, s)
      m.setPosition(node.position[0], node.position[1], node.position[2])
      mesh.setMatrixAt(i, m)
    })
    mesh.instanceMatrix.needsUpdate = true
  })

  const selected = useMemo(
    () => nodes.find((n) => n.nodeId === selectedNodeId) ?? null,
    [nodes, selectedNodeId],
  )
  const pending = useMemo(
    () => nodes.filter((n) => visualOf(n).pendingRing),
    [nodes, visualOf],
  )

  // Density(§3-5) → 노드 주변 halo: 노드당 포인트 1개, 단일 드로우콜
  const halo = useMemo(() => {
    const positions = new Float32Array(nodes.length * 3)
    const colors = new Float32Array(nodes.length * 3)
    const c = new THREE.Color()
    nodes.forEach((node, i) => {
      const v = visualOf(node)
      positions.set(node.position, i * 3)
      c.set(REGION_BY_ID[node.region].color).multiplyScalar(0.5 * v.density)
      colors[i * 3] = c.r
      colors[i * 3 + 1] = c.g
      colors[i * 3 + 2] = c.b
    })
    return { positions, colors }
  }, [nodes, visualOf])

  const onClick = (e: ThreeEvent<MouseEvent>) => {
    e.stopPropagation()
    // 드래그(회전) 후 릴리즈를 클릭으로 오인하지 않는다 — fiber는 노드 클릭엔 delta 필터를
    // 적용하지 않으므로(onPointerMissed에만 적용) 여기서 걸러 선택/해제 가드를 대칭으로 만든다.
    if (e.delta > 2) return
    if (e.instanceId !== undefined) select(nodes[e.instanceId].nodeId)
  }

  return (
    <group>
      <instancedMesh ref={ref} args={[undefined, undefined, nodes.length]} onClick={onClick}>
        <icosahedronGeometry args={[1, 1]} />
        <meshBasicMaterial toneMapped={false} />
      </instancedMesh>

      {/* Density halo — 장식 아님(§7-5 Density 채널), 상호작용 없음 */}
      <points raycast={() => null}>
        <bufferGeometry>
          <bufferAttribute attach="attributes-position" args={[halo.positions, 3]} />
          <bufferAttribute attach="attributes-color" args={[halo.colors, 3]} />
        </bufferGeometry>
        <pointsMaterial
          size={0.09}
          vertexColors
          transparent
          opacity={0.4}
          depthWrite={false}
          blending={THREE.AdditiveBlending}
          sizeAttenuation
          toneMapped={false}
        />
      </points>

      {/* Pending Ring(§6-5): 훈련됨·검증 대기 — 다음 Arena까지 밝기 대신 링 */}
      {pending.map((node) => (
        <Billboard key={node.nodeId} position={[...node.position]}>
          <mesh raycast={() => null}>
            <ringGeometry args={[0.075, 0.086, 32]} />
            <meshBasicMaterial color="#f8fafc" transparent opacity={0.85}
              side={THREE.DoubleSide} toneMapped={false} />
          </mesh>
        </Billboard>
      ))}

      {selected && (
        <Billboard position={[...selected.position]}>
          {/* 선택 하이라이트 링 — region 색 원 밝기 (선택은 시각 인코딩이 아닌 UI 상태) */}
          <mesh raycast={() => null}>
            <ringGeometry args={[0.055, 0.07, 32]} />
            <meshBasicMaterial
              color={REGION_BY_ID[selected.region].color}
              side={THREE.DoubleSide}
              toneMapped={false}
            />
          </mesh>
        </Billboard>
      )}
    </group>
  )
}
