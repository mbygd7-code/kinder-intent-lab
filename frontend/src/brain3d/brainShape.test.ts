/**
 * 해부학적 실루엣 불변식 — 장식 레이어의 구조 정직성 + 결정론.
 *
 * - 샘플 점(셸·볼륨)은 전부 뇌 합집합 안(셸은 지터 여유 내)에 있다
 * - 전체 region 앵커가 모두 실루엣 내부에 있다 (로브 = 뇌 안의 영역)
 * - 샘플링·웹은 결정론(고정 시드) — 리로드마다 같은 뇌
 */
import { describe, expect, it } from 'vitest'

import {
  BRAIN_ELLIPSOIDS,
  buildWeb,
  ellipsoidValue,
  insideBrain,
  nearestRegion,
  sampleShell,
  sampleVolume,
  stemDistanceRatio,
} from './brainShape'
import { REGIONS } from './regions'

describe('brainShape — 실루엣·샘플러', () => {
  it('전체 region 앵커가 모두 뇌 실루엣 내부에 있다 (onto-2.0: 8)', () => {
    for (const r of REGIONS) {
      expect(insideBrain(r.center), r.id).toBe(true)
    }
  })

  it('볼륨 점은 전부 insideBrain', () => {
    const pos = sampleVolume(600)
    expect(pos.length / 3).toBeGreaterThan(500) // rejection 수율 확인
    for (let i = 0; i < pos.length; i += 3) {
      expect(insideBrain([pos[i], pos[i + 1], pos[i + 2]])).toBe(true)
    }
  })

  it('셸 점은 어떤 구성체의 표면 부근(지터 범위)에 있다 — 내부 중심점 아님', () => {
    const pos = sampleShell(600)
    expect(pos.length / 3).toBeGreaterThan(400)
    for (let i = 0; i < pos.length; i += 3) {
      const p = [pos[i], pos[i + 1], pos[i + 2]] as const
      // 타원체 표면: value = (jit×(1±주름 0.035))² ∈ [0.894, 1.126]. 뇌간 옆면: 축거리/r = 1.
      const onEllipsoid = BRAIN_ELLIPSOIDS.some((e) => {
        const v = ellipsoidValue(p, e)
        return v >= 0.88 && v <= 1.14
      })
      const onStem = Math.abs(stemDistanceRatio(p) - 1) <= 0.08
      expect(onEllipsoid || onStem, `점 ${i / 3}이 표면 근방이 아님`).toBe(true)
    }
  })

  it('결정론: 같은 시드 → 같은 점·같은 웹', () => {
    const a = sampleShell(300)
    const b = sampleShell(300)
    expect(Array.from(a)).toEqual(Array.from(b))
    expect(buildWeb(a, 2, 0.2)).toEqual(buildWeb(b, 2, 0.2))
  })

  it('웹 간선은 거리 상한을 지키고 쌍 중복이 없다', () => {
    const pos = sampleShell(400)
    const maxDist = 0.2
    const edges = buildWeb(pos, 2, maxDist)
    expect(edges.length).toBeGreaterThan(0)
    const seen = new Set<string>()
    for (const [i, j] of edges) {
      const key = i < j ? `${i}-${j}` : `${j}-${i}`
      expect(seen.has(key)).toBe(false)
      seen.add(key)
      const d = Math.hypot(
        pos[i * 3] - pos[j * 3],
        pos[i * 3 + 1] - pos[j * 3 + 1],
        pos[i * 3 + 2] - pos[j * 3 + 2],
      )
      expect(d).toBeLessThanOrEqual(maxDist + 1e-9)
    }
  })

  it('nearestRegion은 앵커 자기 자리에서 자기 자신', () => {
    for (const r of REGIONS) expect(nearestRegion(r.center)).toBe(r.id)
  })
})
