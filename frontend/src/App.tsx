/**
 * Zoom 0 — 메인 화면 (§7-1): 시스템의 첫 화면이자 모든 작업의 진입점.
 *
 * 2026-07-12 레이아웃 재정비: 헤더를 1줄 슬림 톱바로 —
 *   좌: 브랜드(영문 제목 + 한글 서브 카피) · 중앙: 북극성 지표(KTIB) · 우: 주요 액션.
 * 수직 공간을 좌우 패널에 돌려준다(패널이 톱바 바로 아래에서 풀 높이로 시작).
 *
 * 중앙 수치 = KTIB global First Intent Accuracy(마지막 Arena 실행 기준, API ktib_global).
 * Arena 미실행이면 null → "—" 표기 — 값을 지어내지 않는다(원칙 8). 캡션이
 * "어두운 게 정상"을 함께 전달한다(§7-6 Dormant는 실패가 아니다 — 구 범례 상태줄 통합).
 *
 * 즉석 문답(§6-7 [4])은 교사의 핵심 학습 행동이라 톱바 CTA로 승격 — 라이브 추론이
 * 필요하므로 실데이터(live)에서만 활성.
 */
import { useState } from 'react'

import { BrainScreen } from './brain3d/BrainScreen'
import { useBrainStore } from './brain3d/store'
import { HelpOverlay } from './panels/HelpOverlay'
import { LiveQuizPanel } from './panels/LiveQuizPanel'
import { NodePanel } from './panels/NodePanel'
import { RegionsPanel } from './panels/RegionsPanel'
import { stageWithNumber } from './panels/terms'

function App() {
  const ktib = useBrainStore((s) => s.ktibGlobal)
  const brainVersion = useBrainStore((s) => s.brainVersion)
  const brainStage = useBrainStore((s) => s.brainStage)
  const brainStageName = useBrainStore((s) => s.brainStageName)
  const dataSource = useBrainStore((s) => s.dataSource)
  const bumpReload = useBrainStore((s) => s.bumpReload)
  const [helpOpen, setHelpOpen] = useState(false)
  const [liveQuizOpen, setLiveQuizOpen] = useState(false)
  // §7-6 스테이지 — 값은 Arena 산출 그대로, 표시만 교사용 한글(terms.ts)
  const stageLabel = stageWithNumber(brainStage, brainStageName)
  return (
    <main className="observatory">
      <header className="topbar">
        <div className="topbar-brand">
          <h1>KINDER BRAIN</h1>
          <span className="topbar-brand-sub">
            선생님 말뜻을 배우는 AI{brainVersion ? ` · ${brainVersion}` : ''}
          </span>
        </div>

        <div className="topbar-score" title="공식 시험(KTIB) 결과로만 갱신되는 점수예요">
          <span className="ktib-value">
            {ktib == null ? '—%' : `${(ktib * 100).toFixed(1)}%`}
          </span>
          <span className="topbar-score-text">
            <span className="topbar-score-label">말뜻 알아맞히기 점수</span>
            {/* null = 시험 전 상태 그대로 — 어두운 뇌를 고장으로 오독하지 않게 안내 */}
            <span className="topbar-score-note">
              {ktib == null ? '아직 시험 전 — 뇌가 어두운 게 정상이에요' : '공식 시험(KTIB) 기준'}
            </span>
          </span>
          {/* §7-6 — API 도착 전엔 스테이지도 표기하지 않는다(지어내지 않음) */}
          {stageLabel != null && (
            <span className="ktib-stage" title="성장 단계 — 시험 결과로만 바뀌어요">
              {stageLabel}
            </span>
          )}
        </div>

        <div className="topbar-actions">
          {/* 즉석 문답 — 라이브 추론 필요: 실데이터(live)에서만 (§6-7 [4]) */}
          {dataSource === 'live' && (
            <button type="button" className="cta-live" onClick={() => setLiveQuizOpen(true)}>
              💬 즉석 문답
            </button>
          )}
          <button type="button" className="header-help" onClick={() => setHelpOpen(true)}>
            ❔ 도움말
          </button>
        </div>
      </header>

      <div className="observatory-body">
        <RegionsPanel />
        <BrainScreen />
        <NodePanel />
      </div>

      {liveQuizOpen && (
        <LiveQuizPanel
          onClose={() => setLiveQuizOpen(false)}
          onComplete={bumpReload} // 훈련 evidence 저장 시에만 — 노드 size/pending 갱신(§6-7 [6])
        />
      )}
      {helpOpen && <HelpOverlay onClose={() => setHelpOpen(false)} />}
    </main>
  )
}

export default App
