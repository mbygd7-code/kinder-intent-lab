/**
 * 📋 할 일(TODO) 패널 — "지금 뭘 하면 목표에 가장 빨리 가는가" (2026-07-17 사용자 요청).
 *
 * 원천: dashboard(문항·GOLD·채점 이력) + review/status(검수 대기·2인 표) + store(/brain —
 * 점수·대표 예문). 판정은 todoSteps.ts 순수 엔진 — 채점 사전판정과 같은 신호라서
 * 이 안내를 따라가면 버튼이 순서대로 켜진다. 실패 시 미연결을 정직하게 표시(지어내지 않음).
 * 액션 버튼은 기존 store 모달 진입점을 재사용한다(패널을 닫고 해당 창을 연다).
 */
import { useEffect, useState } from 'react'

import { type Dashboard, fetchDashboard } from '../api/dashboard'
import { fetchReviewStatus, type ReviewStatus } from '../api/review'
import { useBrainStore } from '../brain3d/store'
import { ArenaRunButton } from '../dashboard/ArenaRunButton'
import { computeTodoSteps, type TodoAction, type TodoStep } from './todoSteps'

const ACTION_LABEL: Record<Exclude<TodoAction, 'arena'>, string> = {
  examWrite: '📝 시험지 작성',
  examUpload: '⬆ 시험지 업로드',
  liveQuiz: '💬 즉석 문답',
  goldReview: '🔍 공부 검수 (2인 → GOLD)',
}

export function TodoPanel({ onClose }: { onClose: () => void }) {
  const reloadNonce = useBrainStore((s) => s.reloadNonce)
  const dataSource = useBrainStore((s) => s.dataSource)
  const ktib = useBrainStore((s) => s.ktibGlobal)
  const brain = useBrainStore((s) => s.brain)
  const openReview = useBrainStore((s) => s.openReview)
  const openExamUpload = useBrainStore((s) => s.openExamUpload)
  const openGoldReview = useBrainStore((s) => s.openGoldReview)
  const openLiveQuiz = useBrainStore((s) => s.openLiveQuiz)
  const [dash, setDash] = useState<Dashboard | null>(null)
  const [review, setReview] = useState<ReviewStatus | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const ctrl = new AbortController()
    Promise.all([fetchDashboard(ctrl.signal), fetchReviewStatus(ctrl.signal)])
      .then(([d, r]) => {
        if (d == null || typeof d !== 'object' || !('scoreboard' in d)) {
          throw new Error('dashboard 형식 아님')
        }
        setDash(d)
        setReview(r)
        setFailed(false)
      })
      .catch(() => {
        if (!ctrl.signal.aborted) setFailed(true)
      })
    return () => ctrl.abort()
  }, [reloadNonce])

  const exemplarTotal = brain?.nodes.reduce((a, n) => a + n.exemplar_count, 0) ?? 0
  const steps: TodoStep[] | null =
    dash && review
      ? computeTodoSteps({
          examTotal: dash.scoreboard.ktib_registered_total,
          frozen: dash.scoreboard.current_ktib != null,
          reviewableTotal: review.reviewable_total,
          readyTotal: review.ready_total,
          goldTotal: dash.scoreboard.gold_total,
          exemplarTotal,
          runCount: dash.performance.runs.length,
          score: ktib,
          target: dash.config.first_intent_accuracy_target,
        })
      : null
  const doneCount = steps?.filter((s) => s.state === 'done').length ?? 0

  // 액션 → 기존 모달 진입점 (TODO를 닫고 해당 창을 연다 — 모달 중첩 방지)
  const go = (a: Exclude<TodoAction, 'arena'>) => {
    onClose()
    if (a === 'examWrite') openReview()
    else if (a === 'examUpload') openExamUpload()
    else if (a === 'goldReview') openGoldReview()
    else openLiveQuiz()
  }

  return (
    <div className="gym-backdrop" role="dialog" aria-label="할 일">
      <div className="gym-modal">
        <div className="gym-head">
          <strong className="gym-title">
            📋 지금 할 일 {steps ? `— ${doneCount}/${steps.length} 단계 완료` : ''}
          </strong>
          <button type="button" className="gym-close" aria-label="닫기" onClick={onClose}>
            ✕
          </button>
        </div>

        {steps && dash && (
          <p className="help-note">
            목표 <strong>{(dash.config.first_intent_accuracy_target * 100).toFixed(0)}%</strong> ·
            현재 <strong>{ktib == null ? '측정 전' : `${(ktib * 100).toFixed(1)}%`}</strong> —
            아래 순서대로 하면 가장 빨리 도달해요. 지금은{' '}
            <strong>{steps.find((s) => s.state === 'current')?.title ?? '목표 달성!'}</strong>{' '}
            차례예요.
          </p>
        )}

        {failed && (
          <p className="help-upload-err">
            ⚠ 상태를 불러오지 못했어요 — 백엔드 연결을 확인해 주세요. 연결되면 자동으로 채워져요.
          </p>
        )}
        {!failed && steps == null && <p className="help-note">불러오는 중…</p>}

        {steps && (
          <ol className="todo-list">
            {steps.map((s, idx) => (
              <li key={s.key} className={`todo-step todo-step-${s.state}`}>
                <div className="todo-step-head">
                  <span className="todo-num" aria-hidden>
                    {s.state === 'done' ? '✓' : idx + 1}
                  </span>
                  <strong className="todo-title">{s.title}</strong>
                  {s.state === 'current' && <span className="todo-now">← 지금 할 일</span>}
                </div>
                <p className="dash-card-sub todo-detail">{s.detail}</p>
                {s.state === 'current' && (
                  <>
                    <p className="todo-why">💡 {s.why}</p>
                    <div className="dash-actions">
                      {s.actions.map((a) =>
                        a === 'arena' ? (
                          <ArenaRunButton key="arena" />
                        ) : a === 'liveQuiz' && dataSource !== 'live' ? null : (
                          <button
                            key={a}
                            type="button"
                            className="dash-btn dash-btn-primary"
                            onClick={() => go(a)}
                          >
                            {ACTION_LABEL[a]}
                          </button>
                        ),
                      )}
                    </div>
                  </>
                )}
              </li>
            ))}
          </ol>
        )}
      </div>
    </div>
  )
}
