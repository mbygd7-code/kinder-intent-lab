/**
 * Gym API 클라이언트 — 강화하기(§7-4) → 세션 → 응답 제출 → evidence 적재 (§8-1).
 * dev에선 vite 프록시(/v1 → 127.0.0.1:8000).
 */
export type GymMode = 'guess_my_intent' | 'choose_right_meaning' | 'correction_drill'

export interface GymItem {
  item_id: string
  utterance: string
  candidate_intents: string[]
  brain_guess: string | null
}

export interface GymSessionStart {
  session_id: string
  pack_id: string
  mode: GymMode
  items: GymItem[]
}

export interface GymResult {
  item_id: string
  chosen_intent: string
  brain_guess?: string | null
  recovery_turns: number
}

export interface GymSubmitReport {
  session_id: string
  episodes_created: number
  evidence_created: number
  by_type: Record<string, number>
  // T4.3 finalize 필드 — 제출 시 집계·pending 설정 결과(§6-7 [5][6]). 구버전 응답엔 부재
  node_intent?: string | null
  episodes_aggregated?: number
  label_states?: Record<string, number>
  pending_set?: boolean
}

/** HTTP 상태를 보존하는 API 오류 — 409(이미 제출된 세션) 같은 의미 있는 상태를 UI가 구분한다 */
export class GymApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'GymApiError'
  }
}

export interface PackOrigin {
  node: string
  region?: string | null
  diagnosis?: string[] | null
  target_confusion?: string | null
}

// --- T4.2/T4.3 Challenge Pack 생성 (§7-4 강화하기 → 서버측 진단 기반 실 pack) ---

export interface PackTargetEdge {
  from_true: string
  to_predicted: string
}

export interface GeneratedPack {
  pack_id: string
  origin: { trigger: string; node: string | null; region: string | null; diagnosis?: string[] }
  strategy: string[] // A_DATA_COVERAGE | B_HUMAN_EVIDENCE | C_CONFUSION | D_MODEL 부분집합
  target_edges?: PackTargetEdge[]
  items: number
  difficulty_curve?: 'easy' | 'medium' | 'medium_to_hard' | 'hard' | 'adversarial'
  persona_mix?: string[] // persona 클러스터 미적재면 부재 — 지어내지 않고 부재로 표시
  delivery_modes: string[]
  expected_yield?: {
    node_priority?: number
    human_evidence?: number
    contrast_pairs?: number
    coverage_orders?: number
  }
}

export interface PackWorkOrder {
  order_id: string
  order_type: string
  status: string
  requested_items: number
}

export interface GeneratedPackResponse {
  pack: GeneratedPack
  diagnosis_codes: string[]
  strategy: string[]
  needs_human: boolean // false ⇒ A/D 전용(훈련 세션 없이 Foundry 작업지시만)
  node_priority: number
  work_orders: PackWorkOrder[]
}

export async function generatePack(
  nodeIntent: string,
  trigger = 'observatory_click',
): Promise<GeneratedPackResponse> {
  const res = await fetch('/v1/gym/pack', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ node_intent: nodeIntent, trigger }),
  })
  if (!res.ok) throw new Error(`gym pack ${res.status}`)
  return (await res.json()) as GeneratedPackResponse
}

export async function openGymSession(
  trainerRef: string,
  mode: GymMode,
  origin: PackOrigin,
): Promise<GymSessionStart> {
  const res = await fetch('/v1/gym/session', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ trainer_ref: trainerRef, mode, origin }),
  })
  if (!res.ok) throw new Error(`gym session ${res.status}`)
  return (await res.json()) as GymSessionStart
}

export async function submitGymSession(
  sessionId: string,
  results: GymResult[],
): Promise<GymSubmitReport> {
  const res = await fetch(`/v1/gym/session/${sessionId}/submit`, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify({ results }),
  })
  if (!res.ok) throw new GymApiError(`gym submit ${res.status}`, res.status)
  return (await res.json()) as GymSubmitReport
}
