/**
 * Zoom 0 — 메인 화면 (§7-1): 시스템의 첫 화면이자 모든 작업의 진입점.
 * 중앙 수치 = KTIB global First Intent Accuracy(마지막 Arena 실행 기준, API ktib_global).
 * Arena 미실행이면 null → "—" 표기 — 값을 지어내지 않는다(원칙 8).
 */
import { BrainScreen } from './brain3d/BrainScreen'
import { useBrainStore } from './brain3d/store'

function App() {
  const ktib = useBrainStore((s) => s.ktibGlobal)
  const brainVersion = useBrainStore((s) => s.brainVersion)
  return (
    <main className="observatory">
      <header className="observatory-header">
        <h1>KINDER INTENT BRAIN{brainVersion ? ` ${brainVersion}` : ''}</h1>
        <div className="ktib-global">
          <span className="ktib-value">
            {ktib == null ? '—%' : `${(ktib * 100).toFixed(1)}%`}
          </span>
          <span className="ktib-note">
            KTIB First Intent Accuracy{ktib == null ? ' · Arena 미실행' : ''}
          </span>
        </div>
      </header>
      <BrainScreen />
    </main>
  )
}

export default App
