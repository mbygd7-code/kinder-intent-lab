/**
 * 즉석 문답(Live Quiz) API 클라이언트 — 자유 발화 라이브 추론 + 사람 판정 제출.
 *
 * 1) POST /v1/intent/infer (mode=gym): 사람이 타이핑한 발화만 담은 최소 Core 요청.
 *    훈련 메타데이터(정답 등)는 절대 넣지 않는다 — 판정은 추론이 끝난 뒤 별도 채널(2)로만
 *    전달된다(절대 규칙 5, runtime §3-0).
 * 2) POST /v1/gym/live/feedback: 사람 판정 → 훈련 evidence 또는 출제(벤치마크 후보) 큐.
 *
 * dev에선 vite 프록시(/v1 → 127.0.0.1:8000).
 */

function hex(n = 12): string {
  const bytes = new Uint8Array(n)
  crypto.getRandomValues(bytes)
  return Array.from(bytes, (b) => (b % 16).toString(16)).join('')
}

// --- 1) 라이브 추론 ---

export interface LiveCandidate {
  intent_id: string
  domain: string | null
  score: number
}

export interface LiveInferResult {
  request_id: string
  top_intent: string | null
  confidence: number | null
  decision: string
  clarification?: { question?: string | null } | null
  candidates: LiveCandidate[]
}

/** 최소 Core 요청 — 화면·행동 컨텍스트 없는 순수 타이핑 문답. 정답·훈련 메타는 없다(규칙 5). */
export function buildInferRequest(utterance: string, trainerRef: string): Record<string, unknown> {
  return {
    request_id: 'REQ_LIVEQ_' + hex(),
    schema_version: 'core-1.0',
    mode: 'gym',
    session: {
      session_id: 'LIVEQ_' + hex(),
      surface_type: 'workspace',
      conversation_history: [],
    },
    prompt: { text: utterance, lang: 'ko', input_method: 'typed' },
    workspace_context: { objects: [], selection: [] },
    recent_actions: [],
    teacher_context: { teacher_ref: trainerRef, profile: {} },
  }
}

/** 후보를 점수순 상위 max개로 — 화면에 3~4개만 보여준다(§7-4 브리핑 톤). */
export function topCandidates(
  raw: { intent_id: string; domain?: string | null; score?: number }[] | undefined,
  max = 4,
): LiveCandidate[] {
  return (raw ?? [])
    .filter((c) => c.intent_id)
    .map((c) => ({ intent_id: c.intent_id, domain: c.domain ?? null, score: c.score ?? 0 }))
    .sort((a, b) => b.score - a.score)
    .slice(0, max)
}

export async function inferLive(utterance: string, trainerRef: string): Promise<LiveInferResult> {
  const res = await fetch('/v1/intent/infer', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(buildInferRequest(utterance, trainerRef)),
  })
  if (!res.ok) throw new Error(`infer ${res.status}`)
  const body = await res.json()
  return {
    request_id: body.request_id,
    top_intent: body.top_intent ?? null,
    confidence: body.confidence ?? null,
    decision: body.decision,
    clarification: body.clarification ?? null,
    candidates: topCandidates(body.intent_candidates),
  }
}

// --- 2) 사람 판정 제출 ---

export type LivePurpose = 'training' | 'benchmark'

export interface LiveFeedbackPayload {
  feedback_id: string
  trainer_ref: string
  utterance: string
  chosen_intent?: string | null
  brain_top_intent?: string | null
  intent_candidates?: string[]
  /** 판정 대상 추론 run id — 서버가 evidence에 남겨 inference_logs와 잇는다(감사 추적) */
  inference_request_id?: string | null
  suggest_new_intent?: boolean
  purpose: LivePurpose
}

export interface LiveFeedbackReport {
  kind: 'confirmation' | 'correction' | 'benchmark_queued' | 'atlas_queued'
  episode_id?: string
  evidence_created?: number
  episodes_aggregated?: number
  label_states?: Record<string, number>
  pending_set?: boolean
  node_intent?: string
  benchmark_queue_size?: number
  atlas_queue_id?: string
}

/** HTTP 상태 보존 오류 — 409(중복/오염)를 UI가 구분해 정직하게 안내한다. */
export class LiveApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'LiveApiError'
  }
}

export function newFeedbackId(): string {
  return 'fb_' + hex(16)
}

export async function submitLiveFeedback(
  payload: LiveFeedbackPayload,
): Promise<LiveFeedbackReport> {
  const res = await fetch('/v1/gym/live/feedback', {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(payload),
  })
  if (!res.ok) {
    let detail = `live feedback ${res.status}`
    try {
      const body = await res.json()
      if (typeof body?.detail === 'string') detail = body.detail
    } catch {
      /* 본문 없는 오류 — 상태 코드만으로 안내 */
    }
    throw new LiveApiError(detail, res.status)
  }
  return (await res.json()) as LiveFeedbackReport
}
