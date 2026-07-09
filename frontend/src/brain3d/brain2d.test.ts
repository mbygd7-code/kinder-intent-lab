/**
 * 2D fallback 레이아웃 불변식 (§5-10 준용 + §7-5 3중 인코딩의 위치 축).
 *
 * 저사양 사용자에게 2D map은 유일한 뷰다 — 3D 좌표(regions.test.ts)와 동일하게
 * 고정 좌표를 스냅샷으로 잠그고, 원 비겹침·점 포함(위치 정직성)을 기하로 보장한다.
 */
import { describe, expect, it } from 'vitest'

import { dot2d, DOT_R, DOT_R_SELECTED, POS_2D, REGION_R } from './brain2dLayout'
import { makeMockNodes } from './mockNodes'
import { REGIONS, type RegionId } from './regions'

describe('POS_2D — 2D 고정 의미 좌표 (§5-10 준용)', () => {
  it('좌표는 고정 — 값이 바뀌면 2D 사용자에게 region 위치 앵커가 깨진다 (스냅샷 잠금)', () => {
    // [2026-07-09] 사용자 승인 리스타일: 3D 해부학 배치(전두=왼쪽)와 방향 일치하도록 1회 이동
    expect(POS_2D).toEqual({
      PLAY: [-0.62, -0.55],
      OBSERVATION: [0.42, -0.62],
      DOCUMENT: [-0.85, 0.1],
      VISUAL: [0.85, -0.05],
      COMMUNICATION: [-0.28, 0.28],
      OPERATION: [0.3, 0.42],
      REFLECTION: [0.72, 0.85],
    })
  })

  it('7개 region 전부 커버', () => {
    expect(Object.keys(POS_2D).sort()).toEqual(REGIONS.map((r) => r.id).sort())
  })

  it('region 원 비겹침: 모든 쌍의 중심거리 ≥ 2×REGION_R', () => {
    const entries = Object.entries(POS_2D)
    for (let i = 0; i < entries.length; i++) {
      for (let j = i + 1; j < entries.length; j++) {
        const [, [ax, ay]] = entries[i]
        const [, [bx, by]] = entries[j]
        expect(Math.hypot(ax - bx, ay - by)).toBeGreaterThanOrEqual(2 * REGION_R)
      }
    }
  })

  it('점 포함 보장: 산포 반경 + 최대 점 반지름이 region 원 안에 든다', () => {
    // dot2d 최대 이탈 = DOT_SPREAD + 점 반지름(선택 시 + stroke 0.006/2)
    const maxDot = Math.max(DOT_R, DOT_R_SELECTED + 0.003)
    expect(0.2 + maxDot).toBeLessThanOrEqual(REGION_R)
  })
})

describe('dot2d — 결정론 + 위치 정직성', () => {
  const seeds = makeMockNodes()

  it('결정론: 같은 nodeId → 같은 2D 좌표', () => {
    for (const s of seeds.slice(0, 10)) {
      expect(dot2d(s.nodeId, s.region)).toEqual(dot2d(s.nodeId, s.region))
    }
  })

  it('105개 전 노드의 점이 소속 region 원 안에 있다', () => {
    for (const s of seeds) {
      const [x, y] = dot2d(s.nodeId, s.region)
      const [cx, cy] = POS_2D[s.region as RegionId]
      expect(Math.hypot(x - cx, y - cy)).toBeLessThanOrEqual(REGION_R - DOT_R)
    }
  })
})
