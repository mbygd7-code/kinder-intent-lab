/**
 * T5.4 Persona Overlay 3D 레이어 (§7-6·§4-2) — 선택된 성향 클러스터의 prior 분포를
 * 노드 위 additive 글로우 디스크로 얹는다. 마크 계산은 personaOverlay.markFromPrior가
 * 유일한 원천(2D fallback과 공유).
 *
 * 절대 규칙 3(§7-5 원칙 8): 부가 채널이다 — NodesMesh(size·밝기·density·ring·pulse)는
 * 이 레이어의 존재를 모르고, 오버레이 ON/OFF에 노드 자체 렌더링은 1픽셀도 변하지 않는다.
 * prior 부재/중립(0.5) 노드는 마크를 아예 그리지 않는다(중립 ≠ 어두움).
 */
import { Billboard } from '@react-three/drei'
import { useMemo } from 'react'
import * as THREE from 'three'

import type { PlacedNode } from './layout'
import { BOOST_COLOR, DAMP_COLOR, markFromPrior } from './personaOverlay'

interface Props {
  nodes: PlacedNode[]
  /** intent_id → prior (§5-5) — 선택된 클러스터의 것 */
  priors: ReadonlyMap<string, number>
}

// 표현 상수(프레젠테이션) — 실험 임계값 아님. 노드(0.03~0.062)보다 살짝 큰 디스크
const DISC_MIN = 0.055
const DISC_GROW = 0.055
const OPACITY_MIN = 0.16
const OPACITY_GROW = 0.5

export function PersonaOverlayLayer({ nodes, priors }: Props) {
  const marks = useMemo(
    () =>
      nodes
        .map((node) => ({ node, mark: markFromPrior(priors.get(node.intentId)) }))
        .filter(({ mark }) => mark.strength > 0),
    [nodes, priors],
  )
  return (
    <group>
      {marks.map(({ node, mark }) => (
        <Billboard key={node.nodeId} position={[...node.position]}>
          {/* raycast 차단 — 오버레이가 노드 클릭을 가로채지 않는다 */}
          <mesh raycast={() => null}>
            <circleGeometry args={[DISC_MIN + DISC_GROW * mark.strength, 24]} />
            <meshBasicMaterial
              color={mark.boost ? BOOST_COLOR : DAMP_COLOR}
              transparent
              opacity={OPACITY_MIN + OPACITY_GROW * mark.strength}
              blending={THREE.AdditiveBlending}
              depthWrite={false}
              toneMapped={false}
            />
          </mesh>
        </Billboard>
      ))}
    </group>
  )
}
