/**
 * 구조 스캐폴드 — 광량 규율: 구조물은 절대 블룸을 타지 않는다 (빛남 = Arena 정확도 전용).
 */
import { describe, expect, it } from 'vitest'

import { BLOOM_THRESHOLD, luma } from './bloom'
import { SHELL_COLOR, SHELL_LINE_INTENSITY } from './StructuralShell'

describe('StructuralShell — 단색 구조물 광량', () => {
  it('그물 선의 유효 광량이 블룸 임계 미만', () => {
    expect(luma(SHELL_COLOR, SHELL_LINE_INTENSITY)).toBeLessThan(BLOOM_THRESHOLD)
  })
})
