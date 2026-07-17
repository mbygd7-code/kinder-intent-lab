/** 의도 목록·표시 수정·변경 제안 API — /v1/ontology. 표시 수정은 PIN 필수(서버 검증). */

export interface IntentItem {
  intent_id: string
  domain: string
  definition: string
  example_count: number
  name_ko: string | null
  description_ko: string | null
}

export interface IntentCatalog {
  ontology_version: string
  total: number
  items: IntentItem[]
}

export interface IntentChangeRequest {
  request_id: string
  intent_id: string | null
  kind: string
  proposal: string
  proposed_by: string
  status: string
  decided_by: string | null
  created_at: string | null
}

async function _json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `요청 실패 (${res.status})`
    try {
      const j = (await res.json()) as { detail?: string }
      if (j?.detail) detail = j.detail
    } catch { /* 기본 문구 */ }
    throw new Error(detail)
  }
  return (await res.json()) as T
}

export const fetchIntentCatalog = async (signal?: AbortSignal): Promise<IntentCatalog> =>
  _json(await fetch('/v1/ontology/intents', { signal }))

export const saveIntentDisplay = async (input: {
  intent_id: string
  pin: string
  edited_by: string
  name_ko?: string | null
  description_ko?: string | null
}): Promise<IntentItem> =>
  _json(await fetch(`/v1/ontology/intents/${encodeURIComponent(input.intent_id)}/display`, {
    method: 'PUT', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  }))

export const submitChangeRequest = async (input: {
  kind: 'DEFINITION' | 'ADD' | 'MOVE' | 'DELETE' | 'OTHER'
  proposal: string
  proposed_by: string
  intent_id?: string | null
}): Promise<IntentChangeRequest> =>
  _json(await fetch('/v1/ontology/change-requests', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  }))

export const fetchChangeRequests = async (signal?: AbortSignal): Promise<IntentChangeRequest[]> =>
  (await _json<{ requests: IntentChangeRequest[] }>(
    await fetch('/v1/ontology/change-requests', { signal }),
  )).requests

/** CSV 일괄: 이름·화면설명만 즉시 반영(PIN). 목록에 없는 id는 서버가 건너뛴다. */
export interface BulkDisplayRow {
  intent_id: string
  name_ko?: string | null
  description_ko?: string | null
}

export interface BulkDisplayResult {
  applied: number
  skipped: { intent_id: string; reason: string }[]
  message: string
}

export const bulkDisplayEdit = async (input: {
  pin: string
  edited_by: string
  rows: BulkDisplayRow[]
}): Promise<BulkDisplayResult> =>
  _json(await fetch('/v1/ontology/intents/display/bulk', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  }))

export const decideChangeRequest = async (input: {
  request_id: string
  pin: string
  decision: 'approve' | 'reject'
  decided_by: string
}): Promise<{ request: IntentChangeRequest; message: string }> =>
  _json(await fetch(`/v1/ontology/change-requests/${encodeURIComponent(input.request_id)}/decide`, {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  }))
