/**
 * 시각 인코딩 규칙 — 설계 문서 §7-5 표 원문 복사 (세션 규칙 6: 바인딩은 이 표를 따른다).
 *
 * | 시각 요소          | 바인딩                                        | 원천  |
 * |-------------------|----------------------------------------------|------|
 * | Node **Size**      | Training Volume (evidence 총량)               | §3   |
 * | Node **Brightness**| **Held-out Accuracy — Arena만이 바꾼다**       | §8   |
 * | Node **Density**   | Evidence Diversity                            | §3-5 |
 * | Node **Pulse**     | Current Activation (지금 추론에 개입 중)        | §5-4 |
 * | **Edge Thickness** | Intent Relation Strength (연관)               | §5-6 |
 * | **Edge Flicker**   | Confusion Rate (혼동)                         | §5-6 |
 * | **Pending Ring**   | 훈련됨·검증 대기                               | §6-5 |
 *
 * - region 색 7종 유지 + 색약 대응: 색 + region 라벨 + 위치(고정 좌표계) 3중 인코딩.
 * - 의미 노드 수 = intent 수(~100). 수천 개 점은 장식 파티클 레이어로 분리(성능 + 정보 정직성).
 *
 * T3.4(뼈대)는 실 데이터 바인딩 전 — 아래 중립값만 쓴다. 절대 규칙 3: brightness의 원천은
 * Arena 결과(heldout_accuracy)뿐이므로, 값이 없는 지금은 전 노드 Dormant(어두움)로 그린다.
 * 값을 지어내지 않는다. 실 바인딩은 T3.5에서 이 모듈을 통해서만 한다.
 */

/** 노드 1개의 시각 속성 — §7-5 표의 노드 행들과 1:1 */
export interface NodeVisual {
  /** Size ← Training Volume (T3.5) */
  size: number
  /** Brightness ← Held-out Accuracy, null = 미측정(Dormant) — Arena만 갱신 (원칙 8) */
  brightness: number
  /** Density ← Evidence Diversity (T3.5) */
  density: number
  /** Pulse ← Current Activation (T3.5) */
  pulse: boolean
  /** Pending Ring ← 훈련됨·검증 대기 (T3.5) */
  pendingRing: boolean
}

/** heldout 미측정(Dormant) 노드의 밝기 — §7-6 Stage 0 "어둡게" */
export const DORMANT_BRIGHTNESS = 0.22

/** T3.4 스켈레톤 기본값: 전 노드 동일 크기·Dormant 밝기 (지어낸 값 없음) */
export const SKELETON_VISUAL: NodeVisual = {
  size: 0.035,
  brightness: DORMANT_BRIGHTNESS,
  density: 0,
  pulse: false,
  pendingRing: false,
}
