/**
 * 블룸 임계 단일 원천 — 블룸은 §7-5 밝기(=Arena 정확도) 채널 전용이다.
 *
 * BrainCanvas의 EffectComposer가 이 임계를 쓰고, 데이터 파티클·구조 쉘은
 * luma(색 × 강도)가 임계 미만이어야 한다(particles.test.ts가 실행 가능하게 강제).
 * 파티클이 블룸을 타면 "빛남 = 측정된 정확도"라는 유일 광량 의미가 오염된다.
 */
export const BLOOM_THRESHOLD = 0.18

/** Rec.709 상대 휘도 — hex 색상 × 강도 배수의 luma ∈ [0, intensity]. */
export function luma(hex: string, intensity = 1): number {
  const h = hex.replace('#', '')
  const r = parseInt(h.slice(0, 2), 16) / 255
  const g = parseInt(h.slice(2, 4), 16) / 255
  const b = parseInt(h.slice(4, 6), 16) / 255
  return (0.2126 * r + 0.7152 * g + 0.0722 * b) * intensity
}
