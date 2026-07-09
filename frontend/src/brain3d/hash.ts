/**
 * 결정론 해시·PRNG — brain3d 전 레이어 공용 (Math.random 금지: 리로드·재렌더 좌표 불변).
 * layout.ts(3D 배치)·brain2dLayout.ts(2D 배치)·ParticleLayer(장식 산포)가 공유한다.
 * 계약은 hash.test.ts가 알려진 입출력 쌍으로 고정한다.
 */

/** FNV-1a 32bit — 문자열 → 결정론 시드 */
export function fnv1a(s: string): number {
  let h = 0x811c9dc5
  for (let i = 0; i < s.length; i++) {
    h ^= s.charCodeAt(i)
    h = Math.imul(h, 0x01000193)
  }
  return h >>> 0
}

/** murmur3 fmix32 — 순차적 id에서도 비트를 고르게 섞는다 (FNV 단독은 호 패턴 발생) */
export function fmix32(h: number): number {
  h ^= h >>> 16
  h = Math.imul(h, 0x85ebca6b)
  h ^= h >>> 13
  h = Math.imul(h, 0xc2b2ae35)
  h ^= h >>> 16
  return h >>> 0
}

/** mulberry32 — 시드 고정 PRNG (0 ≤ x < 1 스트림) */
export function mulberry32(seed: number): () => number {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) | 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}
