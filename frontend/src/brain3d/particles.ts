/**
 * 파티클 인코더 — 뇌 필드와 evidence 디테일, 둘 다 실데이터 (encodings.ts 패턴).
 *
 * [뇌 필드 — buildShellField] 뇌 모양 파티클 필드는 **항상 존재**한다(형태 = 구조).
 * 다만 그 표정이 데이터다: region별 **훈련 에너지**(evidence 총량의 포화 함수)에 따라
 *  - 채도: slate(무학습) → region 고유색(학습됨)으로 립
 *  - 광량: 어둡게 → 선명하게 (단, 항상 블룸 임계 미만 — 빛남은 Arena 정확도 전용)
 *  - 풍성함: 중간 알갱이(bead)·큰 알갱이(accent) 수가 에너지에 비례해 늘어난다
 * 즉 "학습이 없어도 뇌 형태는 있고, 학습될수록 그 영역이 화려해진다".
 *
 * [reliability 글로우 — 두 번째 입력] region 정답률(Arena 파생, statusEncodings.regionGlow)이
 * 있으면 그 region 입자의 **수가 더 늘고 색이 더 밝아진다**(스프라이트 블롭 아님 —
 * 2026-07-15 뇌 자체가 빛나는 표현으로 교체). null(미측정) = 완전 무변화(무광 = 부재).
 * 글로우 기여만은 높은 점수에서 블룸 임계를 넘을 수 있다 — 그것이 곧 "빛남 = Arena
 * 정확도" 채널이라 의미가 오염되지 않는다. 훈련 에너지·호버만으로는 여전히 블룸 불가.
 *
 * [노드 디테일 — buildEvidenceClouds] 노드 주변 미세 입자 = 노드별 근거량(√포화+waterfill),
 * 산포 ∝ diversity, 금색 스파크 = GOLD·전문가 evidence. 무학습 노드 = 무입자.
 *
 * 에너지·채도는 §7-5 Size(훈련량) 채널의 region 집계다 — 밝기(정확도) 채널과 무관하며
 * particles.test.ts가 모든 색의 luma < BLOOM_THRESHOLD를 실행 가능하게 강제한다.
 * 결정론: 시드는 hash.ts, Math.random 금지.
 */
import { insideBrain, nearestRegion, sampleShell, sampleVolume } from './brainShape'
import { fmix32, fnv1a, mulberry32 } from './hash'
import type { PlacedNode } from './layout'
import { REGION_BY_ID, REGIONS, type RegionId } from './regions'

export interface ParticleMetrics {
  evidence_total: number
  evidence_diversity: number
  gold_count: number
  expert_count: number // evidence_buckets.expert (부재 시 0)
}

// ---------- region 훈련 에너지 (§7-5 Size 채널의 region 집계) ----------

/** 에너지 반포화점 — region evidence 합이 이 값일 때 에너지 0.5 (표현 상수) */
export const ENERGY_HALF = 300

/** region별 훈련 에너지 ∈ [0,1) — Σ evidence_total의 포화 함수. 데이터 없으면 0. */
export function regionEnergies(
  placed: readonly PlacedNode[],
  metrics: ReadonlyMap<string, ParticleMetrics>,
): Map<RegionId, number> {
  const totals = new Map<RegionId, number>(REGIONS.map((r) => [r.id, 0]))
  for (const n of placed) {
    const t = metrics.get(n.nodeId)?.evidence_total ?? 0
    totals.set(n.region, (totals.get(n.region) ?? 0) + t)
  }
  const out = new Map<RegionId, number>()
  for (const [id, t] of totals) out.set(id, t / (t + ENERGY_HALF))
  return out
}

// ---------- 뇌 필드 (형태 상시 + 에너지 표정) ----------

export interface ShellLayerBuffers {
  positions: Float32Array
  colors: Float32Array
}

/**
 * region 1개의 필드 레이어 묶음 — region별로 분리 렌더해 호버 시 그 region의
 * 입자만 재질 배수로 즉시 밝힐 수 있다(버퍼 재생성 없음).
 */
export interface RegionField {
  region: RegionId
  volume: ShellLayerBuffers // 내부 성운 — 깊이감
  dust: ShellLayerBuffers // 표면 미세 입자 — 뇌 형태의 기본(항상 전량)
  beads: ShellLayerBuffers // 중간 알갱이 — 기본 소량 + 에너지 비례 증가
  accents: ShellLayerBuffers // 큰 알갱이 — 에너지 비례(무학습 region은 0)
}

/** 호버 시 그 region 필드 광량 배수 — 최대 광량×배수도 블룸 임계 미만(테스트 잠금) */
export const HOVER_BOOST = 1.3

// reliability 글로우(Arena 파생) — 측정된 region의 입자 수·밝기 가산.
// BASE(정답률 0이어도 적용)가 "측정됨"의 표시다 — 미측정(null)과 0점을 구분한다.
export const GLOW_BEAD_BASE = 24 // 측정 표시 — 정답률 0이어도 bead 소량 추가
export const GLOW_BEAD_GAIN = 96 // 정답률 1.0에서 추가되는 bead
export const GLOW_ACCENT_BASE = 8
export const GLOW_ACCENT_GAIN = 36
export const GLOW_LUMA_FLOOR = 0.06 // 측정 표시 — 미묘한 상시 립
export const GLOW_LUMA_GAIN = 0.55 // 정답률 1.0에서 색 밝기 ×1.61 — 고득점 region만 블룸 진입

/** 글로우 색 배수 — null(미측정) = 1(무변화). 정답률에 단조 증가. */
export function glowLumaBoost(glow: number | null): number {
  if (glow == null) return 1
  return 1 + GLOW_LUMA_FLOOR + GLOW_LUMA_GAIN * clamp01(glow)
}

// 전부 표현 상수 — 형태 예산과 지각 가능성의 균형점
export const DUST_COUNT = 2600
export const VOLUME_COUNT = 900
const BEAD_POOL = 2200
const ACCENT_POOL = 900
export const BEAD_BASE = 64 // region당 기본 bead — 무학습이어도 형태의 질감은 있다
export const BEAD_GAIN = 120 // region당 에너지 1.0에서 추가되는 bead
export const ACCENT_MAX = 44 // region당 에너지 1.0에서의 accent 수 (0 에너지 = 0)

/** 무학습 형태 색 — 구조 slate. 에너지가 오르면 region 색으로 립 */
export const FORM_SLATE = '#5b6b85'
const MIX_BASE = 0.3
const MIX_GAIN = 0.7
// 광량 램프 — 최대(에너지 1)에서도 luma < BLOOM_THRESHOLD (particles.test.ts 잠금)
export const DUST_INTENSITY: readonly [number, number] = [0.105, 0.06] // 0.105 → 0.165
export const VOLUME_INTENSITY: readonly [number, number] = [0.06, 0.05] // 0.06 → 0.11
export const BEAD_INTENSITY: readonly [number, number] = [0.11, 0.06] // 0.11 → 0.17
export const ACCENT_INTENSITY: readonly [number, number] = [0.12, 0.05] // 0.12 → 0.17

function hexRgb(hex: string): [number, number, number] {
  const h = hex.replace('#', '')
  return [
    parseInt(h.slice(0, 2), 16) / 255,
    parseInt(h.slice(2, 4), 16) / 255,
    parseInt(h.slice(4, 6), 16) / 255,
  ]
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v))
const SLATE_RGB = hexRgb(FORM_SLATE)

/** slate → region 색 립 + 광량 램프 — 에너지가 곧 표정이다 */
function fieldColor(region: RegionId, energy: number, ramp: readonly [number, number]) {
  const [r, g, b] = hexRgb(REGION_BY_ID[region].color)
  const mix = MIX_BASE + MIX_GAIN * energy
  const s = ramp[0] + ramp[1] * energy
  return [
    (SLATE_RGB[0] + (r - SLATE_RGB[0]) * mix) * s,
    (SLATE_RGB[1] + (g - SLATE_RGB[1]) * mix) * s,
    (SLATE_RGB[2] + (b - SLATE_RGB[2]) * mix) * s,
  ] as const
}

interface RegionPool {
  /** region별 점 인덱스 버킷 (풀 순서 = 결정론) */
  buckets: Map<RegionId, number[]>
  points: Float32Array
}

function bucketByRegion(points: Float32Array): RegionPool {
  const buckets = new Map<RegionId, number[]>(REGIONS.map((r) => [r.id, []]))
  for (let i = 0; i < points.length / 3; i++) {
    const p = [points[i * 3], points[i * 3 + 1], points[i * 3 + 2]] as const
    buckets.get(nearestRegion(p))!.push(i)
  }
  return { buckets, points }
}

// 데이터 무관 샘플 풀 — 1회 계산 후 정적 캐시 (에너지는 색·개수에만 관여)
let poolsCache: {
  dust: RegionPool
  volume: RegionPool
  beads: RegionPool
  accents: RegionPool
} | null = null

function pools() {
  return (poolsCache ??= {
    dust: bucketByRegion(sampleShell(DUST_COUNT, 0xb2a1_c3d4)),
    volume: bucketByRegion(sampleVolume(VOLUME_COUNT)),
    beads: bucketByRegion(sampleShell(BEAD_POOL, 0xbead_0001)),
    accents: bucketByRegion(sampleShell(ACCENT_POOL, 0x610_44ea)),
  })
}

/** 풀의 region 버킷에서 앞 take개 — region 단색(에너지 립×램프×글로우) 버퍼로 */
function sliceBucket(
  pool: RegionPool,
  region: RegionId,
  take: number,
  energies: ReadonlyMap<RegionId, number>,
  ramp: readonly [number, number],
  lumaBoost = 1,
): ShellLayerBuffers {
  const bucket = pool.buckets.get(region)!
  const n = Math.min(bucket.length, Math.max(0, Math.round(take)))
  const positions = new Float32Array(n * 3)
  const colors = new Float32Array(n * 3)
  const base = fieldColor(region, energies.get(region) ?? 0, ramp)
  const [r, g, b] = [base[0] * lumaBoost, base[1] * lumaBoost, base[2] * lumaBoost]
  for (let i = 0; i < n; i++) {
    const pi = bucket[i]
    positions[i * 3] = pool.points[pi * 3]
    positions[i * 3 + 1] = pool.points[pi * 3 + 1]
    positions[i * 3 + 2] = pool.points[pi * 3 + 2]
    colors[i * 3] = r
    colors[i * 3 + 1] = g
    colors[i * 3 + 2] = b
  }
  return { positions, colors }
}

const NO_GLOW: ReadonlyMap<RegionId, number | null> = new Map()

export function buildShellField(
  energies: ReadonlyMap<RegionId, number>,
  glows: ReadonlyMap<RegionId, number | null> = NO_GLOW,
): RegionField[] {
  const p = pools()
  return REGIONS.map((reg) => {
    const e = energies.get(reg.id) ?? 0
    const glow = glows.get(reg.id) ?? null
    const boost = glowLumaBoost(glow)
    const beadTake =
      BEAD_BASE + BEAD_GAIN * e +
      (glow == null ? 0 : GLOW_BEAD_BASE + GLOW_BEAD_GAIN * clamp01(glow))
    const accentTake =
      ACCENT_MAX * e + (glow == null ? 0 : GLOW_ACCENT_BASE + GLOW_ACCENT_GAIN * clamp01(glow))
    return {
      region: reg.id,
      volume: sliceBucket(p.volume, reg.id, Infinity, energies, VOLUME_INTENSITY, boost),
      dust: sliceBucket(p.dust, reg.id, Infinity, energies, DUST_INTENSITY, boost),
      beads: sliceBucket(p.beads, reg.id, beadTake, energies, BEAD_INTENSITY, boost),
      accents: sliceBucket(p.accents, reg.id, accentTake, energies, ACCENT_INTENSITY, boost),
    }
  })
}

/** 에너지·글로우 서명(3자리 반올림) — 어느 쪽이 바뀌어도 필드를 재빌드 */
export function shellSignature(
  energies: ReadonlyMap<RegionId, number>,
  glows: ReadonlyMap<RegionId, number | null> = NO_GLOW,
): string {
  return REGIONS.map((r) => {
    const g = glows.get(r.id) ?? null
    return `${r.id}:${(energies.get(r.id) ?? 0).toFixed(3)}:${g == null ? '-' : g.toFixed(3)}`
  }).join('|')
}

let fieldCache: { sig: string; field: RegionField[] } | null = null

export function cachedShellField(
  energies: ReadonlyMap<RegionId, number>,
  glows: ReadonlyMap<RegionId, number | null> = NO_GLOW,
): RegionField[] {
  const sig = shellSignature(energies, glows)
  if (fieldCache?.sig !== sig) fieldCache = { sig, field: buildShellField(energies, glows) }
  return fieldCache.field
}

// ---------- 노드 디테일 입자 (근거량·다양성·GOLD 스파크) ----------

export interface EvidenceClouds {
  basePositions: Float32Array
  baseColors: Float32Array
  sparkPositions: Float32Array
  sparkColors: Float32Array
  /** 노드별 배정 결과 — 범례·검증용 (합 ≤ EVIDENCE_BUDGET) */
  perNode: ReadonlyMap<string, { count: number; sparks: number }>
}

// 디테일은 필드를 보조한다 — 덩어리(blob)로 읽히지 않게 소량·넓은 산포
export const EVIDENCE_BUDGET = 2400
export const PARTICLE_MIN = 4
export const PARTICLE_MAX = 140
export const BASE_INTENSITY = 0.17 // luma 최대 0.786(#facc15)×0.17×1.1 ≈ 0.147 < 0.18
export const SPARK_INTENSITY = 0.17 // #fde68a luma 0.895×0.17 ≈ 0.152 < 0.18
export const SPARK_COLOR = '#fde68a' // GOLD·전문가 — OPERATION(#facc15)과는 백색도·크기로 구분
const JITTER_MAX = 1.1 // 색 지터 상한 ×(0.9 + 0.2·rng())
const SPREAD_MIN = 0.07
const SPREAD_GROW = 0.09
const REJECT_TRIES = 8

interface AllocInput {
  nodeId: string
  total: number
  goldExpert: number
}

/**
 * 예산 배분 — weight=√total(포화: 대형 노드의 예산 독식 방지), waterfill로
 * min/max 클램프를 반복 재분배. nodeId 정렬 순회라 입력 순서 무관 결정론.
 */
export function allocateParticles(
  inputs: AllocInput[],
  budget: number = EVIDENCE_BUDGET,
): Map<string, { count: number; sparks: number }> {
  const out = new Map<string, { count: number; sparks: number }>()
  const eligible = inputs
    .filter((n) => n.total > 0)
    .sort((a, b) => (a.nodeId < b.nodeId ? -1 : 1))
  if (eligible.length === 0) return out

  // 예산이 최소 보장조차 못 채우면 균등 분할(오늘 63노드×4=252 ≪ 2400 — 방어용)
  if (eligible.length * PARTICLE_MIN >= budget) {
    const each = Math.max(1, Math.floor(budget / eligible.length))
    for (const n of eligible) {
      out.set(n.nodeId, { count: each, sparks: Math.min(n.goldExpert, each) })
    }
    return out
  }

  const weight = new Map(eligible.map((n) => [n.nodeId, Math.sqrt(n.total)]))
  const alloc = new Map<string, number>()
  let unfixed = [...eligible]
  let left = budget
  // waterfill: 클램프에 걸린 노드를 고정하고 잔여 예산을 나머지에 재분배
  for (let pass = 0; pass <= eligible.length && unfixed.length > 0; pass++) {
    const wSum = unfixed.reduce((s, n) => s + (weight.get(n.nodeId) ?? 0), 0)
    const violators: AllocInput[] = []
    for (const n of unfixed) {
      const share = Math.round((left * (weight.get(n.nodeId) ?? 0)) / wSum)
      if (share < PARTICLE_MIN || share > PARTICLE_MAX) violators.push(n)
    }
    if (violators.length === 0) {
      for (const n of unfixed) {
        alloc.set(n.nodeId, Math.round((left * (weight.get(n.nodeId) ?? 0)) / wSum))
      }
      break
    }
    for (const n of violators) {
      const share = Math.round((left * (weight.get(n.nodeId) ?? 0)) / wSum)
      const fixed = share < PARTICLE_MIN ? PARTICLE_MIN : PARTICLE_MAX
      alloc.set(n.nodeId, fixed)
      left -= fixed
    }
    unfixed = unfixed.filter((n) => !alloc.has(n.nodeId))
  }

  // 반올림 초과분 트림 — MIN 초과 노드 중 큰 것부터(동률은 nodeId 순) 1씩 회수
  let total = [...alloc.values()].reduce((s, v) => s + v, 0)
  while (total > budget) {
    let target: string | null = null
    let max = PARTICLE_MIN
    for (const [id, v] of [...alloc.entries()].sort()) {
      if (v > max) {
        max = v
        target = id
      }
    }
    if (target === null) break
    alloc.set(target, max - 1)
    total--
  }

  for (const n of eligible) {
    const count = alloc.get(n.nodeId) ?? PARTICLE_MIN
    out.set(n.nodeId, { count, sparks: Math.min(n.goldExpert, count) })
  }
  return out
}

export function buildEvidenceClouds(
  placed: readonly PlacedNode[],
  metrics: ReadonlyMap<string, ParticleMetrics>,
): EvidenceClouds {
  const inputs: AllocInput[] = placed.map((n) => {
    const m = metrics.get(n.nodeId)
    return {
      nodeId: n.nodeId,
      total: m?.evidence_total ?? 0,
      goldExpert: (m?.gold_count ?? 0) + (m?.expert_count ?? 0),
    }
  })
  const alloc = allocateParticles(inputs)

  const base: number[] = []
  const baseCol: number[] = []
  const spark: number[] = []
  const sparkCol: number[] = []
  const sparkRgb = hexRgb(SPARK_COLOR)

  // nodeId 정렬 순회 — 버퍼 내용까지 입력 순서 무관 결정론
  const sorted = [...placed].sort((a, b) => (a.nodeId < b.nodeId ? -1 : 1))
  for (const node of sorted) {
    const a = alloc.get(node.nodeId)
    if (!a) continue
    const m = metrics.get(node.nodeId)
    const spread = SPREAD_MIN + SPREAD_GROW * clamp01(m?.evidence_diversity ?? 0)
    const rng = mulberry32(fmix32(fnv1a(`${node.nodeId}#ev`)))
    const [cr, cg, cb] = hexRgb(REGION_BY_ID[node.region].color)

    for (let k = 0; k < a.count; k++) {
      // 뇌 내부 ∩ 자기 Voronoi 거부 샘플 — 실패마다 반경 축소, 최종 폴백 = 노드 위치
      let px = node.position[0]
      let py = node.position[1]
      let pz = node.position[2]
      for (let t = 0; t < REJECT_TRIES; t++) {
        const theta = 2 * Math.PI * rng()
        const phi = Math.acos(2 * rng() - 1)
        const shrink = t < 4 ? 1 : 0.6 ** (t - 3)
        const r = spread * Math.cbrt(rng()) * shrink
        const x = node.position[0] + r * Math.sin(phi) * Math.cos(theta)
        const y = node.position[1] + r * Math.sin(phi) * Math.sin(theta)
        const z = node.position[2] + r * Math.cos(phi)
        if (insideBrain([x, y, z]) && nearestRegion([x, y, z]) === node.region) {
          px = x
          py = y
          pz = z
          break
        }
      }
      const jitter = 0.9 + 0.2 * rng() // ≤ JITTER_MAX — luma 상한 계산에 포함
      if (k < a.sparks) {
        spark.push(px, py, pz)
        sparkCol.push(
          sparkRgb[0] * SPARK_INTENSITY,
          sparkRgb[1] * SPARK_INTENSITY,
          sparkRgb[2] * SPARK_INTENSITY,
        )
      } else {
        base.push(px, py, pz)
        const s = BASE_INTENSITY * Math.min(jitter, JITTER_MAX)
        baseCol.push(cr * s, cg * s, cb * s)
      }
    }
  }

  return {
    basePositions: new Float32Array(base),
    baseColors: new Float32Array(baseCol),
    sparkPositions: new Float32Array(spark),
    sparkColors: new Float32Array(sparkCol),
    perNode: new Map([...alloc.entries()].sort()),
  }
}

/** 데이터 서명 — 위치·지표가 하나라도 바뀌면 달라진다 (캐시 키). */
export function cloudsSignature(
  placed: readonly PlacedNode[],
  metrics: ReadonlyMap<string, ParticleMetrics>,
): string {
  const parts = [...placed]
    .sort((a, b) => (a.nodeId < b.nodeId ? -1 : 1))
    .map((n) => {
      const m = metrics.get(n.nodeId)
      return [
        n.nodeId,
        m?.evidence_total ?? 0,
        m?.evidence_diversity ?? 0,
        m?.gold_count ?? 0,
        m?.expert_count ?? 0,
        n.position.join(','),
      ].join('|')
    })
  return String(fnv1a(parts.join(';')))
}

// 모듈 캐시 — 2D↔3D 리마운트에 재계산 없음, 데이터가 바뀌면(서명 변경) 재빌드
let cache: { sig: string; clouds: EvidenceClouds } | null = null

export function cachedEvidenceClouds(
  placed: readonly PlacedNode[],
  metrics: ReadonlyMap<string, ParticleMetrics>,
): EvidenceClouds {
  const sig = cloudsSignature(placed, metrics)
  if (cache?.sig !== sig) cache = { sig, clouds: buildEvidenceClouds(placed, metrics) }
  return cache.clouds
}
