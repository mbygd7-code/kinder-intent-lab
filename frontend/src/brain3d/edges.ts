/**
 * 혼동 edge 인코더 — §7-5 Edge Thickness(state)·Edge Flicker(confusion_rate) 유일 원천.
 *
 * §5-6 confusion_edges 실데이터만 그린다:
 * - 두께·불투명 = state 사다리(hypothesized < observed < confirmed, 단조)
 * - 점선 = rate 미측정(Arena 전) — 가설을 실측처럼 그리지 않는다(정직)
 * - 깜빡임 Hz = 측정된 confusion_rate ∝ (rate 0 = 소등 — 혼동이 사라졌다)
 * - 미측정 = slate 저휘도(구조물과 같은 색계지만 노드에 앵커·방향 그라디언트로 구분),
 *   측정 = amber 경고 톤 — 측정 edge의 광량은 Arena 산출이라 밝아도 정직하다
 *   (노드 brightness와 같은 정직성 등급). 대량 가산 레이어가 아니라 블룸 오염 위험 낮음.
 * 곡선: 12분할 베지어, 중점을 뇌 중심 반대쪽으로 리프트 — 뇌 내부를 관통하지 않게.
 */
import type { ConfusionState, GlobalConfusionEdge } from '../api/observatory'
import type { EdgeDisplayMode } from './store'

export interface EdgeVisual {
  width: number // §7-5 Edge Thickness ← state 랭크 (px, Line2 screen-space)
  dashed: boolean // rate null(미측정) → 점선
  opacity: number
  flickerHz: number // §7-5 Edge Flicker ← rate. 0 = 깜빡임 없음(미측정 또는 rate 0)
  colorFrom: string // 방향 그라디언트: 출발(어둡게) → 도착(밝게)
  colorTo: string
}

export const EDGE_WIDTH: Record<ConfusionState, number> = {
  hypothesized: 1,
  observed: 1.8,
  confirmed: 2.6,
}
export const EDGE_OPACITY: Record<ConfusionState, number> = {
  hypothesized: 0.16,
  observed: 0.34,
  confirmed: 0.5,
}
/** 선택 노드 인접 edge 강조 배수 (버킷 분리 렌더) */
export const EDGE_SELECT_BOOST = 1.6

const SLATE_FROM = '#3a465c'
const SLATE_TO = '#8fa3c4'
const AMBER_FROM = '#7c4a03'
const AMBER_TO = '#f59e0b'

const clamp01 = (v: number) => Math.min(1, Math.max(0, v))

export function edgeVisual(e: {
  state: ConfusionState
  confusion_rate: number | null
}): EdgeVisual {
  const measured = e.confusion_rate !== null && e.confusion_rate !== undefined
  const rate = measured ? clamp01(e.confusion_rate as number) : 0
  return {
    width: EDGE_WIDTH[e.state] ?? 1,
    dashed: !measured,
    opacity: EDGE_OPACITY[e.state] ?? EDGE_OPACITY.hypothesized,
    // rate 0은 "혼동이 소등된" 측정 결과 — 깜빡이지 않는다 (§7-5 flicker 소등)
    flickerHz: measured && rate > 0 ? 0.6 + 2.4 * rate : 0,
    colorFrom: measured ? AMBER_FROM : SLATE_FROM,
    colorTo: measured ? AMBER_TO : SLATE_TO,
  }
}

/**
 * 표시 필터(§5-6 UX 결정): focus = 확정(state) ∪ 측정(rate) ∪ 선택 노드 인접.
 * all = 전체(147개 가설 지형까지) — HUD 토글.
 */
export function visibleEdges(
  edges: readonly GlobalConfusionEdge[],
  mode: EdgeDisplayMode,
  selectedIntentId: string | null,
): GlobalConfusionEdge[] {
  if (mode === 'all') return [...edges]
  return edges.filter(
    (e) =>
      e.state === 'confirmed' ||
      (e.confusion_rate !== null && e.confusion_rate !== undefined) ||
      (selectedIntentId !== null &&
        (e.from_intent === selectedIntentId || e.to_intent === selectedIntentId)),
  )
}

// ---------- 연결 사유 정보 (선택 노드의 상대 노드 위 칩, §5-6) ----------

/** edge 출처(origin) 한글 — "왜 이 연결이 존재하는가"의 근원 (교사용 쉬운 말) */
export const ORIGIN_KO: Record<string, string> = {
  SKEPTIC: 'AI가 헷갈릴 수 있다고 짚음',
  CONSENSUS_DISAGREEMENT: '라벨 의견이 갈렸음',
  GYM_CORRECTION: '훈련 중 바로잡음',
  ARENA_MATRIX: '시험에서 실제로 틀림',
}

export const STATE_KO: Record<ConfusionState, string> = {
  hypothesized: '추측',
  observed: '관찰됨',
  confirmed: '확인됨',
}

export interface EdgeInfo {
  /** 방향 설명 — 선택 노드 기준 유출/유입 */
  direction: string
  /** 상태 + 출처 — 연결이 존재하는 이유 */
  reason: string
  /** 측정치 — rate 없으면 "측정 전"(지어내지 않음) */
  rate: string
  measured: boolean
}

/**
 * 선택 노드 기준의 연결 사유 텍스트. §5-6 필드만 사용 — 없는 값은 표기하지 않는다.
 * from_true=선택: "선택 발화가 상대로 오인될 수 있다", to_predicted=선택: 그 반대.
 */
export function edgeInfo(
  e: GlobalConfusionEdge,
  selectedIntentId: string,
): EdgeInfo {
  const outgoing = e.from_intent === selectedIntentId
  const measured = e.confusion_rate !== null && e.confusion_rate !== undefined
  return {
    direction: outgoing ? '이 의도로 착각할 수 있음' : '이 의도에서 착각되어 들어옴',
    reason: `${STATE_KO[e.state] ?? e.state} · ${ORIGIN_KO[e.origin ?? ''] ?? e.origin ?? '출처 미상'}`,
    rate: measured ? `헷갈린 비율 ${Math.round((e.confusion_rate as number) * 100)}%` : '시험 전',
    measured,
  }
}

export interface EdgeCurve {
  edge: GlobalConfusionEdge
  visual: EdgeVisual
  /** 13개 점(12분할 베지어) — 뇌 중심 반대쪽으로 리프트된 곡선 */
  points: Array<readonly [number, number, number]>
  /** 선택 노드 인접 여부 — 강조 버킷 분리용 */
  touchesSelected: boolean
}

/**
 * 폴리라인 위 t∈[0,1] 지점 — 전파 펄스의 이동 경로 샘플러.
 * t는 edge의 의미 방향(from→to)을 따른다 — 펄스 흐름 = 혼동 방향(§5-6).
 */
export function samplePolyline(
  points: ReadonlyArray<readonly [number, number, number]>,
  t: number,
): [number, number, number] {
  const segs = points.length - 1
  const x = Math.min(0.9999, Math.max(0, t)) * segs
  const i = Math.floor(x)
  const f = x - i
  const a = points[i]
  const b = points[i + 1]
  return [
    a[0] + (b[0] - a[0]) * f,
    a[1] + (b[1] - a[1]) * f,
    a[2] + (b[2] - a[2]) * f,
  ]
}

const BRAIN_CENTROID: readonly [number, number, number] = [0, -0.05, 0]
const CURVE_SEGMENTS = 12
const LIFT_RATIO = 0.18

/** 미배치 intent(노드 없음)의 edge는 그리지 않는다 — 허공 지오메트리 금지. */
export function buildEdgeCurves(
  edges: readonly GlobalConfusionEdge[],
  posByIntent: ReadonlyMap<string, readonly [number, number, number]>,
  selectedIntentId: string | null,
): { curves: EdgeCurve[]; skipped: number } {
  const curves: EdgeCurve[] = []
  let skipped = 0
  for (const edge of edges) {
    const a = posByIntent.get(edge.from_intent)
    const b = posByIntent.get(edge.to_intent)
    if (!a || !b) {
      skipped++
      continue
    }
    const mid = [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2]
    const out = [
      mid[0] - BRAIN_CENTROID[0],
      mid[1] - BRAIN_CENTROID[1],
      mid[2] - BRAIN_CENTROID[2],
    ]
    const outLen = Math.hypot(out[0], out[1], out[2]) || 1
    const dist = Math.hypot(b[0] - a[0], b[1] - a[1], b[2] - a[2])
    const lift = LIFT_RATIO * dist
    const ctrl = [
      mid[0] + (out[0] / outLen) * lift,
      mid[1] + (out[1] / outLen) * lift,
      mid[2] + (out[2] / outLen) * lift,
    ]
    const points: Array<readonly [number, number, number]> = []
    for (let s = 0; s <= CURVE_SEGMENTS; s++) {
      const t = s / CURVE_SEGMENTS
      const u = 1 - t
      // 2차 베지어: u²·a + 2ut·ctrl + t²·b
      points.push([
        u * u * a[0] + 2 * u * t * ctrl[0] + t * t * b[0],
        u * u * a[1] + 2 * u * t * ctrl[1] + t * t * b[1],
        u * u * a[2] + 2 * u * t * ctrl[2] + t * t * b[2],
      ])
    }
    curves.push({
      edge,
      visual: edgeVisual(edge),
      points,
      touchesSelected:
        selectedIntentId !== null &&
        (edge.from_intent === selectedIntentId || edge.to_intent === selectedIntentId),
    })
  }
  return { curves, skipped }
}
