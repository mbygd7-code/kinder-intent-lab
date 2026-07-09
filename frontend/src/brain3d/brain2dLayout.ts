/**
 * 2D region map 고정 레이아웃 — §7-5 fallback의 의미 좌표계 (§5-10 준용).
 *
 * 2D 좌표는 3D 고정 좌표계의 사시상 배치(전두=왼쪽)를 스키마틱하게 옮긴 **고정값**이다 —
 * 저사양 사용자에게는 이 뷰가 유일한 지도이므로 위치 안정성 보장은 3D와 동일하게 적용된다.
 * brain2d.test.ts가 스냅샷·비겹침·점 포함 불변식을 잠근다. 임의 수정 금지.
 */
import { fmix32, fnv1a } from './hash'
import type { RegionId } from './regions'

/** region별 2D 고정 좌표 (스키마틱 사시상 뷰, 전두=왼쪽 — 3D 해부학 배치와 동일 방향) */
export const POS_2D: Record<RegionId, readonly [number, number]> = {
  PLAY: [-0.62, -0.55],
  OBSERVATION: [0.42, -0.62],
  DOCUMENT: [-0.85, 0.1],
  VISUAL: [0.85, -0.05],
  COMMUNICATION: [-0.28, 0.28],
  OPERATION: [0.3, 0.42],
  REFLECTION: [0.72, 0.85],
}

export const REGION_R = 0.26 // region 원 반지름
export const DOT_SPREAD = 0.2 // 노드 점 산포 반경 (< REGION_R − 최대 점 크기: 점이 원을 벗어나지 않게)
export const DOT_R = 0.018 // 기본 점 반지름
export const DOT_R_SELECTED = 0.035 // 선택 점 반지름 (+stroke 0.006/2)

/** nodeId 해시 → region 원 안 결정론 2D 배치 (각도·반경 해시 독립 — 뭉침 방지) */
export function dot2d(nodeId: string, region: RegionId): [number, number] {
  const angle = (fmix32(fnv1a(nodeId)) / 0xffffffff) * 2 * Math.PI
  const radius = DOT_SPREAD * Math.sqrt(fmix32(fnv1a(`${nodeId}#r`)) / 0xffffffff)
  const [cx, cy] = POS_2D[region]
  return [cx + radius * Math.cos(angle), cy + radius * Math.sin(angle)]
}
