/**
 * T5.4 AC — Persona Overlay 마크 계산 (§7-6·§5-5).
 *
 * 핵심 정직성: prior "부재"는 중립이지 낮은 prior가 아니다 — 마크 없음(strength 0),
 * 어둡게 그릴 근거가 없다. 그리고 이 모듈의 출력엔 §7-5 밝기 채널에 관한 어떤 값도 없다
 * (부가 채널 — 절대 규칙 3은 encodings.test의 소스 스캔이 이 파일에도 강제한다).
 */
import { describe, expect, it } from 'vitest'

import { markFromPrior, NEUTRAL_MARK, NEUTRAL_PRIOR } from './personaOverlay'

describe('markFromPrior — §5-5 prior → 오버레이 마크', () => {
  it('prior 부재(undefined/null) → 중립 마크(표시 없음) — 낮은 prior가 아니다', () => {
    expect(markFromPrior(undefined)).toEqual(NEUTRAL_MARK)
    expect(markFromPrior(null)).toEqual(NEUTRAL_MARK)
    expect(markFromPrior(undefined).strength).toBe(0)
  })

  it('중립값 0.5 → 마크 없음 (강조 없음)', () => {
    expect(markFromPrior(NEUTRAL_PRIOR)).toEqual(NEUTRAL_MARK)
  })

  it('prior > 0.5 → boost 마크, 0.5에서 멀수록 강함', () => {
    const mild = markFromPrior(0.6)
    const strong = markFromPrior(0.9)
    expect(mild.boost).toBe(true)
    expect(strong.boost).toBe(true)
    expect(strong.strength).toBeGreaterThan(mild.strength)
    expect(strong.strength).toBeCloseTo(0.8)
  })

  it('prior < 0.5 → 억제 마크(boost=false)', () => {
    const damp = markFromPrior(0.1)
    expect(damp.boost).toBe(false)
    expect(damp.strength).toBeCloseTo(0.8)
  })

  it('범위 밖·비수치 입력도 안전: strength는 [0,1] 클램프, NaN은 중립', () => {
    expect(markFromPrior(5).strength).toBe(1)
    expect(markFromPrior(-3).strength).toBe(1)
    expect(markFromPrior(Number.NaN)).toEqual(NEUTRAL_MARK)
  })

  it('마크 출력엔 strength·boost뿐 — 밝기(§7-5) 채널로 새는 필드가 없다 (절대 규칙 3)', () => {
    expect(Object.keys(markFromPrior(0.9)).sort()).toEqual(['boost', 'strength'])
  })
})
