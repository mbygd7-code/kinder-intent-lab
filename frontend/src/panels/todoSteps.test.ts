/**
 * TODO 엔진 AC — 파이프라인 순서 판정(첫 미완료 = 지금 할 일), 실측 수치 표기, 목표 도달.
 */
import { describe, expect, it } from 'vitest'

import { computeTodoSteps, type TodoInputs } from './todoSteps'

const BASE: TodoInputs = {
  examTotal: 0, frozen: false, reviewableTotal: 0, readyTotal: 0, goldTotal: 0,
  exemplarTotal: 0, runCount: 0, score: null, target: 0.96,
}

const cur = (i: TodoInputs) => computeTodoSteps(i).find((s) => s.state === 'current')?.key

describe('computeTodoSteps', () => {
  it('시험지가 없으면 1단계(시험지)가 지금 할 일 — 뒤 단계는 잠김', () => {
    const steps = computeTodoSteps(BASE)
    expect(cur(BASE)).toBe('exam')
    expect(steps.map((s) => s.state)).toEqual(['current', 'locked', 'locked', 'locked', 'locked'])
  })

  it('시험지 동결 + 재료 없음 → 재료 모으기', () => {
    expect(cur({ ...BASE, examTotal: 386, frozen: true })).toBe('material')
  })

  it('검수 대기가 쌓이면 → 공부 검수(GOLD)가 지금 할 일 (현재 상태)', () => {
    const i = { ...BASE, examTotal: 386, frozen: true, reviewableTotal: 91, readyTotal: 0 }
    const steps = computeTodoSteps(i)
    expect(cur(i)).toBe('review')
    const review = steps.find((s) => s.key === 'review')!
    expect(review.detail).toContain('대기 91건')
    expect(review.why).toContain('채점 버튼이 켜져요') // 뭘 하면 뭐가 좋아지는지
  })

  it('GOLD·대표 예문이 생기면 → 채점 실행', () => {
    expect(cur({
      ...BASE, examTotal: 386, frozen: true, reviewableTotal: 30,
      goldTotal: 60, exemplarTotal: 55,
    })).toBe('arena')
  })

  it('첫 유효 점수가 나오면 → 반복 상승 단계 (0% 채점은 완료로 안 침)', () => {
    const gotScore = {
      ...BASE, examTotal: 386, frozen: true, reviewableTotal: 5,
      goldTotal: 60, exemplarTotal: 55, runCount: 3, score: 0.62,
    }
    expect(cur(gotScore)).toBe('improve')
    // 채점은 했지만 0%면(대표 예문 이전의 헛채점) 여전히 채점 단계 — 완료를 지어내지 않는다
    expect(cur({ ...gotScore, score: 0, runCount: 2 })).toBe('arena')
  })

  it('목표 도달이면 전 단계 done — current 없음', () => {
    const done = {
      ...BASE, examTotal: 386, frozen: true, reviewableTotal: 5,
      goldTotal: 300, exemplarTotal: 200, runCount: 9, score: 0.97,
    }
    const steps = computeTodoSteps(done)
    expect(steps.every((s) => s.state === 'done')).toBe(true)
    expect(cur(done)).toBeUndefined()
  })
})
