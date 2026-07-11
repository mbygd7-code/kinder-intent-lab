/**
 * 3D Brain 캔버스 — Zoom 0 (§7-1): 회전(드래그)·줌(휠) + 레이어 합성 + 블룸.
 *
 * 레이어 규약(정보 정직성): 유색 = 데이터, 단색 slate = 구조물.
 * - 의미 노드(NodesMesh, 상호작용) · evidence 파티클(훈련 근거량) · 혼동 edge(§5-6)
 *   · region glow(Arena reliability) · 플랫폼 게이지(성장 스테이지·KTIB) = 전부 실데이터
 * - StructuralShell(뇌 실루엣) = 데이터 아님 — 단색·정적
 * 블룸(BLOOM_THRESHOLD)은 §7-5 밝기(Arena 정확도) 채널 전용 — 데이터 파티클·구조물은
 * 임계 미만 광량으로 억제된다(각 인코더 테스트가 강제).
 */
import { OrbitControls } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { Bloom, EffectComposer } from '@react-three/postprocessing'

import { BLOOM_THRESHOLD } from './bloom'
import { BrainFieldLayer } from './BrainFieldLayer'
import { ConfusionEdgeLayer } from './ConfusionEdgeLayer'
import { EdgeInfoLabels } from './EdgeInfoLabels'
import type { NodeVisual } from './encodings'
import { EvidenceParticleLayer } from './EvidenceParticleLayer'
import type { PlacedNode } from './layout'
import { NodesMesh } from './NodesMesh'
import type { ParticleMetrics } from './particles'
import { PersonaOverlayLayer } from './PersonaOverlayLayer'
import { Platform } from './Platform'
import { RegionGlowLayer } from './RegionGlowLayer'
import { RegionHoverTargets } from './RegionHoverTargets'
import { RegionLabels } from './RegionLabels'
import { StructuralShell } from './StructuralShell'
import { useBrainStore } from './store'

interface Props {
  nodes: PlacedNode[]
  visuals?: ReadonlyMap<string, NodeVisual>
  /** evidence 파티클 원천(노드별 훈련 근거 지표) — 없으면(mock 등) 파티클 없음 */
  metrics?: ReadonlyMap<string, ParticleMetrics>
  /** T5.4 Persona Overlay(§7-6) — 선택 클러스터의 intent_id → prior. null = 오버레이 OFF */
  overlayPriors?: ReadonlyMap<string, number> | null
}

const EMPTY_METRICS: ReadonlyMap<string, ParticleMetrics> = new Map()

export function BrainCanvas({ nodes, visuals, metrics, overlayPriors }: Props) {
  const select = useBrainStore((s) => s.select)
  return (
    <Canvas
      camera={{ position: [3.05, 0.35, -0.45], fov: 42 }}
      dpr={[1, 1.75]}
      onPointerMissed={() => select(null)}
      gl={{ antialias: true }}
    >
      <NodesMesh nodes={nodes} visuals={visuals} />
      {/* 절대 규칙 3: 오버레이는 NodesMesh 위 부가 레이어 — 노드 밝기 인코딩을 덮지 않는다 */}
      {overlayPriors && <PersonaOverlayLayer nodes={nodes} priors={overlayPriors} />}
      {/* 뇌 필드 — 형태 상시 + region 훈련 에너지로 채도·풍성함 증가 */}
      <BrainFieldLayer nodes={nodes} metrics={metrics ?? EMPTY_METRICS} />
      <EvidenceParticleLayer nodes={nodes} metrics={metrics ?? EMPTY_METRICS} />
      {/* §7-5 Edge Thickness/Flicker — §5-6 confusion_edges 실데이터 (store에서 구독) */}
      <ConfusionEdgeLayer nodes={nodes} />
      {/* 선택 노드의 연결 사유 칩 — 상대 노드 위에 방향·상태·출처·혼동률 */}
      <EdgeInfoLabels nodes={nodes} />
      <StructuralShell />
      {/* Arena reliability의 공간 광 — 미측정 region은 무광(부재) */}
      <RegionGlowLayer />
      {/* region 호버 — 투명 타깃 (활성화 표현은 BrainFieldLayer가 그 region 입자를 밝힘) */}
      <RegionHoverTargets />
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
          luminanceThreshold={BLOOM_THRESHOLD}
          luminanceSmoothing={0.22}
          radius={0.72}
        />
      </EffectComposer>
    </Canvas>
  )
}
