/**
 * GET /v1/observatory/dashboard 클라이언트 — 브레인 운영실 집계 (읽기 전용).
 *
 * 정직성 계약(백엔드 app/api/dashboard.py와 쌍):
 * - 측정 전·비교 불가 값은 null — 화면은 '—'로 그린다 (0으로 위장 금지)
 * - 기준선(하한·목표)은 payload.config가 원천 — 프론트 하드코딩 금지(절대 규칙 1)
 * - 유입 시계열의 0만이 실제 0(그날 도착 없음)
 */

export interface DashboardConfig {
  critical_surface_min_items: number
  gold_low_threshold: number
  first_intent_accuracy_target: number
  min_agreement_kappa: number
}

export interface CurrentKtib {
  version: string
  episode_count: number
}

export interface Scoreboard {
  ktib_registered_total: number
  ktib_pending_total: number
  critical_met: number
  critical_total: number
  current_ktib: CurrentKtib | null
  train_total: number
  gold_total: number
  channels: Record<string, number>
  human_evidence: Record<string, number>
  review_awaiting_batches: number
}

export interface DailyCount {
  day: string
  count: number
}

export interface Stream {
  total: number
  last_days: DailyCount[]
}

export interface Inflow {
  foundry: Stream
  human_teaching: Stream
  exam: Stream
  shadow: Stream
}

export interface InflowDelta {
  train_episodes: number
  gold: number
  benchmark_episodes: number
}

export interface RunPoint {
  run_id: string
  created_at: string
  accuracy: number | null
  item_count: number | null
  ece: number | null
  delta_pp: number | null
  inflow_since_prev: InflowDelta | null
  region_regressions: string[]
  critical_worse: string[]
  critical: Record<string, unknown> | null
}

export interface Performance {
  axis: { ktib_version: string; model_version: string } | null
  runs: RunPoint[]
  attribution_ready: boolean
}

export interface OntologyVersionRow {
  version: string
  change_type: string | null
  created_at: string | null
}

export interface Expansion {
  intent_count: number
  positive_examples_total: number
  ontology_version: string
  unknown_pool: number
  ambiguous: number
  atlas_queue_pending: number
  ontology_versions: OntologyVersionRow[]
}

export interface ReviewBatch {
  batch_id: string
  created_by: string
  status: 'AWAITING_SECOND' | 'SECOND_DONE' | 'REGISTERED'
  item_count: number
  agreement_kappa: number | null
  ktib_version: string | null
  created_at: string | null
}

export interface IntentRow {
  intent_id: string
  region: string
  is_critical: boolean
  exam_registered: number
  exam_pending: number
  gap_to_floor: number | null
  train: number
  gold: number
  positive_examples: number
  heldout_accuracy: number | null
  evidence_total: number
}

export interface Dashboard {
  config: DashboardConfig
  scoreboard: Scoreboard
  inflow: Inflow
  performance: Performance
  expansion: Expansion
  review_inbox: ReviewBatch[]
  intents: IntentRow[]
}

export async function fetchDashboard(signal?: AbortSignal): Promise<Dashboard> {
  const res = await fetch('/v1/observatory/dashboard', { signal })
  if (!res.ok) throw new Error(`dashboard API ${res.status}`)
  return (await res.json()) as Dashboard
}
