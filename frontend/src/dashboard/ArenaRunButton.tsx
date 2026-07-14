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
  // 사전 판정 — 서버가 준 실행 불가 사유(mock provider·시험지 없음). 있으면 버튼이 회색으로 선다
  const [blocked, setBlocked] = useState<string | null>(null)
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

  // 사전 판정 재조회 — 마운트 1회로 끝내지 않는다: 그 순간 서버가 재시작 중이면 판정을
  // 놓친 채 버튼이 활성으로 남고, 사용자는 PIN까지 넣고서야 409 문구만 보게 된다(실사고).
  // 클릭·제출 실패 시마다 다시 물어 스스로 회복한다.
  const refreshBlocked = useCallback(async (signal?: AbortSignal): Promise<string | null> => {
    try {
      const s = await fetchArenaStatus(signal)
      // 구 서버(runnable 부재)는 기존처럼 활성 — 지어내지 않고 서버 판정만 따른다
      const b = s.runnable === false ? (s.blocked_reason ?? '지금은 채점할 수 없어요') : null
      setBlocked(b)
      return b
    } catch {
      return null // 상태 채널 실패는 버튼을 막지 않는다 — 다음 기회에 재판정
    }
  }, [])

  // 마운트 시 1회 — 진행 중 채점 이어보기 + 사전 판정(실행 불가면 회색 버튼)
  useEffect(() => {
    const ctrl = new AbortController()
    fetchArenaStatus(ctrl.signal)
      .then((s) => {
        if (s.running) setPhase('running')
        setBlocked(s.runnable === false ? (s.blocked_reason ?? '지금은 채점할 수 없어요') : null)
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
    const entered = pin.trim()
    setPin('') // 입력창은 어느 경로로 닫히든 다음에 빈 채로 열린다(비밀번호 잔류 금지)
    setPhase('starting')
    setMsg(null)
    try {
      const message = await startArenaRun(entered)
      setPhase('running')
      setMsg(message)
    } catch (err) {
      setMsg(err instanceof Error ? err.message : String(err)) // 서버 문구 그대로 (401/409)
      // 거절 사유가 사전 판정 조건(mock·시험지 없음)이면 버튼을 회색으로 전환하고
      // 팝오버를 닫는다 — 다시 PIN을 넣어도 소용없는 상태를 열어두지 않는다
      const b = await refreshBlocked()
      setPhase(b ? 'idle' : 'pin') // 잘못된 PIN 등은 팝오버 유지(입력은 이미 비움)
    }
  }

  const closePin = () => {
    setPin('') // 취소·ESC — 입력했던 비밀번호를 지운다
    setPhase('idle')
  }

  const onMainClick = () => {
    if (blocked) {
      setMsg((m) => (m === blocked ? null : blocked)) // 회색 버튼 클릭 = 안내 문구 토글
      return
    }
    setMsg(null)
    setPin('') // 다시 열 때 항상 빈 입력창
    setPhase((p) => (p === 'pin' ? 'idle' : 'pin'))
    // 여는 순간 백그라운드 재판정 — 마운트 때 놓쳤거나 그 사이 서버 상태가 바뀐 경우
    // (예: provider 변경·시험지 등록) 팝오버를 닫고 회색+안내로 정정한다
    void refreshBlocked().then((b) => {
      if (b) {
        setPhase('idle')
        setMsg(b)
      }
    })
  }

  const busy = phase === 'starting' || phase === 'running'
  return (
    <span className="arena-run-wrap">
      <button
        type="button"
        className={`dash-btn dash-btn-primary${blocked ? ' dash-btn-blocked' : ''}`}
        disabled={busy}
        aria-disabled={blocked != null}
        onClick={onMainClick}
        title={
          blocked ??
          '동결된 시험지로 뇌를 채점해요 — 실행하면 점수·밝기가 갱신됩니다 (운영자 비밀번호 필요)'
        }
      >
        {phase === 'running' ? '⏳ 채점 중…' : phase === 'starting' ? '시작 중…' : '🎯 채점 실행'}
      </button>
      {phase === 'pin' && !blocked && (
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
              if (e.key === 'Escape') closePin()
            }}
          />
          <button type="button" className="dash-btn dash-btn-primary" onClick={() => void submit()}>
            확인
          </button>
          <button type="button" className="dash-btn" onClick={closePin}>
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
