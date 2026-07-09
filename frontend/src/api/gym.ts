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
}

export interface PackOrigin {
  node: string
  region?: string | null
  diagnosis?: string[] | null
  target_confusion?: string | null
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
  if (!res.ok) throw new Error(`gym submit ${res.status}`)
  return (await res.json()) as GymSubmitReport
}
