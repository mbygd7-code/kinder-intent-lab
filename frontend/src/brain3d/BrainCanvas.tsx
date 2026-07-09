/**
 * 3D Brain 캔버스 — Zoom 0 (§7-1): 회전(드래그)·줌(휠) + 노드/파티클/라벨 레이어.
 * 빈 공간 클릭 = 선택 해제. 저사양 fallback은 BrainScreen이 결정한다.
 */
import { OrbitControls } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'

import type { PlacedNode } from './layout'
import { NodesMesh } from './NodesMesh'
import { ParticleLayer } from './ParticleLayer'
import { RegionLabels } from './RegionLabels'
import { useBrainStore } from './store'

interface Props {
  nodes: PlacedNode[]
}

export function BrainCanvas({ nodes }: Props) {
  const select = useBrainStore((s) => s.select)
  return (
    <Canvas
      camera={{ position: [0, 0.5, 3.4], fov: 45 }}
      dpr={[1, 2]}
      onPointerMissed={() => select(null)}
    >
      <NodesMesh nodes={nodes} />
      <ParticleLayer />
      <RegionLabels />
      <OrbitControls
        enablePan={false}
        minDistance={1.8}
        maxDistance={6.5}
        autoRotate
        autoRotateSpeed={0.6}
        makeDefault
      />
    </Canvas>
  )
}
