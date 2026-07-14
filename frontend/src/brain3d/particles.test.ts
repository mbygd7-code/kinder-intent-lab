/**
 * Evidence 파티클 — "입자 = 실데이터" 불변식.
 *
 * 핵심: ① evidence 0 → 입자 0 (미학습 = 무입자, 정직) ② 예산 상한 ③ 훈련량 단조
 * ④ 결정론 ⑤ 공간 정직성(뇌 내부 ∩ 자기 Voronoi) ⑥ 광량 규율 — 어떤 입자 색도
 * 블룸 임계를 넘지 않는다(빛남 = Arena 정확도 전용, §7-5).
 */
import { describe, expect, it } from 'vitest'

import { BLOOM_THRESHOLD, luma } from './bloom'
import { insideBrain, nearestRegion } from './brainShape'
import { layoutNodes } from './layout'
import { makeMockNodes } from './mockNodes'
import {
  allocateParticles,
  BASE_INTENSITY,
  buildEvidenceClouds,
  buildShellField,
  cloudsSignature,
  DUST_COUNT,
  EVIDENCE_BUDGET,
  HOVER_BOOST,
  PARTICLE_MAX,
  PARTICLE_MIN,
  regionEnergies,
  shellSignature,
  SPARK_COLOR,
  SPARK_INTENSITY,
  type ParticleMetrics,
} from './particles'
import { REGIONS, type RegionId } from './regions'

const placed = layoutNodes(makeMockNodes()) // 105 노드

function metricsFor(
  fn: (i: number) => Partial<ParticleMetrics>,
): Map<string, ParticleMetrics> {
  return new Map(
    placed.map((n, i) => [
      n.nodeId,
      {
        evidence_total: 0,
        evidence_diversity: 0,
        gold_count: 0,
        expert_count: 0,
        ...fn(i),
      },
    ]),
  )
}

describe('allocateParticles — 예산 배분', () => {
  it('evidence 0 노드는 배정 자체가 없다 (미학습 = 무입자)', () => {
    const alloc = allocateParticles([
      { nodeId: 'a', total: 0, goldExpert: 0 },
      { nodeId: 'b', total: 10, goldExpert: 0 },
    ])
    expect(alloc.has('a')).toBe(false)
    expect(alloc.get('b')!.count).toBeGreaterThan(0)
  })

  it('총 배정 ≤ 예산, 노드당 [MIN, MAX] 클램프', () => {
    const inputs = placed.map((n, i) => ({
      nodeId: n.nodeId,
      total: 1 + i * 37, // 1 ~ 3849 광범위
      goldExpert: 0,
    }))
    const alloc = allocateParticles(inputs)
    const sum = [...alloc.values()].reduce((s, v) => s + v.count, 0)
    expect(sum).toBeLessThanOrEqual(EVIDENCE_BUDGET)
    for (const { count } of alloc.values()) {
      expect(count).toBeGreaterThanOrEqual(PARTICLE_MIN)
      expect(count).toBeLessThanOrEqual(PARTICLE_MAX)
    }
  })

  it('훈련량 단조: total이 크면 배정도 크다 (클램프에 안 걸리는 예산에서)', () => {
    const alloc = allocateParticles(
      [
        { nodeId: 'small', total: 20, goldExpert: 0 },
        { nodeId: 'big', total: 2000, goldExpert: 0 },
      ],
      100, // 둘 다 [MIN, MAX] 안에 들어오는 예산 — 기본 예산이면 둘 다 MAX로 동률
    )
    expect(alloc.get('big')!.count).toBeGreaterThan(alloc.get('small')!.count)
  })

  it('스파크 = min(gold+expert, 배정) — 예산 불변 치환', () => {
    const alloc = allocateParticles([{ nodeId: 'g', total: 50, goldExpert: 9999 }])
    const a = alloc.get('g')!
    expect(a.sparks).toBe(a.count) // 전부 스파크로 치환돼도 개수 자체는 그대로
  })

  it('입력 순서 무관 결정론', () => {
    const inputs = placed.map((n, i) => ({ nodeId: n.nodeId, total: 5 + i, goldExpert: i % 3 }))
    const a = allocateParticles(inputs)
    const b = allocateParticles([...inputs].reverse())
    expect([...a.entries()].sort()).toEqual([...b.entries()].sort())
  })
})

describe('buildEvidenceClouds — 공간·색 정직성', () => {
  const metrics = metricsFor((i) => ({
    evidence_total: i % 4 === 0 ? 0 : 10 + i * 3, // 1/4은 무학습
    evidence_diversity: (i % 10) / 10,
    gold_count: i % 5,
    expert_count: i % 2,
  }))

  it('결정론: 같은 입력 → 같은 버퍼', () => {
    const a = buildEvidenceClouds(placed, metrics)
    const b = buildEvidenceClouds(placed, metrics)
    expect(a.basePositions).toEqual(b.basePositions)
    expect(a.sparkPositions).toEqual(b.sparkPositions)
    expect(a.baseColors).toEqual(b.baseColors)
  })

  it('evidence 0 노드는 perNode에 없다 · 총량 ≤ 예산', () => {
    const clouds = buildEvidenceClouds(placed, metrics)
    for (const [i, n] of placed.entries()) {
      if (i % 4 === 0) expect(clouds.perNode.has(n.nodeId)).toBe(false)
    }
    const total = [...clouds.perNode.values()].reduce((s, v) => s + v.count, 0)
    expect(total).toBeLessThanOrEqual(EVIDENCE_BUDGET)
    expect((clouds.basePositions.length + clouds.sparkPositions.length) / 3).toBe(total)
  })

  it('모든 입자가 뇌 내부 ∩ 유효 region Voronoi 셀에 있다', () => {
    const clouds = buildEvidenceClouds(placed, metrics)
    const regionIds = new Set(REGIONS.map((r) => r.id))
    for (const arr of [clouds.basePositions, clouds.sparkPositions]) {
      for (let i = 0; i < arr.length; i += 3) {
        const p = [arr[i], arr[i + 1], arr[i + 2]] as const
        expect(insideBrain(p)).toBe(true)
        expect(regionIds.has(nearestRegion(p))).toBe(true)
      }
    }
  })

  it('광량 규율: 전 region 색·스파크 색의 luma < BLOOM_THRESHOLD (지터 상한 포함)', () => {
    for (const r of REGIONS) {
      expect(luma(r.color, BASE_INTENSITY * 1.1), r.id).toBeLessThan(BLOOM_THRESHOLD)
    }
    expect(luma(SPARK_COLOR, SPARK_INTENSITY)).toBeLessThan(BLOOM_THRESHOLD)
  })

  it('렌더된 색 버퍼의 실제 luma도 임계 미만이다 (구현 우회 방지)', () => {
    const clouds = buildEvidenceClouds(placed, metrics)
    for (const arr of [clouds.baseColors, clouds.sparkColors]) {
      for (let i = 0; i < arr.length; i += 3) {
        const l = 0.2126 * arr[i] + 0.7152 * arr[i + 1] + 0.0722 * arr[i + 2]
        expect(l).toBeLessThan(BLOOM_THRESHOLD)
      }
    }
  })
})

describe('regionEnergies — 훈련 에너지 (§7-5 Size 채널의 region 집계)', () => {
  it('데이터 없음 → 전 region 0, 합에 단조 증가·포화(<1)', () => {
    const zero = regionEnergies(placed, metricsFor(() => ({})))
    for (const r of REGIONS) expect(zero.get(r.id)).toBe(0)
    const some = regionEnergies(placed, metricsFor(() => ({ evidence_total: 20 })))
    const more = regionEnergies(placed, metricsFor(() => ({ evidence_total: 400 })))
    for (const r of REGIONS) {
      expect(some.get(r.id)!).toBeGreaterThan(0)
      expect(more.get(r.id)!).toBeGreaterThan(some.get(r.id)!)
      expect(more.get(r.id)!).toBeLessThan(1)
    }
  })
})

describe('buildShellField — 뇌 형태 상시 + 훈련 에너지 표정 (region별 그룹)', () => {
  const zeroE = new Map<RegionId, number>(REGIONS.map((r) => [r.id, 0]))
  const fullE = new Map<RegionId, number>(REGIONS.map((r) => [r.id, 1]))
  const lumaOf = (c: Float32Array, i: number) =>
    0.2126 * c[i] + 0.7152 * c[i + 1] + 0.0722 * c[i + 2]
  const count = (f: ReturnType<typeof buildShellField>, k: 'dust' | 'beads' | 'accents') =>
    f.reduce((s, r) => s + r[k].positions.length / 3, 0)

  it('무학습에도 형태는 있다: dust 전량 + region당 기본 bead, accent는 0', () => {
    const f = buildShellField(zeroE)
    expect(f).toHaveLength(REGIONS.length) // region별 그룹 — 호버 배수 렌더의 전제
    expect(count(f, 'dust')).toBe(DUST_COUNT)
    for (const rf of f) {
      expect(rf.beads.positions.length / 3).toBeGreaterThan(0) // BEAD_BASE — 기본 질감
      expect(rf.accents.positions.length).toBe(0) // 큰 알갱이는 학습의 산물
    }
  })

  it('학습될수록 풍성해진다: bead·accent 수가 에너지에 비례해 증가', () => {
    const z = buildShellField(zeroE)
    const f = buildShellField(fullE)
    expect(count(f, 'beads')).toBeGreaterThan(count(z, 'beads'))
    expect(count(f, 'accents')).toBeGreaterThan(0)
  })

  it('학습될수록 선명해진다: full 에너지의 dust 색 luma > zero (같은 region 기준)', () => {
    const z = buildShellField(zeroE)[0]
    const f = buildShellField(fullE)[0]
    expect(lumaOf(f.dust.colors, 0)).toBeGreaterThan(lumaOf(z.dust.colors, 0))
  })

  it('광량 규율: 최대 에너지 × 호버 배수(HOVER_BOOST)도 luma < BLOOM_THRESHOLD', () => {
    const f = buildShellField(fullE)
    for (const rf of f) {
      for (const layer of [rf.volume, rf.dust, rf.beads, rf.accents]) {
        for (let i = 0; i < layer.colors.length; i += 3) {
          expect(lumaOf(layer.colors, i) * HOVER_BOOST).toBeLessThan(BLOOM_THRESHOLD)
        }
      }
    }
  })

  it('결정론 + 서명: 같은 에너지 → 같은 필드, 에너지 변화 → 다른 서명', () => {
    expect(buildShellField(fullE)).toEqual(buildShellField(fullE))
    expect(shellSignature(zeroE)).not.toBe(shellSignature(fullE))
  })
})

describe('reliability 글로우 — 측정된 region 입자의 수·밝기 가산 (Arena 파생)', () => {
  const midE = new Map<RegionId, number>(REGIONS.map((r) => [r.id, 0.5]))
  const glowsOf = (v: number | null) =>
    new Map<RegionId, number | null>(REGIONS.map((r) => [r.id, v]))
  const lumaOf = (c: Float32Array, i: number) =>
    0.2126 * c[i] + 0.7152 * c[i + 1] + 0.0722 * c[i + 2]

  it('미측정(null) = 완전 무변화 — 글로우 없는 필드와 동일 버퍼', () => {
    expect(buildShellField(midE, glowsOf(null))).toEqual(buildShellField(midE))
  })

  it('측정 0점도 미측정과 구분된다: bead·accent 수와 luma가 소폭 오른다 (측정 표시)', () => {
    const none = buildShellField(midE)[0]
    const zero = buildShellField(midE, glowsOf(0))[0]
    expect(zero.beads.positions.length).toBeGreaterThan(none.beads.positions.length)
    expect(zero.accents.positions.length).toBeGreaterThan(none.accents.positions.length)
    expect(lumaOf(zero.dust.colors, 0)).toBeGreaterThan(lumaOf(none.dust.colors, 0))
  })

  it('단조: 정답률이 높을수록 입자가 더 많고 더 밝다', () => {
    const low = buildShellField(midE, glowsOf(0.2))[0]
    const high = buildShellField(midE, glowsOf(0.9))[0]
    expect(high.beads.positions.length).toBeGreaterThan(low.beads.positions.length)
    expect(high.accents.positions.length).toBeGreaterThan(low.accents.positions.length)
    expect(lumaOf(high.dust.colors, 0)).toBeGreaterThan(lumaOf(low.dust.colors, 0))
  })

  it('광량 규율은 훈련·호버 전용 잠금 그대로: 글로우 없는 최대 에너지는 블룸 미만 (기존 테스트) — 글로우 기여만 고득점에서 임계를 넘을 수 있다', () => {
    const fullGlow = buildShellField(midE, glowsOf(1))
    // 글로우가 luma를 실제로 끌어올렸는지(표현이 살아있는지)만 확인 — 상한은 정확도 채널이라 없음
    const none = buildShellField(midE)
    for (const [i, rf] of fullGlow.entries()) {
      expect(lumaOf(rf.beads.colors, 0)).toBeGreaterThan(lumaOf(none[i].beads.colors, 0))
    }
  })

  it('서명: 글로우 변화(측정 도착)만으로도 필드가 재빌드된다', () => {
    expect(shellSignature(midE, glowsOf(null))).not.toBe(shellSignature(midE, glowsOf(0)))
    expect(shellSignature(midE, glowsOf(0.3))).not.toBe(shellSignature(midE, glowsOf(0.7)))
    expect(shellSignature(midE)).toBe(shellSignature(midE, glowsOf(null)))
  })
})

describe('cloudsSignature — 캐시 키', () => {
  const base = metricsFor(() => ({ evidence_total: 10 }))

  it('같은 데이터 → 같은 서명, 지표 변화 → 다른 서명', () => {
    expect(cloudsSignature(placed, base)).toBe(cloudsSignature(placed, base))
    const changed = new Map(base)
    const first = placed[0].nodeId
    changed.set(first, { ...changed.get(first)!, evidence_total: 11 })
    expect(cloudsSignature(placed, changed)).not.toBe(cloudsSignature(placed, base))
  })

  it('위치 변화도 서명을 바꾼다', () => {
    const moved = placed.map((n, i) =>
      i === 0 ? { ...n, position: [9, 9, 9] as const } : n,
    )
    expect(cloudsSignature(moved, base)).not.toBe(cloudsSignature(placed, base))
  })
})
