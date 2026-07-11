/**
 * 노드 배치 v2 — nodeId 해시 시드 결정론 + 실제 뇌 볼륨 안 배치.
 *
 * 위치는 §7-5 3중 인코딩의 한 축: 노드는 소속 region 구름(중심+반경) ∩ 뇌 내부에만
 * 놓여 "보이는 위치 = 실제 소속"이 성립하고, evidence 파티클·구조 쉘과 같은 공간
 * (뇌 형태)에 자연스럽게 안착한다. region 구름은 서로 겹치지 않게 설계돼(중심 간
 * 최소 0.616 ≥ 2×반경) 구름 안이면 Voronoi 소속도 자동 성립 — 그래도 벨트앤서스펜더로
 * nearestRegion을 재확인한다.
 *
 * 알고리즘: nodeId 정렬 순회(입력 순서 무관 결정론) → 노드당 후보 K개(구 내 부피 균등,
 * rng 소비량 고정) → insideBrain ∧ 자기 Voronoi 필터 → 기배치 동일 region 노드와의
 * 최소거리를 최대화하는 후보 선택(blue-noise 근사). 후보 전멸 시 region 중심 인근 폴백
 * (전 region 중심의 insideBrain은 layout.test.ts가 보증).
 *
 * 트레이드오프(의도된 것): 노드 추가(거버넌스 이벤트, 드묾) 시 같은 region의 정렬
 * 후순위 노드가 자기 후보 K개 안에서 이동할 수 있다. 같은 입력 → 같은 출력은 항상
 * 성립한다. 배치는 nodeId·region에만 의존 — 가변 지표(evidence 등)는 절대 쓰지
 * 않는다(훈련이 노드를 움직이면 위치 인코딩의 정직성이 깨진다).
 */
import { insideBrain, nearestRegion } from './brainShape'
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

/** 같은 region 노드 간 기대 최소 간격 — 표현 상수(실험 임계값 아님, 테스트 하한). */
export const MIN_SEP = 0.04
/** 노드당 후보 수 — 클수록 간격 품질↑, 결정론 비용은 상수. */
const CANDIDATES = 12

function dist2(a: readonly number[], b: readonly number[]): number {
  const dx = a[0] - b[0]
  const dy = a[1] - b[1]
  const dz = a[2] - b[2]
  return dx * dx + dy * dy + dz * dz
}

export function layoutNodes(seeds: NodeSeed[]): PlacedNode[] {
  // 결정론: 입력 순서와 무관하게 nodeId 정렬 순서로 배치한다 (출력은 입력 순서 유지)
  const order = seeds
    .map((_, i) => i)
    .sort((a, b) => (seeds[a].nodeId < seeds[b].nodeId ? -1 : 1))

  const placedByRegion = new Map<RegionId, Array<readonly [number, number, number]>>()
  const out: PlacedNode[] = new Array(seeds.length)

  for (const idx of order) {
    const seed = seeds[idx]
    const { center, radius } = REGION_BY_ID[seed.region]
    const rng = mulberry32(fmix32(fnv1a(seed.nodeId)))

    // 후보 K개를 항상 전부 생성 — rng 소비량이 고정이라 유효성과 무관하게 결정론
    const candidates: Array<readonly [number, number, number]> = []
    for (let k = 0; k < CANDIDATES; k++) {
      const theta = 2 * Math.PI * rng()
      const phi = Math.acos(2 * rng() - 1)
      const r = radius * Math.cbrt(rng())
      const p: readonly [number, number, number] = [
        center[0] + r * Math.sin(phi) * Math.cos(theta),
        center[1] + r * Math.sin(phi) * Math.sin(theta),
        center[2] + r * Math.cos(phi),
      ]
      if (insideBrain(p) && nearestRegion(p) === seed.region) candidates.push(p)
    }

    const same = placedByRegion.get(seed.region) ?? []
    let position: readonly [number, number, number]
    if (candidates.length === 0) {
      // 폴백: region 중심 인근(중심은 전 region에서 뇌 내부 — 테스트 보증)
      position = [
        center[0] + 0.05 * (rng() - 0.5),
        center[1] + 0.05 * (rng() - 0.5),
        center[2] + 0.05 * (rng() - 0.5),
      ]
    } else if (same.length === 0) {
      position = candidates[0] // 첫 유효 후보 — 이웃이 없으면 간격 기준이 없다
    } else {
      // blue-noise 근사: 기배치 이웃과의 최소거리를 최대화
      let best = candidates[0]
      let bestScore = -Infinity
      for (const p of candidates) {
        let minD = Infinity
        for (const q of same) minD = Math.min(minD, dist2(p, q))
        if (minD > bestScore) {
          bestScore = minD
          best = p
        }
      }
      position = best
    }

    same.push(position)
    placedByRegion.set(seed.region, same)
    out[idx] = { ...seed, position }
  }
  return out
}
