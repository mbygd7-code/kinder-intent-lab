/**
 * 노드 배치 — nodeId 해시 시드 결정론 배치 (재렌더·리로드에 좌표 불변).
 *
 * 위치는 §7-5 3중 인코딩의 한 축: 노드는 소속 region 구름(중심+반경) 안에만 놓여
 * "보이는 위치 = 실제 소속"이 성립한다. 임베딩 기반 정밀 배치(§5-9 용도 ①)는 후속 —
 * 여기서는 구조 정직성(소속 region 안, 결정론)만 보장한다.
 */
import { fmix32, fnv1a, mulberry32 } from './hash'
import { REGION_BY_ID, type RegionId } from './regions'

export interface NodeSeed {
  nodeId: string
  intentId: string
  region: RegionId
}

export interface PlacedNode extends NodeSeed {
  position: readonly [number, number, number]
}

export function layoutNodes(seeds: NodeSeed[]): PlacedNode[] {
  return seeds.map((seed) => {
    const { center, radius } = REGION_BY_ID[seed.region]
    const rng = mulberry32(fmix32(fnv1a(seed.nodeId)))
    // 구 내부 균등 샘플: 방향(구면 균등) × 반경(cbrt로 부피 균등)
    const theta = 2 * Math.PI * rng()
    const phi = Math.acos(2 * rng() - 1)
    const r = radius * Math.cbrt(rng())
    const position: [number, number, number] = [
      center[0] + r * Math.sin(phi) * Math.cos(theta),
      center[1] + r * Math.sin(phi) * Math.sin(theta),
      center[2] + r * Math.cos(phi),
    ]
    return { ...seed, position }
  })
}
