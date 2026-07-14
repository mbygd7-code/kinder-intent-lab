/**
 * 채점(Arena) 웹 트리거 클라이언트 — POST /arena/run (PIN) + GET /arena/status 폴링.
 *
 * 서버 가드(백엔드 app/api/arena_ops.py와 쌍): PIN 불일치 401, mock provider·중복 실행 409.
 * 에러 detail은 그대로 사용자에게 보여줄 수 있는 한국어 문장이다.
 */

export interface ArenaLastRun {
  run_id: string
  accuracy: number | null
  item_count: number | null
  created_at: string | null
}

export interface ArenaStatus {
  running: boolean
  started_at: string | null
  error: string | null
  last_run: ArenaLastRun | null
}

export async function startArenaRun(pin: string): Promise<string> {
  const res = await fetch('/v1/observatory/arena/run', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pin }),
  })
  const body = await res.json().catch(() => null)
  if (!res.ok) {
    throw new Error(body?.detail ?? `채점 시작 실패 (${res.status})`)
  }
  return body?.message ?? '채점을 시작했어요'
}

export async function fetchArenaStatus(signal?: AbortSignal): Promise<ArenaStatus> {
  const res = await fetch('/v1/observatory/arena/status', { signal })
  if (!res.ok) throw new Error(`arena status ${res.status}`)
  return (await res.json()) as ArenaStatus
}
