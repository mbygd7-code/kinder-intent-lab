/**
 * T3.4 AC — 노드 배치: 결정론 + 위치 인코딩 정직성 (§7-5).
 *
 * 노드 수 = intent 수(~100, §5 노드 정의). AC는 100개 기준이므로 100+로 검증한다.
 * 위치는 3중 인코딩의 한 축 — 노드가 소속 region 구름 안에만 있어야
 * "보이는 위치 = 실제 소속"이 성립한다.
 */
import { describe, expect, it } from 'vitest'

import { layoutNodes } from './layout'
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

  it('위치 정직성: 모든 노드가 소속 region 반경 안에 있다', () => {
    for (const n of layoutNodes(seeds)) {
      const { center, radius } = REGION_BY_ID[n.region]
      const d = Math.hypot(
        n.position[0] - center[0],
        n.position[1] - center[1],
        n.position[2] - center[2],
      )
      expect(d).toBeLessThanOrEqual(radius + 1e-9)
    }
  })

  it('위치 정직성: 모든 노드의 최근접 region 중심 = 소속 region (겹침 없음)', () => {
    for (const n of layoutNodes(seeds)) {
      let nearest = ''
      let best = Infinity
      for (const r of REGIONS) {
        const d = Math.hypot(
          n.position[0] - r.center[0],
          n.position[1] - r.center[1],
          n.position[2] - r.center[2],
        )
        if (d < best) {
          best = d
          nearest = r.id
        }
      }
      expect(nearest).toBe(n.region)
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
