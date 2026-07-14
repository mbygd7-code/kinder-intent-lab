/**
 * 플랫폼·region glow 상태 인코더 — 전부 Arena 산출값만 받는다 (§7-1·§7-6).
 *
 * - 스테이지 링: 바닥 5개 동심 링 중 점등 수 = brain_stage(0~5). null·0 = 전부 소등.
 * - KTIB 호: 플랫폼 외곽 호 길이 = ktib_global × 2π. null = 호 자체가 없다(0%가 아니다).
 * - region glow: 은은한 광 ∝ region reliability(Arena heldout 평균). null = 무광(부재).
 * 미측정을 0으로 그리지 않는다 — 게이지의 "부재"가 곧 "측정 전"을 전달한다.
 */
import type { GrowthStage } from '../api/observatory'

/** Stage 1~5에 대응하는 바닥 링 반지름 (표현 상수) */
export const STAGE_RING_RADII = [0.47, 0.63, 0.79, 0.95, 1.11] as const

/** 점등 여부 배열 — index i = Stage i+1 도달 여부. null·0 → 전부 false. */
export function litRings(brainStage: GrowthStage | null): boolean[] {
  const stage = brainStage ?? 0
  return STAGE_RING_RADII.map((_, i) => i < stage)
}

/** KTIB 호 — null(미측정)이면 null(호 없음). 측정값은 비율 그대로 호 길이로. */
export function ktibArc(ktib: number | null): { thetaLength: number } | null {
  if (ktib === null) return null
  const v = Math.min(1, Math.max(0, ktib))
  return { thetaLength: v * Math.PI * 2 }
}

/**
 * region 글로우 — reliability(Arena 파생)에 단조. null → null(무광 = 미측정).
 * 표현은 BrainFieldLayer→particles.ts: 그 영역 입자의 수·밝기 가산(블롭 스프라이트 폐지).
 */
export function regionGlow(reliability: number | null): { intensity: number } | null {
  if (reliability === null || reliability === undefined) return null
  return { intensity: Math.min(1, Math.max(0, reliability)) }
}
