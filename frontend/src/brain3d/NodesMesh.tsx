/**
 * 의미 노드 레이어 — instanced mesh 1개로 ~100 노드 렌더 (§7-5 성능 규칙).
 *
 * 인코딩 바인딩은 encodings.ts의 §7-5 표를 따른다. T3.4는 스켈레톤: 전 노드
 * SKELETON_VISUAL(동일 크기·Dormant 밝기) — Arena 데이터가 없으므로 밝기를 지어내지
 * 않는다(원칙 8). 색은 region 3중 인코딩의 ①.
 */
import { Billboard } from '@react-three/drei'
import type { ThreeEvent } from '@react-three/fiber'
import { useLayoutEffect, useMemo, useRef } from 'react'
import * as THREE from 'three'

import { SKELETON_VISUAL } from './encodings'
import type { PlacedNode } from './layout'
import { REGION_BY_ID } from './regions'
import { useBrainStore } from './store'

interface Props {
  nodes: PlacedNode[]
}

export function NodesMesh({ nodes }: Props) {
  const ref = useRef<THREE.InstancedMesh>(null)
  const selectedNodeId = useBrainStore((s) => s.selectedNodeId)
  const select = useBrainStore((s) => s.select)

  useLayoutEffect(() => {
    const mesh = ref.current
    if (!mesh) return
    const m = new THREE.Matrix4()
    const color = new THREE.Color()
    nodes.forEach((node, i) => {
      m.makeScale(SKELETON_VISUAL.size, SKELETON_VISUAL.size, SKELETON_VISUAL.size)
      m.setPosition(node.position[0], node.position[1], node.position[2])
      mesh.setMatrixAt(i, m)
      // Dormant: region 색 × 낮은 밝기 (§7-6 Stage 0 — 측정 전엔 어둡다)
      color.set(REGION_BY_ID[node.region].color).multiplyScalar(SKELETON_VISUAL.brightness)
      mesh.setColorAt(i, color)
    })
    mesh.instanceMatrix.needsUpdate = true
    if (mesh.instanceColor) mesh.instanceColor.needsUpdate = true
  }, [nodes])

  const selected = useMemo(
    () => nodes.find((n) => n.nodeId === selectedNodeId) ?? null,
    [nodes, selectedNodeId],
  )

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
      {selected && (
        <Billboard position={[...selected.position]}>
          {/* 선택 하이라이트 링 — region 색 원 밝기 (선택은 시각 인코딩이 아닌 UI 상태) */}
          <mesh>
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
