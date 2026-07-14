/**
 * 채점 실행 버튼 — 대시보드 PERFORMANCE 헤더와 시험지 검수 모달이 공유하는 단일 진입점.
 *
 * 클릭 → PIN 입력(오클릭 방지 자물쇠, 서버 검증) → 백그라운드 채점 시작 → 4초 간격 상태
 * 폴링 → 완료 시 bumpReload(뇌·대시보드 갱신) + 점수 표시. 다른 곳에서 시작된 채점도
 * 마운트 시 상태 조회로 이어서 보여준다. 실패(401/409/실행 에러)는 서버 문구 그대로 —
 * 지어내지 않는다.
 */
import { useCallback, useEffect, useRef, useState } from 'react'

import { fetchArenaStatus, startArenaRun } from '../api/arenaOps'
import { useBrainStore } from '../brain3d/store'

type Phase = 'idle' | 'pin' | 'starting' | 'running' | 'done' | 'error'

const POLL_MS = 4000

export function ArenaRunButton() {
  const bumpReload = useBrainStore((s) => s.bumpReload)
  const [phase, setPhase] = useState<Phase>('idle')
  const [pin, setPin] = useState('')
  const [msg, setMsg] = useState<string | null>(null)
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null)

  const stopPoll = () => {
    if (pollRef.current != null) {
      clearInterval(pollRef.current)
      pollRef.current = null
    }
  }

  const settle = useCallback(
    (status: { error: string | null; last_run: { accuracy: number | null } | null }) => {
      stopPoll()
      if (status.error) {
        setPhase('error')
        setMsg(`채점 실패 — ${status.error}`)
        return
      }
      const acc = status.last_run?.accuracy
      setPhase('done')
      setMsg(acc == null ? '채점 완료' : `채점 완료 · ${(acc * 100).toFixed(1)}%`)
      bumpReload() // 뇌(밝기)·대시보드 수치 refetch — 반영은 Arena 경로가 이미 커밋했다
    },
    [bumpReload],
  )

  // 마운트 시 1회 — 다른 화면/사람이 시작한 채점이 돌고 있으면 이어서 표시
  useEffect(() => {
    const ctrl = new AbortController()
    fetchArenaStatus(ctrl.signal)
      .then((s) => {
        if (s.running) setPhase('running')
      })
      .catch(() => undefined) // 상태 채널 실패는 버튼을 막지 않는다
    return () => ctrl.abort()
  }, [])

  // running 동안 폴링
  useEffect(() => {
    if (phase !== 'running') return
    pollRef.current = setInterval(() => {
      fetchArenaStatus()
        .then((s) => {
          if (!s.running) settle(s)
        })
        .catch(() => undefined) // 일시 실패 — 다음 틱에 재시도
    }, POLL_MS)
    return stopPoll
  }, [phase, settle])

  const submit = async () => {
    if (!pin.trim()) return
    setPhase('starting')
    setMsg(null)
    try {
      const message = await startArenaRun(pin.trim())
      setPin('')
      setPhase('running')
      setMsg(message)
    } catch (err) {
      setPhase('pin') // 입력을 유지한 채 서버 문구 그대로 보여준다 (401/409)
      setMsg(err instanceof Error ? err.message : String(err))
    }
  }

  const busy = phase === 'starting' || phase === 'running'
  return (
    <span className="arena-run-wrap">
      <button
        type="button"
        className="dash-btn dash-btn-primary"
        disabled={busy}
        onClick={() => setPhase((p) => (p === 'pin' ? 'idle' : 'pin'))}
        title="동결된 시험지로 뇌를 채점해요 — 실행하면 점수·밝기가 갱신됩니다 (운영자 비밀번호 필요)"
      >
        {phase === 'running' ? '⏳ 채점 중…' : phase === 'starting' ? '시작 중…' : '🎯 채점 실행'}
      </button>
      {phase === 'pin' && (
        <span className="arena-pin-pop">
          <input
            className="arena-pin-input"
            type="password"
            inputMode="numeric"
            placeholder="비밀번호"
            aria-label="채점 비밀번호"
            value={pin}
            autoFocus
            onChange={(e) => setPin(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') void submit()
              if (e.key === 'Escape') setPhase('idle')
            }}
          />
          <button type="button" className="dash-btn dash-btn-primary" onClick={() => void submit()}>
            확인
          </button>
          <button type="button" className="dash-btn" onClick={() => setPhase('idle')}>
            취소
          </button>
        </span>
      )}
      {msg && (
        <span
          className={`arena-msg${phase === 'error' ? ' arena-msg-error' : ''}${phase === 'done' ? ' arena-msg-done' : ''}`}
          role="status"
        >
          {msg}
        </span>
      )}
    </span>
  )
}
