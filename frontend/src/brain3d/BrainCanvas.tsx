/**
 * 3D Brain 캔버스 — Zoom 0 (§7-1): 회전(드래그)·줌(휠) + 레이어 합성 + 블룸.
 *
 * 레이어: 의미 노드(NodesMesh, 상호작용) / 장식(ParticleLayer 셸·볼륨, NeuralWeb, Platform —
 * 전부 raycast 차단) / RegionLabels(3중 인코딩 ②). 초기 카메라는 -x 측면 = 레퍼런스 이미지의
 * 사시상(전두가 화면 왼쪽) 프로필. 빈 공간 클릭 = 선택 해제.
 * 블룸(luminanceThreshold)은 장식 셸(고휘도)만 빛나게 하고 Dormant 의미 노드(저휘도)는
 * 어둡게 남긴다 — brightness 인코딩(원칙 8)을 장식이 오염하지 않는다.
 */
import { OrbitControls } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { Bloom, EffectComposer } from '@react-three/postprocessing'

import type { NodeVisual } from './encodings'
import type { PlacedNode } from './layout'
import { NeuralWeb } from './NeuralWeb'
import { NodesMesh } from './NodesMesh'
import { ParticleLayer } from './ParticleLayer'
import { Platform } from './Platform'
import { RegionLabels } from './RegionLabels'
import { useBrainStore } from './store'

interface Props {
  nodes: PlacedNode[]
  visuals?: ReadonlyMap<string, NodeVisual>
}

export function BrainCanvas({ nodes, visuals }: Props) {
  const select = useBrainStore((s) => s.select)
  return (
    <Canvas
      camera={{ position: [3.05, 0.35, -0.45], fov: 42 }}
      dpr={[1, 1.75]}
      onPointerMissed={() => select(null)}
      gl={{ antialias: true }}
    >
      <NodesMesh nodes={nodes} visuals={visuals} />
      <ParticleLayer />
      <NeuralWeb />
      <Platform />
      <RegionLabels />
      <OrbitControls
        enablePan={false}
        minDistance={1.9}
        maxDistance={6.5}
        target={[0, -0.15, 0]}
        // 상반구만: 폴라각 0(수직 위)~수평까지 — 바닥면 아래로 카메라가 내려가지 못하게 한다
        minPolarAngle={0.12}
        maxPolarAngle={Math.PI / 2}
        autoRotate
        autoRotateSpeed={0.3}
        makeDefault
      />
      <EffectComposer>
        <Bloom
          mipmapBlur
          intensity={1.15}
          luminanceThreshold={0.18}
          luminanceSmoothing={0.22}
          radius={0.72}
        />
      </EffectComposer>
    </Canvas>
  )
}
