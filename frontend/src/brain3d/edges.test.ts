/**
 * 혼동 edge 인코더 — §7-5 Thickness/Flicker 바인딩 + 정직성.
 *
 * 핵심: 점선 ⟺ rate 미측정, flicker 0 ⟺ 미측정·rate 0(소등), 두께는 state 단조,
 * focus 필터 = 확정 ∪ 측정 ∪ 선택 인접, 미배치 intent는 스킵(허공 지오메트리 금지).
 */
import { describe, expect, it } from 'vitest'

import type { GlobalConfusionEdge } from '../api/observatory'
import {
  buildEdgeCurves,
  EDGE_WIDTH,
  edgeInfo,
  edgeVisual,
  samplePolyline,
  visibleEdges,
} from './edges'

function edge(over: Partial<GlobalConfusionEdge>): GlobalConfusionEdge {
  return {
    edge_id: 'CE_x',
    from_intent: 'a',
    to_intent: 'b',
    confusion_rate: null,
    state: 'hypothesized',
    origin: 'SKEPTIC',
    ...over,
  }
}

describe('edgeVisual — §7-5 바인딩', () => {
  it('점선 ⟺ rate 미측정 (가설을 실측처럼 그리지 않는다)', () => {
    expect(edgeVisual(edge({ confusion_rate: null })).dashed).toBe(true)
    expect(edgeVisual(edge({ confusion_rate: 0.3, state: 'confirmed' })).dashed).toBe(false)
    expect(edgeVisual(edge({ confusion_rate: 0 })).dashed).toBe(false) // 측정된 0은 실선
  })

  it('flicker: 미측정·rate 0 → 0(소등), rate에 단조 증가', () => {
    expect(edgeVisual(edge({ confusion_rate: null })).flickerHz).toBe(0)
    expect(edgeVisual(edge({ confusion_rate: 0 })).flickerHz).toBe(0)
    const low = edgeVisual(edge({ confusion_rate: 0.1 })).flickerHz
    const high = edgeVisual(edge({ confusion_rate: 0.9 })).flickerHz
    expect(low).toBeGreaterThan(0)
    expect(high).toBeGreaterThan(low)
  })

  it('두께: hypothesized < observed < confirmed (state 사다리 단조)', () => {
    expect(EDGE_WIDTH.hypothesized).toBeLessThan(EDGE_WIDTH.observed)
    expect(EDGE_WIDTH.observed).toBeLessThan(EDGE_WIDTH.confirmed)
    expect(edgeVisual(edge({ state: 'confirmed' })).width).toBe(EDGE_WIDTH.confirmed)
  })

  it('색: 측정 = amber, 미측정 = slate (그라디언트 from ≠ to — 방향 표현)', () => {
    const m = edgeVisual(edge({ confusion_rate: 0.4 }))
    const u = edgeVisual(edge({ confusion_rate: null }))
    expect(m.colorTo).not.toBe(u.colorTo)
    expect(m.colorFrom).not.toBe(m.colorTo)
  })
})

describe('visibleEdges — focus/all 필터 (§5-6 UX 결정)', () => {
  const edges = [
    edge({ edge_id: 'E_hyp', from_intent: 'a', to_intent: 'b' }),
    edge({ edge_id: 'E_conf', from_intent: 'c', to_intent: 'd', state: 'confirmed' }),
    edge({ edge_id: 'E_meas', from_intent: 'e', to_intent: 'f', confusion_rate: 0.2 }),
    edge({ edge_id: 'E_sel', from_intent: 'g', to_intent: 'a' }),
  ]

  it('all = 전체', () => {
    expect(visibleEdges(edges, 'all', null)).toHaveLength(4)
  })

  it('focus 미선택 = 확정 + 측정만 (가설 소음 제거)', () => {
    const ids = visibleEdges(edges, 'focus', null).map((e) => e.edge_id)
    expect(ids.sort()).toEqual(['E_conf', 'E_meas'])
  })

  it('focus + 선택 = 확정 + 측정 + 선택 인접(방향 불문)', () => {
    const ids = visibleEdges(edges, 'focus', 'a').map((e) => e.edge_id)
    expect(ids.sort()).toEqual(['E_conf', 'E_hyp', 'E_meas', 'E_sel'])
  })
})

describe('edgeInfo — 연결 사유 텍스트 (§5-6 필드만, 날조 없음)', () => {
  it('방향: from=선택 → 유출 문구, to=선택 → 유입 문구', () => {
    const e = edge({ from_intent: 'sel', to_intent: 'other' })
    expect(edgeInfo(e, 'sel').direction).toContain('착각할 수 있음')
    expect(edgeInfo(e, 'other').direction).toContain('착각되어 들어옴')
  })

  it('사유: 상태 한글 + 출처 한글 (미지 출처는 원문 그대로 — 날조 없음)', () => {
    const skeptic = edgeInfo(edge({ origin: 'SKEPTIC' }), 'a')
    expect(skeptic.reason).toContain('추측')
    expect(skeptic.reason).toContain('헷갈릴 수 있다고 짚음')
    const arena = edgeInfo(
      edge({ state: 'confirmed', origin: 'ARENA_MATRIX', confusion_rate: 0.3 }),
      'a',
    )
    expect(arena.reason).toContain('확인됨')
    expect(arena.reason).toContain('시험에서 실제로 틀림')
    expect(edgeInfo(edge({ origin: 'FUTURE_SOURCE' }), 'a').reason).toContain('FUTURE_SOURCE')
  })

  it('측정치: rate null → "측정 전"(0% 아님), 측정되면 %', () => {
    expect(edgeInfo(edge({ confusion_rate: null }), 'a')).toMatchObject({
      rate: '시험 전',
      measured: false,
    })
    expect(edgeInfo(edge({ confusion_rate: 0.42 }), 'a')).toMatchObject({
      rate: '헷갈린 비율 42%',
      measured: true,
    })
  })
})

describe('samplePolyline — 전파 펄스 경로 (방향 = from→to)', () => {
  const line: Array<readonly [number, number, number]> = [
    [0, 0, 0],
    [1, 0, 0],
    [2, 0, 0],
  ]

  it('t=0 → 시작점(from), t=1 → 끝점(to) — 펄스가 혼동 방향을 따른다', () => {
    expect(samplePolyline(line, 0)).toEqual([0, 0, 0])
    const end = samplePolyline(line, 1)
    expect(end[0]).toBeCloseTo(2, 3)
  })

  it('중간 t는 선형 보간, 범위 밖 t는 클램프', () => {
    expect(samplePolyline(line, 0.25)).toEqual([0.5, 0, 0])
    expect(samplePolyline(line, 0.75)).toEqual([1.5, 0, 0])
    expect(samplePolyline(line, -1)).toEqual([0, 0, 0])
    expect(samplePolyline(line, 2)[0]).toBeCloseTo(2, 3)
  })
})

describe('buildEdgeCurves — 곡선·스킵', () => {
  const pos = new Map<string, readonly [number, number, number]>([
    ['a', [0, 0.55, 0.62]],
    ['b', [0, 0.62, -0.42]],
  ])

  it('미배치 intent의 edge는 스킵 + 카운트 (허공 지오메트리 금지)', () => {
    const { curves, skipped } = buildEdgeCurves(
      [edge({}), edge({ edge_id: 'CE_ghost', from_intent: 'a', to_intent: 'NOPE' })],
      pos,
      null,
    )
    expect(curves).toHaveLength(1)
    expect(skipped).toBe(1)
  })

  it('곡선은 13점, 양 끝 = 노드 위치, 결정론', () => {
    const one = buildEdgeCurves([edge({})], pos, null).curves[0]
    const two = buildEdgeCurves([edge({})], pos, null).curves[0]
    expect(one.points).toHaveLength(13)
    expect(one.points[0]).toEqual(pos.get('a'))
    expect(one.points[12]).toEqual(pos.get('b'))
    expect(one.points).toEqual(two.points)
    // 리프트: 중간점이 직선 중점과 다르다 (뇌 관통 방지)
    const mid = one.points[6]
    const straight = [0, (0.55 + 0.62) / 2, (0.62 - 0.42) / 2]
    expect(Math.hypot(mid[0] - straight[0], mid[1] - straight[1], mid[2] - straight[2]))
      .toBeGreaterThan(0.01)
  })

  it('touchesSelected — 선택 인접 edge 플래그(강조 버킷 분리)', () => {
    const { curves } = buildEdgeCurves([edge({})], pos, 'a')
    expect(curves[0].touchesSelected).toBe(true)
    expect(buildEdgeCurves([edge({})], pos, 'zzz').curves[0].touchesSelected).toBe(false)
  })
})
