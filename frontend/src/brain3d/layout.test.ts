/**
 * T3.4 AC + 배치 v2 — 노드 배치: 결정론 + 위치 인코딩 정직성 (§7-5).
 *
 * 노드 수 = intent 수(~100, §5 노드 정의). AC는 100개 기준이므로 100+로 검증한다.
 * v2: 노드는 소속 region 구름 ∩ 뇌 내부(insideBrain)에 놓여 파티클·쉘과 같은
 * 공간에 안착하고, 같은 region 안에서 blue-noise 간격을 가진다.
 */
import { describe, expect, it } from 'vitest'

import { insideBrain, nearestRegion } from './brainShape'
import { layoutNodes, MIN_SEP } from './layout'
import { makeMockNodes } from './mockNodes'
import { REGIONS, REGION_BY_ID } from './regions'

const seeds = makeMockNodes() // 7 region × 15 = 105 ≥ 100 (AC 기준)

describe('layoutNodes — 결정론적 배치', () => {
  it('AC: 100개 이상 노드가 전부 배치된다 (유실·중복 없음)', () => {
    const placed = layoutNodes(seeds)
    expect(seeds.length).toBeGreaterThanOrEqual(100)
    expect(placed).toHaveLength(seeds.length)
    expect(new Set(placed.map((n) => n.nodeId)).size).toBe(seeds.length)
  })

  it('결정론: 같은 입력 → 같은 좌표 (재렌더·리로드에 좌표가 흔들리지 않는다)', () => {
    const a = layoutNodes(seeds)
    const b = layoutNodes(seeds)
    expect(a).toEqual(b)
  })

  it('입력 순서 무관: 뒤섞어 넣어도 nodeId별 좌표는 동일 (nodeId 정렬 순회)', () => {
    const byId = new Map(layoutNodes(seeds).map((n) => [n.nodeId, n.position]))
    const shuffled = [...seeds].reverse()
    for (const n of layoutNodes(shuffled)) {
      expect(n.position).toEqual(byId.get(n.nodeId))
    }
  })

  it('위치 정직성: 모든 노드가 소속 region 반경 안 + 뇌 내부 + 자기 Voronoi 셀', () => {
    for (const n of layoutNodes(seeds)) {
      const { center, radius } = REGION_BY_ID[n.region]
      const d = Math.hypot(
        n.position[0] - center[0],
        n.position[1] - center[1],
        n.position[2] - center[2],
      )
      expect(d).toBeLessThanOrEqual(radius + 1e-9)
      expect(insideBrain(n.position), `${n.nodeId} 뇌 밖`).toBe(true)
      expect(nearestRegion(n.position)).toBe(n.region)
    }
  })

  it('폴백 안전성: 전 region 중심이 뇌 내부 + 자기 Voronoi (전멸 시 착지 지점)', () => {
    for (const r of REGIONS) {
      expect(insideBrain(r.center), `${r.id} 중심이 뇌 밖`).toBe(true)
      expect(nearestRegion(r.center)).toBe(r.id)
    }
  })

  it('blue-noise: 같은 region 노드 간 최소 간격 ≥ MIN_SEP', () => {
    const placed = layoutNodes(seeds)
    for (const r of REGIONS) {
      const group = placed.filter((n) => n.region === r.id)
      for (let i = 0; i < group.length; i++) {
        for (let j = i + 1; j < group.length; j++) {
          const d = Math.hypot(
            group[i].position[0] - group[j].position[0],
            group[i].position[1] - group[j].position[1],
            group[i].position[2] - group[j].position[2],
          )
          expect(d, `${group[i].nodeId} ↔ ${group[j].nodeId}`).toBeGreaterThanOrEqual(MIN_SEP)
        }
      }
    }
  })

  it('같은 region 내 노드끼리도 서로 다른 위치를 가진다', () => {
    const placed = layoutNodes(seeds)
    const keys = new Set(placed.map((n) => n.position.join(',')))
    expect(keys.size).toBe(placed.length)
  })
})

describe('makeMockNodes — Observatory API 전까지의 임시 데이터', () => {
  it('7개 region 전부를 커버한다', () => {
    const covered = new Set(seeds.map((s) => s.region))
    expect(covered.size).toBe(7)
  })

  it('nodeId는 전역 유일하다', () => {
    expect(new Set(seeds.map((s) => s.nodeId)).size).toBe(seeds.length)
  })
})
