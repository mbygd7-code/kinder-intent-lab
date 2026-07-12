/**
 * 시험지 2차 검수 대기열 API 클라이언트 (§3-3·§8-2) — 웹 1~5 평점 검수.
 *
 * A가 문항+1~5 제출 → 대기 → 다른 컴퓨터의 B가 blind로 1~5 → 서로 다른 2명 ∧ 가중 kappa ≥
 * 임계면 등록. kappa·총점은 서버가 계산해 응답으로 준다(프론트는 표시만 — B는 A 점수를 못 본다).
 */

/** HTTP 상태 보존 오류 — 409(중복 검수·같은 사람 등)를 UI가 구분 (gym.ts 패턴) */
export class KtibReviewApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message)
    this.name = 'KtibReviewApiError'
  }
}

async function jsonOrThrow<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `요청 실패 (${res.status})`
    try {
      const j = (await res.json()) as { detail?: string }
      if (j?.detail) detail = j.detail
    } catch {
      /* JSON 아님 — 기본 문구 유지 */
    }
    throw new KtibReviewApiError(detail, res.status)
  }
  return (await res.json()) as T
}

async function postJson<T>(url: string, body: unknown): Promise<T> {
  return jsonOrThrow<T>(
    await fetch(url, {
      method: 'POST',
      headers: { 'content-type': 'application/json' },
      body: JSON.stringify(body),
    }),
  )
}

// --- 타입 (백엔드 observatory.py pydantic과 1:1) ---

export interface CandidateItemIn {
  intent: string
  teacher_prompt: string
  rating: number // 작성자 A 1~5
}

export interface BatchSummary {
  batch_id: string
  created_by: string
  status: 'AWAITING_SECOND' | 'SECOND_DONE' | 'REGISTERED'
  item_count: number
  agreement_kappa: number | null
  accepted_count: number
  registerable: boolean
  ktib_version: string | null
}

export interface PendingItem {
  item_id: string
  intent: string
  teacher_prompt: string
  // rating_a는 오지 않는다 — anti-anchoring(§8-2)
}

export interface PendingBatch {
  batch_id: string
  created_by: string
  item_count: number
  items: PendingItem[]
}

export interface CandidateList {
  pending: PendingBatch[]
  mine: BatchSummary[]
}

export interface RegisterResult {
  ok: boolean
  dry_run: boolean
  inserted: number
  skipped_duplicate: number
  eligible_total: number
  ktib_version: string | null
  message: string
}

// --- 호출 ---

export function createCandidateBatch(
  reviewer: string,
  items: CandidateItemIn[],
): Promise<BatchSummary> {
  return postJson('/v1/observatory/ktib/candidates', { reviewer, items })
}

export async function listCandidates(reviewer: string): Promise<CandidateList> {
  const q = new URLSearchParams({ reviewer }).toString()
  return jsonOrThrow<CandidateList>(await fetch(`/v1/observatory/ktib/candidates?${q}`))
}

export function submitSecondReview(
  batchId: string,
  reviewer: string,
  ratings: Array<{ item_id: string; rating: number }>,
): Promise<BatchSummary> {
  return postJson(`/v1/observatory/ktib/candidates/${encodeURIComponent(batchId)}/review`, {
    reviewer,
    ratings,
  })
}

export function registerCandidateBatch(
  batchId: string,
  reviewer: string,
  commit: boolean,
): Promise<RegisterResult> {
  return postJson(`/v1/observatory/ktib/candidates/${encodeURIComponent(batchId)}/register`, {
    reviewer,
    commit,
  })
}
