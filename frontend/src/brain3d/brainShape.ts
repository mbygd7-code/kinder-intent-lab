/**
 * 해부학적 뇌 실루엣 — 절차적 생성 (외부 에셋 0, 디자인 레퍼런스의 단일 뇌).
 *
 * 형태 = 타원체 합집합: 대뇌 + 좌우 측두엽 벌지 + 소뇌 + 뇌간(캡슐).
 * 측면(사시상) 뷰에서 레퍼런스 이미지의 프로필(전두 둥근 앞, 후두 뒤, 소뇌·뇌간 아래)이 나온다.
 * 모든 샘플링은 mulberry32 고정 시드 — Math.random 금지(리로드 불변, brainShape.test.ts로 잠금).
 *
 * 이 레이어는 전부 **장식**이다(§7-5 정보 정직성): 점·웹은 의미 노드가 아니고 상호작용도 없다.
 * 색만 region 로브(최근접 앵커 보로노이)를 따라가 "하나의 뇌 안의 색 영역들"을 만든다.
 */
import { mulberry32 } from './hash'
import { REGIONS, type RegionId } from './regions'

export interface Ellipsoid {
  center: readonly [number, number, number]
  radii: readonly [number, number, number]
}

// 뇌 구성체 (로컬 좌표: +z 전두(앞), +y 상부, x 좌우)
export const CEREBRUM: Ellipsoid = { center: [0, 0.22, 0.05], radii: [0.72, 0.72, 1.08] }
export const TEMPORAL_L: Ellipsoid = { center: [-0.45, -0.12, 0.25], radii: [0.34, 0.38, 0.62] }
export const TEMPORAL_R: Ellipsoid = { center: [0.45, -0.12, 0.25], radii: [0.34, 0.38, 0.62] }
export const CEREBELLUM: Ellipsoid = { center: [0, -0.48, -0.68], radii: [0.46, 0.3, 0.4] }
/** 뇌간 캡슐: 선분 A→B 주변 반지름 r */
export const STEM = {
  a: [0, -0.28, -0.28] as const,
  b: [0, -1.02, -0.42] as const,
  r: 0.13,
}

/** 실루엣 구성 타원체 목록 (테스트에서 표면 근접 검증에 사용) */
export const BRAIN_ELLIPSOIDS: readonly Ellipsoid[] = [
  CEREBRUM, TEMPORAL_L, TEMPORAL_R, CEREBELLUM,
]
const COMPONENTS: readonly Ellipsoid[] = BRAIN_ELLIPSOIDS

/** 타원체 내부 판정값: <1 내부, =1 표면 */
export function ellipsoidValue(p: readonly number[], e: Ellipsoid): number {
  const dx = (p[0] - e.center[0]) / e.radii[0]
  const dy = (p[1] - e.center[1]) / e.radii[1]
  const dz = (p[2] - e.center[2]) / e.radii[2]
  return dx * dx + dy * dy + dz * dz
}

/** 뇌간 축(선분)까지의 거리를 캡슐 반지름으로 나눈 비율: <1 내부, =1 옆면 */
export function stemDistanceRatio(p: readonly number[]): number {
  const { a, b, r } = STEM
  const ab = [b[0] - a[0], b[1] - a[1], b[2] - a[2]]
  const ap = [p[0] - a[0], p[1] - a[1], p[2] - a[2]]
  const len2 = ab[0] * ab[0] + ab[1] * ab[1] + ab[2] * ab[2]
  const t = Math.max(0, Math.min(1, (ap[0] * ab[0] + ap[1] * ab[1] + ap[2] * ab[2]) / len2))
  const cx = a[0] + ab[0] * t
  const cy = a[1] + ab[1] * t
  const cz = a[2] + ab[2] * t
  return Math.hypot(p[0] - cx, p[1] - cy, p[2] - cz) / r
}

function insideCapsule(p: readonly number[]): boolean {
  return stemDistanceRatio(p) <= 1
}

/** 합집합 내부 판정 — 장식 점이 "뇌 안"에 있는지의 원천 (테스트로 잠금) */
export function insideBrain(p: readonly number[]): boolean {
  if (insideCapsule(p)) return true
  for (const e of COMPONENTS) if (ellipsoidValue(p, e) <= 1) return true
  return false
}

/** 최근접 region 앵커 → 로브 색 배정 (보로노이) */
export function nearestRegion(p: readonly number[]): RegionId {
  let best = Infinity
  let id: RegionId = REGIONS[0].id
  for (const r of REGIONS) {
    const d =
      (p[0] - r.center[0]) ** 2 + (p[1] - r.center[1]) ** 2 + (p[2] - r.center[2]) ** 2
    if (d < best) {
      best = d
      id = r.id
    }
  }
  return id
}

/** 합집합 바깥 표면(다른 구성체 내부에 묻힌 표면점 제외)에 점을 뿌린다 — 실루엣 셸 */
export function sampleShell(count: number, seed = 0xb2a1_c3d4): Float32Array {
  const rng = mulberry32(seed)
  const out = new Float32Array(count * 3)
  // 구성체별 대략적 표면적 비례 배분(대뇌가 지배적)
  const weights = [0.52, 0.11, 0.11, 0.16, 0.1] // cerebrum, tempL, tempR, cerebellum, stem
  let i = 0
  let guard = 0
  while (i < count && guard < count * 60) {
    guard++
    const w = rng()
    let acc = 0
    let ci = 0
    for (let k = 0; k < weights.length; k++) {
      acc += weights[k]
      if (w <= acc) {
        ci = k
        break
      }
    }
    let p: [number, number, number]
    if (ci === 4) {
      // 뇌간: 캡슐 옆면
      const t = rng()
      const ang = rng() * Math.PI * 2
      const { a, b, r } = STEM
      const cx = a[0] + (b[0] - a[0]) * t
      const cy = a[1] + (b[1] - a[1]) * t
      const cz = a[2] + (b[2] - a[2]) * t
      p = [cx + Math.cos(ang) * r, cy, cz + Math.sin(ang) * r]
    } else {
      const e = COMPONENTS[ci]
      const theta = rng() * Math.PI * 2
      const cosPhi = 2 * rng() - 1
      const sinPhi = Math.sqrt(1 - cosPhi * cosPhi)
      // 주름(gyri) 변위: 사인 곱 필드 — 대뇌·측두엽은 굵은 주름, 소뇌는 가는 가로 줄무늬.
      // 결정론(각도 기반), Math.random 없음. 진폭은 반경의 ±3.5%.
      const fold =
        ci === 3
          ? 0.02 * Math.sin(26 * Math.acos(cosPhi)) // 소뇌: 가는 striation
          : 0.035 *
            Math.sin(5.3 * theta + 1.7) *
            Math.sin(4.1 * Math.acos(cosPhi) + 0.6)
      // 살짝 안팎 지터(±2%) + 주름 — 유기적 질감
      const jit = (0.98 + rng() * 0.045) * (1 + fold)
      p = [
        e.center[0] + e.radii[0] * sinPhi * Math.cos(theta) * jit,
        e.center[1] + e.radii[1] * cosPhi * jit,
        e.center[2] + e.radii[2] * sinPhi * Math.sin(theta) * jit,
      ]
    }
    // 다른 구성체 내부에 묻힌 표면점은 버린다(합집합의 겉면만 남김)
    let buried = false
    for (let k = 0; k < COMPONENTS.length; k++) {
      if (k === ci) continue
      if (ellipsoidValue(p, COMPONENTS[k]) < 0.94) {
        buried = true
        break
      }
    }
    if (ci !== 4 && !buried && insideCapsule(p)) buried = true
    if (buried) continue
    out[i * 3] = p[0]
    out[i * 3 + 1] = p[1]
    out[i * 3 + 2] = p[2]
    i++
  }
  return out.subarray(0, i * 3) as Float32Array
}

/** 합집합 내부 볼륨에 점을 뿌린다 — 내부 성운 */
export function sampleVolume(count: number, seed = 0x5eed_0b0e): Float32Array {
  const rng = mulberry32(seed)
  const out = new Float32Array(count * 3)
  let i = 0
  let guard = 0
  while (i < count && guard < count * 40) {
    guard++
    const p = [
      -0.85 + rng() * 1.7,
      -1.15 + rng() * 2.1,
      -1.15 + rng() * 2.3,
    ] as const
    if (!insideBrain(p)) continue
    out[i * 3] = p[0]
    out[i * 3 + 1] = p[1]
    out[i * 3 + 2] = p[2]
    i++
  }
  return out.subarray(0, i * 3) as Float32Array
}

/**
 * 장식 신경 웹: 셸 점들의 k-최근접 이웃 연결 (거리 상한, 쌍 중복 제거).
 * 반환: LineSegments용 위치 인덱스 쌍 배열. 의미 없음 — §5-6 confusion edge와 무관(장식 레이어).
 */
export function buildWeb(
  positions: Float32Array,
  k = 2,
  maxDist = 0.17,
): Array<[number, number]> {
  const n = positions.length / 3
  const md2 = maxDist * maxDist
  const pairs = new Set<number>()
  for (let i = 0; i < n; i++) {
    const ix = positions[i * 3]
    const iy = positions[i * 3 + 1]
    const iz = positions[i * 3 + 2]
    // k개 최근접 (단순 O(n²) — 빌드 1회, n≈2500이면 수십 ms)
    const best: Array<{ j: number; d: number }> = []
    for (let j = 0; j < n; j++) {
      if (j === i) continue
      const dx = positions[j * 3] - ix
      const dy = positions[j * 3 + 1] - iy
      const dz = positions[j * 3 + 2] - iz
      const d = dx * dx + dy * dy + dz * dz
      if (d > md2) continue
      if (best.length < k) {
        best.push({ j, d })
        best.sort((a, b) => a.d - b.d)
      } else if (d < best[k - 1].d) {
        best[k - 1] = { j, d }
        best.sort((a, b) => a.d - b.d)
      }
    }
    for (const { j } of best) {
      const key = i < j ? i * n + j : j * n + i
      pairs.add(key)
    }
  }
  const edges: Array<[number, number]> = []
  for (const key of pairs) edges.push([Math.floor(key / n), key % n])
  return edges
}
