/**
 * T3.4 AC — region 7 고정 좌표계 (§5-10) + 3중 인코딩 (§7-5).
 *
 * §5-10: 7개 region은 v1 고정 — 노드가 늘어도 PLAY는 항상 같은 자리.
 * §7-5: 색약 대응 — 색 + region 라벨 + 위치(고정 좌표계)의 3중 인코딩.
 */
import { describe, expect, it } from 'vitest'

import { REGIONS, REGION_BY_ID, type RegionId } from './regions'

// 백엔드 app/core/ontology.py CANONICAL_DOMAINS와 1:1 (순서 포함)
const CANONICAL_DOMAINS: RegionId[] = [
  'PLAY', 'OBSERVATION', 'DOCUMENT', 'VISUAL', 'COMMUNICATION', 'OPERATION', 'REFLECTION',
]

describe('regions — 7 고정 region (§5-10)', () => {
  it('정확히 7개, id·순서가 백엔드 CANONICAL_DOMAINS와 일치한다', () => {
    expect(REGIONS.map((r) => r.id)).toEqual(CANONICAL_DOMAINS)
  })

  it('좌표는 v1 고정 — 값이 바뀌면 의미 좌표계가 깨진다 (스냅샷 잠금)', () => {
    // 임의 변경 금지: region 신설·개편 = 온톨로지 major 버전 (§5-10)
    // [2026-07-09] 사용자 승인 리스타일: 분산 셸 → 해부학적 단일 뇌 내부로 1회 이동
    const centers = Object.fromEntries(REGIONS.map((r) => [r.id, r.center]))
    expect(centers).toEqual({
      PLAY: [0, 0.55, 0.62],
      OBSERVATION: [0, 0.62, -0.42],
      DOCUMENT: [0, -0.08, 0.8],
      VISUAL: [0, 0.12, -0.82],
      COMMUNICATION: [-0.42, -0.1, 0.3],
      OPERATION: [0.42, -0.1, 0.3],
      REFLECTION: [0.0, -0.48, -0.68],
    })
  })

  it('3중 인코딩: 모든 region이 색·라벨·위치를 전부 가진다 (§7-5)', () => {
    for (const r of REGIONS) {
      expect(r.color).toMatch(/^#[0-9a-f]{6}$/i) // ① 색
      expect(r.label.length).toBeGreaterThan(0) //  ② 라벨
      expect(r.center).toHaveLength(3) //           ③ 고정 좌표
      expect(r.radius).toBeGreaterThan(0)
    }
  })

  it('색과 라벨은 region 간 중복 없다 (인코딩 구분성)', () => {
    const colors = REGIONS.map((r) => r.color.toLowerCase())
    const labels = REGIONS.map((r) => r.label)
    expect(new Set(colors).size).toBe(7)
    expect(new Set(labels).size).toBe(7)
  })

  it('위치 인코딩 정직성: 산포 반경이 region 간 최소 중심거리의 절반 미만 — 구름이 겹치지 않는다', () => {
    let minPair = Infinity
    for (let i = 0; i < REGIONS.length; i++) {
      for (let j = i + 1; j < REGIONS.length; j++) {
        const [ax, ay, az] = REGIONS[i].center
        const [bx, by, bz] = REGIONS[j].center
        minPair = Math.min(minPair, Math.hypot(ax - bx, ay - by, az - bz))
      }
    }
    for (const r of REGIONS) expect(r.radius).toBeLessThan(minPair / 2)
  })

  it('REGION_BY_ID 인덱스가 REGIONS와 일치한다', () => {
    for (const r of REGIONS) expect(REGION_BY_ID[r.id]).toBe(r)
  })
})
