/**
 * Zoom 0 — 메인 화면 (§7-1): 시스템의 첫 화면이자 모든 작업의 진입점.
 * 중앙 수치 = KTIB global First Intent Accuracy(마지막 Arena 실행 기준, API ktib_global).
 * Arena 미실행이면 null → "—" 표기 — 값을 지어내지 않는다(원칙 8).
 *
 * T5.4: 수치 곁에 §7-6 성장 스테이지(brain_stage_name, 전부 Arena 산출)를 함께 띄운다.
 * 미측정 뇌 = "Dormant"(아직 잠들어 있는 뇌) — 0점·실패가 아니라 깨어나기 전 상태로 읽힌다.
 * Stage 4(Cross-Region Flow)는 설계 미정의로 백엔드가 내보내지 않아 3 → 5로 건너뛴다.
 */
import { useState } from 'react'

import { BrainScreen } from './brain3d/BrainScreen'
import { useBrainStore } from './brain3d/store'
import { HelpOverlay } from './panels/HelpOverlay'
import { NodePanel } from './panels/NodePanel'
import { RegionsPanel } from './panels/RegionsPanel'
import { stageWithNumber } from './panels/terms'

function App() {
  const ktib = useBrainStore((s) => s.ktibGlobal)
  const brainVersion = useBrainStore((s) => s.brainVersion)
  const brainStage = useBrainStore((s) => s.brainStage)
  const brainStageName = useBrainStore((s) => s.brainStageName)
  const [helpOpen, setHelpOpen] = useState(false)
  // §7-6 스테이지 — 값은 Arena 산출 그대로, 표시만 교사용 한글(terms.ts)
  const stageLabel = stageWithNumber(brainStage, brainStageName)
  return (
    <main className="observatory">
      <header className="observatory-header">
        {/* 도움말 — 헤더 우측 상단 (어떤 상태에서도 열림) */}
        <button type="button" className="header-help" onClick={() => setHelpOpen(true)}>
          ❔ 도움말
        </button>
        <h1>
          킨더 브레인
          <span className="header-sub">
            선생님 말뜻을 배우는 AI{brainVersion ? ` · ${brainVersion}` : ''}
          </span>
        </h1>
        <div className="ktib-global">
          <span className="ktib-value">
            {ktib == null ? '—%' : `${(ktib * 100).toFixed(1)}%`}
          </span>
          {/* §7-6 — API 도착 전엔 스테이지도 표기하지 않는다(지어내지 않음) */}
          {stageLabel != null && (
            <span className="ktib-stage" title="성장 단계 — 시험 결과로만 바뀌어요">
              {stageLabel}
            </span>
          )}
          <span className="ktib-note">
            말뜻 알아맞히기 점수 (공식 시험 기준)
            {ktib == null
              ? stageLabel != null
                ? ' · 아직 시험 전 — 뇌가 잠들어 있어요'
                : ' · 아직 시험 전'
              : ''}
          </span>
        </div>
      </header>
      <div className="observatory-body">
        <RegionsPanel />
        <BrainScreen />
        <NodePanel />
      </div>
      {helpOpen && <HelpOverlay onClose={() => setHelpOpen(false)} />}
    </main>
  )
}

export default App
