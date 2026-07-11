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
 * ── 코드 리뷰 체크리스트 (원칙 8 / 절대 규칙 3) ─────────────────────────────
 * [ ] brightness 계산(visualFromNode의 heldout 분기)은 **이 파일에만** 존재한다
 * [ ] brightness의 유일한 입력은 API의 heldout_accuracy(=Arena 전용 컬럼)다
 * [ ] evidence_total/diversity/pending/훈련 이벤트는 brightness에 절대 관여 못 한다
 * [ ] 다른 파일은 NodeVisual.brightness를 **읽기만** 한다 (encodings.checklist.test가 스캔 강제)
 * ────────────────────────────────────────────────────────────────────────
 */

/** Observatory API 노드 데이터 중 인코딩에 쓰는 필드 (src/api/observatory.ts 계약의 부분집합) */
export interface EncodableNode {
  evidence_total: number
  evidence_diversity: number
  heldout_accuracy: number | null
  pending_evaluation: boolean
}

/** 노드 1개의 시각 속성 — §7-5 표의 노드 행들과 1:1 */
export interface NodeVisual {
  /** Size ← Training Volume */
  size: number
  /** Brightness ← Held-out Accuracy, null = 미측정(Dormant) — Arena만 갱신 (원칙 8) */
  brightness: number
  /** Density ← Evidence Diversity [0,1] */
  density: number
  /** Pulse ← Current Activation (store의 pulsing 집합이 구동 — 기본 false) */
  pulse: boolean
  /** Pending Ring ← 훈련됨·검증 대기 */
  pendingRing: boolean
}

/** heldout 미측정(Dormant) 노드의 밝기 — §7-6 Stage 0 "어둡게" */
export const DORMANT_BRIGHTNESS = 0.22

// 표현 상수(프레젠테이션) — 실험 임계값 아님.
// 크기 범위는 파티클 필드와 어울리게 절제 — 노드가 "큰 원판"으로 화면을 지배하지 않게
// (2026-07-11 사용자 피드백). 단조성(§7-5 Size ← Training Volume)은 그대로다.
const SIZE_MIN = 0.022
const SIZE_MAX = 0.048
const SIZE_HALF = 60 // evidence_total이 이 값일 때 크기 절반 지점(포화 곡선)
const BRIGHT_MIN = 0.3 // 측정된 0%도 Dormant보다 아주 살짝 구분
const BRIGHT_MAX = 1.25 // 고정확 노드는 블룸 임계 위 — 밝은 노드가 빛난다

/** T3.4 스켈레톤/데이터 부재 기본값: 동일 크기·Dormant (지어낸 값 없음) */
export const SKELETON_VISUAL: NodeVisual = {
  size: 0.028,
  brightness: DORMANT_BRIGHTNESS,
  density: 0,
  pulse: false,
  pendingRing: false,
}

function clamp01(x: number): number {
  return Math.min(1, Math.max(0, x))
}

/**
 * §7-5 바인딩의 유일한 구현. brightness는 heldout_accuracy만 본다 —
 * 훈련량·다양성·pending은 각자 자기 채널(size/density/ring)로만 나간다.
 */
export function visualFromNode(node: EncodableNode): NodeVisual {
  const t = Math.max(0, node.evidence_total)
  const size = SIZE_MIN + (SIZE_MAX - SIZE_MIN) * (t / (t + SIZE_HALF))
  const brightness =
    node.heldout_accuracy == null
      ? DORMANT_BRIGHTNESS
      : BRIGHT_MIN + (BRIGHT_MAX - BRIGHT_MIN) * clamp01(node.heldout_accuracy)
  return {
    size,
    brightness,
    density: clamp01(node.evidence_diversity),
    pulse: false,
    pendingRing: node.pending_evaluation,
  }
}
