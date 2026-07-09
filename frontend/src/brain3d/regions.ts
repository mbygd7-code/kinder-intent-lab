/**
 * 7 Brain Region — v1 고정 의미 좌표계 (§5-10).
 *
 * "7개 region은 v1 고정 — 3D 의미 좌표계의 안정성을 위해서다(노드가 늘어도 PLAY는 항상
 *  같은 자리). region 내부 노드 수는 성장한다. region 신설·개편 = 온톨로지 major 버전."
 *
 * §7-5 3중 인코딩(색약 대응): region 색 7종 + region 라벨 + 위치(고정 좌표계).
 * id·순서는 백엔드 app/core/ontology.py CANONICAL_DOMAINS와 1:1 — regions.test.ts가 잠근다.
 * 좌표를 바꾸는 것은 의미 좌표계 변경이므로 설계 승인 없이 수정 금지 (테스트 스냅샷이 막는다).
 */

export type RegionId =
  | 'PLAY'
  | 'OBSERVATION'
  | 'DOCUMENT'
  | 'VISUAL'
  | 'COMMUNICATION'
  | 'OPERATION'
  | 'REFLECTION'

export interface BrainRegion {
  id: RegionId
  /** 표시 라벨 — 3중 인코딩 ② */
  label: string
  /** region 색 — 3중 인코딩 ① (디자인 레퍼런스 팔레트) */
  color: string
  /** v1 고정 중심 좌표 — 3중 인코딩 ③ (§5-10) */
  center: readonly [number, number, number]
  /** 노드 산포 반경 — region 간 최소 중심거리/2 미만 (구름 비겹침, layout.test) */
  radius: number
}

// 해부학적 로브 배치 (brainShape.ts 실루엣 내부, 사시상 뷰 = 레퍼런스 이미지):
// PLAY=전두상부, DOCUMENT=전두하부, OBSERVATION=두정, VISUAL=후두,
// COMMUNICATION/OPERATION=좌/우 측두, REFLECTION=소뇌·뇌간.
// 2026-07-09 사용자 승인 리스타일로 1회 이동(분산 셸 → 단일 뇌 내부) — 이후 다시 고정.
// 쌍거리 최소 0.616(VISUAL–REFLECTION) ≥ 2×radius(0.56) — 비겹침 테스트 유지.
export const REGIONS: readonly BrainRegion[] = [
  { id: 'PLAY', label: 'Play', color: '#4ade80', center: [0, 0.55, 0.62], radius: 0.28 },
  { id: 'OBSERVATION', label: 'Observation', color: '#38bdf8', center: [0, 0.62, -0.42], radius: 0.28 },
  { id: 'DOCUMENT', label: 'Document', color: '#fb923c', center: [0, -0.08, 0.8], radius: 0.28 },
  { id: 'VISUAL', label: 'Visual', color: '#c084fc', center: [0, 0.12, -0.82], radius: 0.28 },
  { id: 'COMMUNICATION', label: 'Communication', color: '#f472b6', center: [-0.42, -0.1, 0.3], radius: 0.28 },
  { id: 'OPERATION', label: 'Operation', color: '#facc15', center: [0.42, -0.1, 0.3], radius: 0.28 },
  { id: 'REFLECTION', label: 'Reflection', color: '#22d3ee', center: [0.0, -0.48, -0.68], radius: 0.28 },
] as const

export const REGION_BY_ID = Object.fromEntries(
  REGIONS.map((r) => [r.id, r]),
) as Record<RegionId, BrainRegion>
