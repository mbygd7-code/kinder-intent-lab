/**
 * Zoom 0 — 메인 화면 (§7-1): 시스템의 첫 화면이자 모든 작업의 진입점.
 * 중앙 수치 = KTIB global First Intent Accuracy(마지막 Arena 실행 기준, API ktib_global).
 * Arena 미실행이면 null → "—" 표기 — 값을 지어내지 않는다(원칙 8).
 *
 * T5.4: 수치 곁에 §7-6 성장 스테이지(brain_stage_name, 전부 Arena 산출)를 함께 띄운다.
 * 미측정 뇌 = "Dormant"(아직 잠들어 있는 뇌) — 0점·실패가 아니라 깨어나기 전 상태로 읽힌다.
 * Stage 4(Cross-Region Flow)는 설계 미정의로 백엔드가 내보내지 않아 3 → 5로 건너뛴다.
 */
import { BrainScreen } from './brain3d/BrainScreen'
import { useBrainStore } from './brain3d/store'
import { NodePanel } from './panels/NodePanel'
import { RegionsPanel } from './panels/RegionsPanel'

function App() {
  const ktib = useBrainStore((s) => s.ktibGlobal)
  const brainVersion = useBrainStore((s) => s.brainVersion)
  const brainStage = useBrainStore((s) => s.brainStage)
  const brainStageName = useBrainStore((s) => s.brainStageName)
  return (
    <main className="observatory">
      <header className="observatory-header">
        <h1>KINDER INTENT BRAIN{brainVersion ? ` ${brainVersion}` : ''}</h1>
        <div className="ktib-global">
          <span className="ktib-value">
            {ktib == null ? '—%' : `${(ktib * 100).toFixed(1)}%`}
          </span>
          {/* §7-6 — API 도착 전엔 스테이지도 표기하지 않는다(지어내지 않음) */}
          {brainStageName != null && (
            <span className="ktib-stage" title="§7-6 성장 스테이지 — Arena 산출">
              {brainStage != null ? `Stage ${brainStage} · ` : ''}
              {brainStageName}
            </span>
          )}
          <span className="ktib-note">
            KTIB First Intent Accuracy
            {ktib == null
              ? brainStageName != null
                ? ' · Arena 미실행 — 뇌가 아직 잠들어 있어요'
                : ' · Arena 미실행'
              : ''}
          </span>
        </div>
      </header>
      <div className="observatory-body">
        <RegionsPanel />
        <BrainScreen />
        <NodePanel />
      </div>
    </main>
  )
}

export default App
