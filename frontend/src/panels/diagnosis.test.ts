/**
 * T3.6 §7-3 진단 엔진 — 이 단계는 계산값 **mock**(티켓 AC). 결정론·정직성만 검증한다:
 * 같은 노드는 항상 같은 mock을 내고, Gold Data 축은 mock이 아니라 실 gold_count에서 나온다.
 */
import { describe, expect, it } from 'vitest'

import { goldDataLevel, mockDiagnosis } from './diagnosis'

const INTENTS = ['a_x', 'b_y', 'c_z', 'd_w', 'e_v']

describe('mockDiagnosis (§7-3 미리보기)', () => {
  it('결정론: 같은 nodeId → 같은 혼동·WHY-WEAK', () => {
    expect(mockDiagnosis('N_a_x', INTENTS)).toEqual(mockDiagnosis('N_a_x', INTENTS))
  })

  it('방향성 혼동은 자기 자신을 가리키지 않고, rate 내림차순', () => {
    const d = mockDiagnosis('N_a_x', INTENTS)
    expect(d.confusions.length).toBeGreaterThanOrEqual(1)
    for (const c of d.confusions) {
      expect(c.intentId).not.toBe('a_x')
      expect(INTENTS).toContain(c.intentId)
      expect(c.rate).toBeGreaterThan(0)
      expect(c.rate).toBeLessThanOrEqual(1)
    }
    const rates = d.confusions.map((c) => c.rate)
    expect(rates).toEqual([...rates].sort((x, y) => y - x))
  })

  it('WHY-WEAK 3축은 HIGH/MED/LOW 중 하나 (Gold Data는 여기서 안 만든다)', () => {
    const w = mockDiagnosis('N_a_x', INTENTS).why
    for (const lvl of [w.ambiguousLanguage, w.screenContextCoverage, w.personaDiversity]) {
      expect(['HIGH', 'MED', 'LOW']).toContain(lvl)
    }
    expect(w).not.toHaveProperty('goldData') // Gold Data는 실데이터 소관
  })

  it('후보가 1개(자기뿐)면 혼동 목록은 비어도 된다 (지어내지 않음)', () => {
    const d = mockDiagnosis('N_a_x', ['a_x'])
    expect(d.confusions).toEqual([])
  })
})

describe('goldDataLevel — 실 gold_count 기반 (mock 아님, §7-3 Gold Data 축)', () => {
  it('절대량 임계로 LOW/MED/HIGH', () => {
    expect(goldDataLevel(0)).toBe('LOW')
    expect(goldDataLevel(2)).toBe('LOW')
    expect(goldDataLevel(5)).toBe('MED')
    expect(goldDataLevel(50)).toBe('HIGH')
  })
})
