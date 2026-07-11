/**
 * 상태 인코더 — 미측정 = 부재(0이 아님), Arena 값에 단조.
 */
import { describe, expect, it } from 'vitest'

import { ktibArc, litRings, regionGlow, STAGE_RING_RADII } from './statusEncodings'

describe('litRings — 성장 스테이지 링 (§7-6)', () => {
  it('null·Stage 0 → 전부 소등', () => {
    expect(litRings(null)).toEqual([false, false, false, false, false])
    expect(litRings(0)).toEqual([false, false, false, false, false])
  })

  it('Stage 3 → 앞 3개 점등, Stage 5 → 전부 점등', () => {
    expect(litRings(3)).toEqual([true, true, true, false, false])
    expect(litRings(5)).toEqual([true, true, true, true, true])
  })

  it('링 5개 = Stage 1~5, 반지름 단조 증가', () => {
    expect(STAGE_RING_RADII).toHaveLength(5)
    for (let i = 1; i < STAGE_RING_RADII.length; i++) {
      expect(STAGE_RING_RADII[i]).toBeGreaterThan(STAGE_RING_RADII[i - 1])
    }
  })
})

describe('ktibArc — KTIB 호 게이지 (§7-1)', () => {
  it('null(미측정) → 호 없음 (0%가 아니다)', () => {
    expect(ktibArc(null)).toBeNull()
  })

  it('측정값 → 호 길이 = 비율 × 2π', () => {
    expect(ktibArc(0.618)!.thetaLength).toBeCloseTo(0.618 * Math.PI * 2)
    expect(ktibArc(0)!.thetaLength).toBe(0) // 측정된 0은 "호 길이 0" — null과 다르다
    expect(ktibArc(1.7)!.thetaLength).toBeCloseTo(Math.PI * 2) // 클램프
  })
})

describe('regionGlow — reliability 광 (Arena 파생)', () => {
  it('null → 무광(부재), 측정값에 단조', () => {
    expect(regionGlow(null)).toBeNull()
    expect(regionGlow(0.9)!.intensity).toBeGreaterThan(regionGlow(0.3)!.intensity)
    expect(regionGlow(1.5)!.intensity).toBe(1) // 클램프
  })
})
