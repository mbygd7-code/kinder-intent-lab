/**
 * 결정론 해시·PRNG 계약 고정 — 3D(layout)·2D(brain2dLayout)·파티클이 공유하는 시드 규칙.
 * 값이 바뀌면 저장된 화면 배치가 전부 이동한다 — 알려진 입출력 쌍으로 잠근다.
 */
import { describe, expect, it } from 'vitest'

import { fmix32, fnv1a, mulberry32 } from './hash'

describe('hash 계약 (알려진 입출력 고정)', () => {
  it('fnv1a', () => {
    expect(fnv1a('')).toBe(2166136261) // FNV offset basis
    expect(fnv1a('BN_play_intent_01')).toBe(44368835)
  })

  it('fmix32', () => {
    expect(fmix32(0)).toBe(0)
    expect(fmix32(fnv1a('BN_play_intent_01'))).toBe(2421305400)
  })

  it('mulberry32 — 같은 시드는 같은 스트림', () => {
    const a = mulberry32(42)
    expect(a()).toBeCloseTo(0.6011037519201636, 12)
    expect(a()).toBeCloseTo(0.44829055899754167, 12)
    const b = mulberry32(42)
    expect(b()).toBeCloseTo(0.6011037519201636, 12)
  })

  it('mulberry32 출력은 [0,1) 범위', () => {
    const r = mulberry32(7)
    for (let i = 0; i < 1000; i++) {
      const x = r()
      expect(x).toBeGreaterThanOrEqual(0)
      expect(x).toBeLessThan(1)
    }
  })
})
