/**
 * 공부 데이터 웹 검수 API — /v1/review (투트랙 세트 ③).
 *
 * 큐는 blind(발화만 — 제안·타인 표 없음, 앵커링 방지). 적용은 서버의 GOLD 유일문
 * (apply_review_batch)이 판정한다 — 프론트는 표만 나른다.
 */

export interface ReviewQueueItem {
  episode_id: string
  teacher_prompt: string
  lang: string
  origin_channel: string
}

export interface ReviewQueue {
  reviewer: string
  total_reviewable: number
  my_done: number
  items: ReviewQueueItem[]
}

export interface ReviewApplyResult {
  labeled: number
  rejected: number
  unchanged: number
  kappa: number | null
  exemplars_added: number
  message: string
}

export interface ReviewerStat {
  name: string
  votes: number
}

export interface ReviewStatus {
  reviewable_total: number
  ready_total: number
  reviewers: ReviewerStat[]
}

async function _json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `요청 실패 (${res.status})`
    try {
      const j = (await res.json()) as { detail?: string }
      if (j?.detail) detail = j.detail
    } catch {
      /* JSON 아님 — 기본 문구 */
    }
    throw new Error(detail)
  }
  return (await res.json()) as T
}

export async function fetchReviewQueue(reviewer: string, signal?: AbortSignal): Promise<ReviewQueue> {
  const res = await fetch(`/v1/review/queue?reviewer=${encodeURIComponent(reviewer)}`, { signal })
  return _json<ReviewQueue>(res)
}

/** chosen_intent null = "못 쓰는 발화" 폐기 표 */
export async function postReviewVote(input: {
  reviewer: string
  episode_id: string
  chosen_intent: string | null
}): Promise<{ ok: boolean; vote_id: string; updated: boolean }> {
  const res = await fetch('/v1/review/vote', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  })
  return _json(res)
}

export async function applyReview(approvedBy: string): Promise<ReviewApplyResult> {
  const res = await fetch('/v1/review/apply', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ approved_by: approvedBy }),
  })
  return _json<ReviewApplyResult>(res)
}

export async function fetchReviewStatus(signal?: AbortSignal): Promise<ReviewStatus> {
  const res = await fetch('/v1/review/status', { signal })
  return _json<ReviewStatus>(res)
}
