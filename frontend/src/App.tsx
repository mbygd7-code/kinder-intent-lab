/**
 * Zoom 0 — 메인 화면 (§7-1): 시스템의 첫 화면이자 모든 작업의 진입점.
 * 중앙 수치 = KTIB global First Intent Accuracy(마지막 Arena 실행 기준).
 * Arena 미실행 상태에서는 값을 지어내지 않고 "—"로 표기한다(원칙 8: 정확도의 원천은 Arena뿐).
 */
import { BrainScreen } from './brain3d/BrainScreen'

function App() {
  return (
    <main className="observatory">
      <header className="observatory-header">
        <h1>KINDER INTENT BRAIN</h1>
        <div className="ktib-global">
          <span className="ktib-value">—%</span>
          <span className="ktib-note">KTIB First Intent Accuracy · Arena 미실행</span>
        </div>
      </header>
      <BrainScreen />
    </main>
  )
}

export default App
