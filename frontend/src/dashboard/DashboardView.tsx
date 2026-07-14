/**
 * 브레인 운영실(대시보드) 컨테이너 — "들어온다 → 배운다 → 증명한다 → 확장된다" 한 화면.
 *
 * 데이터: GET /v1/observatory/dashboard 를 [reloadNonce]로 재조회(즉석 문답·검수 완료 시 갱신).
 * 재조회 일시 실패는 기존 데이터를 유지한다(BrainScreen live 유지와 동일 원칙) — 최초 실패만
 * 미연결 카드. 실력 카드의 원천은 store(/brain)라 카드별로 자기 원천의 상태만 반영한다.
 */
import { useEffect, useState } from 'react'

import { type Dashboard, fetchDashboard } from '../api/dashboard'
import { useBrainStore } from '../brain3d/store'
import { ExpansionStory } from './ExpansionStory'
import { InflowStreams } from './InflowStreams'
import { IntentTable } from './IntentTable'
import { ReviewInbox } from './ReviewInbox'
import { RunTimeline } from './RunTimeline'
import { Scoreboard } from './Scoreboard'

type Status = 'loading' | 'ready' | 'error'

export function DashboardView() {
  const reloadNonce = useBrainStore((s) => s.reloadNonce)
  const webglOk = useBrainStore((s) => s.webglOk)
  const setViewMode = useBrainStore((s) => s.setViewMode)
  const [data, setData] = useState<Dashboard | null>(null)
  const [status, setStatus] = useState<Status>('loading')

  useEffect(() => {
    const ctrl = new AbortController()
    fetchDashboard(ctrl.signal)
      .then((payload) => {
        // 형식 방어 — 다른 응답이 섞이면 부분 렌더로 지어내지 않고 미연결 처리
        if (payload == null || typeof payload !== 'object' || !('scoreboard' in payload)) {
          throw new Error('dashboard 응답 형식 아님')
        }
        setData(payload)
        setStatus('ready')
      })
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return
        console.warn('dashboard API 실패:', err)
        // 이미 그린 실데이터가 있으면 유지(다소 이전 상태가 정직) — 최초 실패만 에러 카드
        setStatus((prev) => (prev === 'ready' ? 'ready' : 'error'))
      })
    return () => ctrl.abort()
  }, [reloadNonce])

  return (
    <div className="dashboard" role="region" aria-label="브레인 운영실">
      <div className="dash-bg" aria-hidden />
      <div className="dash-inner">
        <header className="dash-header dash-rise" style={{ animationDelay: '0ms' }}>
          <div>
            <h2 className="dash-title">BRAIN OPS</h2>
            <p className="dash-subtitle">
              브레인 운영실 — 데이터가 들어오고 · 뇌가 배우고 · 시험으로 증명하고 · 계속
              확장됩니다
            </p>
          </div>
          {webglOk && (
            <button type="button" className="dash-btn" onClick={() => setViewMode('3d')}>
              🧠 3D 뇌로 보기
            </button>
          )}
        </header>

        {status === 'error' && data == null && (
          <div className="dash-card dash-empty">
            <p className="dash-empty-title">운영실 데이터를 불러오지 못했어요</p>
            <p className="dash-card-sub">백엔드 연결을 확인해 주세요 — 연결되면 자동으로 채워집니다.</p>
          </div>
        )}
        {status === 'loading' && data == null && (
          <div className="dash-card dash-empty">
            <p className="dash-card-sub">불러오는 중…</p>
          </div>
        )}

        {data != null && (
          <>
            <div className="dash-rise" style={{ animationDelay: '60ms' }}>
              <Scoreboard data={data} />
            </div>
            <div className="dash-rise" style={{ animationDelay: '120ms' }}>
              <InflowStreams data={data} />
            </div>
            <div className="dash-rise" style={{ animationDelay: '180ms' }}>
              <RunTimeline data={data} />
            </div>
            <div className="dash-grid dash-grid-2 dash-rise" style={{ animationDelay: '240ms' }}>
              <ExpansionStory data={data} />
              <ReviewInbox data={data} />
            </div>
            <div className="dash-rise" style={{ animationDelay: '300ms' }}>
              <IntentTable data={data} />
            </div>
          </>
        )}
      </div>
    </div>
  )
}
