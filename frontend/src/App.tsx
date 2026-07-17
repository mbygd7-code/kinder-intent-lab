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
 * 톱바 우측 CTA는 📋 할 일(TODO) 하나로 통합(2026-07-17 사용자 결정) — 시험지 작성·즉석
 * 문답은 대시보드 카드와 TODO 안내에서 진입한다. TODO는 실데이터로 "지금 뭘 하면 목표에
 * 가장 빨리 가는가"를 단계별로 안내한다(todoSteps.ts).
 */
import { BrainScreen } from './brain3d/BrainScreen'
import { effectiveViewMode, useBrainStore } from './brain3d/store'
import { HelpOverlay } from './panels/HelpOverlay'
import { ExamUploadModal } from './panels/ExamUpload'
import { KtibReviewModal } from './panels/KtibReviewModal'
import { GoldReviewPanel } from './panels/GoldReviewPanel'
import { IntentCatalogPanel } from './panels/IntentCatalogPanel'
import { LiveQuizPanel } from './panels/LiveQuizPanel'
import { NodePanel } from './panels/NodePanel'
import { RegionsPanel } from './panels/RegionsPanel'
import { stageWithNumber } from './panels/terms'
import { TodoPanel } from './panels/TodoPanel'

function App() {
  const ktib = useBrainStore((s) => s.ktibGlobal)
  const brainVersion = useBrainStore((s) => s.brainVersion)
  const brainStage = useBrainStore((s) => s.brainStage)
  const brainStageName = useBrainStore((s) => s.brainStageName)
  const bumpReload = useBrainStore((s) => s.bumpReload)
  // 모달 상태는 store — 톱바와 대시보드 액션 버튼이 같은 진입점을 공유한다
  const helpOpen = useBrainStore((s) => s.helpOpen)
  const helpTab = useBrainStore((s) => s.helpTab)
  const liveQuizOpen = useBrainStore((s) => s.liveQuizOpen)
  const goldReviewOpen = useBrainStore((s) => s.goldReviewOpen)
  const closeGoldReview = useBrainStore((s) => s.closeGoldReview)
  const intentCatalogOpen = useBrainStore((s) => s.intentCatalogOpen)
  const closeIntentCatalog = useBrainStore((s) => s.closeIntentCatalog)
  const reviewOpen = useBrainStore((s) => s.reviewOpen)
  const closeReview = useBrainStore((s) => s.closeReview)
  const examUploadOpen = useBrainStore((s) => s.examUploadOpen)
  const closeExamUpload = useBrainStore((s) => s.closeExamUpload)
  const closeLiveQuiz = useBrainStore((s) => s.closeLiveQuiz)
  const todoOpen = useBrainStore((s) => s.todoOpen)
  const openTodo = useBrainStore((s) => s.openTodo)
  const closeTodo = useBrainStore((s) => s.closeTodo)
  const openHelp = useBrainStore((s) => s.openHelp)
  const closeHelp = useBrainStore((s) => s.closeHelp)
  // 대시보드 모드면 좌우 패널을 걷는다 — 대시보드가 전폭 스크롤 페이지가 된다
  const viewMode = useBrainStore((s) => s.viewMode)
  const webglOk = useBrainStore((s) => s.webglOk)
  const dashboardMode = effectiveViewMode({ viewMode, webglOk }) === 'dashboard'
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
          {/* 📋 할 일 — 실데이터 기반 "지금 뭘 하면 목표에 빨리 가는가" 안내(2026-07-17).
              시험지 작성·즉석 문답 진입은 이 안내와 대시보드 카드가 담당한다 */}
          <button type="button" className="cta-live" onClick={openTodo}>
            📋 TODO
          </button>
          <button type="button" className="header-help" onClick={() => openHelp('service')}>
            ❔ 도움말
          </button>
        </div>
      </header>

      <div className="observatory-body">
        {!dashboardMode && <RegionsPanel />}
        <BrainScreen />
        {!dashboardMode && <NodePanel />}
      </div>

      {todoOpen && <TodoPanel onClose={closeTodo} />}
      {liveQuizOpen && (
        <LiveQuizPanel
          onClose={closeLiveQuiz}
          onComplete={bumpReload} // 훈련 evidence 저장 시에만 — 노드 size/pending 갱신(§6-7 [6])
        />
      )}
      {intentCatalogOpen && <IntentCatalogPanel onClose={closeIntentCatalog} />}
      {goldReviewOpen && (
        <GoldReviewPanel
          onClose={closeGoldReview}
          onApplied={bumpReload} // GOLD 확정 성공 시 — 대시보드·뇌 수치 재조회
        />
      )}
      {reviewOpen && (
        <KtibReviewModal
          onClose={closeReview}
          onComplete={bumpReload} // 등록(commit) 성공 시 뇌 상태 refetch
        />
      )}
      {examUploadOpen && (
        <ExamUploadModal
          onClose={() => {
            closeExamUpload()
            bumpReload() // 업로드 확정 후 닫혔을 수 있다 — 시험지 수치 재조회
          }}
          onOpenHelp={() => {
            closeExamUpload()
            openHelp('exam')
          }}
        />
      )}
      {helpOpen && <HelpOverlay onClose={closeHelp} initialTab={helpTab} />}
    </main>
  )
}

export default App
