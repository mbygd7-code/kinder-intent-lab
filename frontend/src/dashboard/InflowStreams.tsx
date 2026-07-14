/**
 * B. 데이터 유입 4스트림 — 어디서 데이터가 들어오고 있나 (HF Dataset Card식 출처 투명성).
 *
 * FlowDots는 최근 창에 유입이 실제로 있을 때만 흐른다(정직). 식별은 색+라벨 병행(색 단독 금지).
 * 액션은 전부 기존 흐름 연결 — 새 편집기를 만들지 않는다.
 */
import type { Dashboard, Stream } from '../api/dashboard'
import { useBrainStore } from '../brain3d/store'
import { CountUp } from './viz/CountUp'
import { FlowDots } from './viz/FlowDots'
import { Sparkline } from './viz/Sparkline'

// 고정 순서 카테고리 색(dataviz: 순환 배정 금지) — 기존 앱 region 팔레트 계승.
// CVD 분리·대비 검증 통과(validate_palette). 명도 밴드는 기존 브랜드 우선 — 직접 라벨로 보완.
const STREAM_COLOR = {
  foundry: '#38bdf8',
  human_teaching: '#4ade80',
  exam: '#facc15',
  shadow: '#c084fc',
} as const

function recentSum(s: Stream): number {
  return s.last_days.reduce((a, d) => a + d.count, 0)
}

function StreamCard({
  stream, title, sub, color, children, empty, tip,
}: {
  stream: Stream
  title: string
  sub: string
  color: string
  children?: React.ReactNode
  /** 총량 0일 때의 정직한 안내 문구 */
  empty?: string
  /** 총량 숫자의 호버 설명 */
  tip?: string
}) {
  const recent = recentSum(stream)
  return (
    <article className="dash-card dash-stream">
      <FlowDots active={recent > 0} color={color} />
      <header className="dash-card-label" style={{ color }}>
        {title}
      </header>
      <p className="dash-card-sub">{sub}</p>
      {stream.total === 0 && empty ? (
        <p className="dash-empty-note">{empty}</p>
      ) : (
        <div className="dash-card-row">
          <div>
            <div className="dash-stream-value">
              <CountUp value={stream.total} suffix="건" tip={tip} />
            </div>
            <p
              className="dash-card-sub"
              title={`최근 ${stream.last_days.length}일 동안 새로 도착한 수예요 — 옆 선이 일별 흐름이에요.`}
            >
              최근 {stream.last_days.length}일 <strong>+{recent}</strong>
            </p>
          </div>
          <Sparkline data={stream.last_days.map((d) => d.count)} label={title} color={color} />
        </div>
      )}
      {children && <div className="dash-actions">{children}</div>}
    </article>
  )
}

export function InflowStreams({ data }: { data: Dashboard }) {
  const dataSource = useBrainStore((s) => s.dataSource)
  const webglOk = useBrainStore((s) => s.webglOk)
  const setViewMode = useBrainStore((s) => s.setViewMode)
  const openReview = useBrainStore((s) => s.openReview)
  const openExamUpload = useBrainStore((s) => s.openExamUpload)
  const openLiveQuiz = useBrainStore((s) => s.openLiveQuiz)
  const openHelp = useBrainStore((s) => s.openHelp)
  const { inflow } = data

  return (
    <section aria-label="데이터 유입">
      <h2 className="dash-section-title">
        INFLOW <span>데이터 유입 — 무엇이 들어오고 있나</span>
      </h2>
      <div className="dash-grid dash-grid-4">
        <StreamCard
          stream={inflow.foundry} color={STREAM_COLOR.foundry}
          title="시나리오 공장" sub="컴퓨터 연습문제 · 자동 생성(낮은 등급)"
          tip="컴퓨터가 자동으로 지어낸 연습문제가 지금까지 도착한 총량이에요 — 여러 AI의 교차 검토를 통과해야 저장되고, '컴퓨터 생성' 등급으로 낮게 취급돼요."
        >
          <button type="button" className="dash-btn" onClick={() => openHelp('study')}>
            공부 문항 보기
          </button>
        </StreamCard>

        <StreamCard
          stream={inflow.human_teaching} color={STREAM_COLOR.human_teaching}
          title="선생님 가르침" sub="강화하기 · 즉석 문답(사람 확인 등급)"
          tip="선생님이 강화하기·즉석 문답으로 직접 가르친 데이터의 총량이에요 — 답 하나하나가 뇌의 교과서가 되는, 가장 귀한 유입이에요."
        >
          {/* 즉석 문답은 라이브 추론 필요 — live에서만 (App 톱바와 동일 게이트) */}
          {dataSource === 'live' && (
            <button type="button" className="dash-btn dash-btn-primary" onClick={openLiveQuiz}>
              💬 즉석 문답
            </button>
          )}
          {webglOk && (
            <button type="button" className="dash-btn" onClick={() => setViewMode('3d')}>
              3D에서 강화하기
            </button>
          )}
        </StreamCard>

        <StreamCard
          stream={inflow.exam} color={STREAM_COLOR.exam}
          title="시험지" sub="사람 출제 · 2인 검수 · 등록 후 동결"
          tip="시험지 금고에 등록된 문항의 총량이에요 — 뇌 실력을 재는 용도로만 쓰이고, 공부(훈련)에는 절대 쓰이지 않아요."
        >
          <button type="button" className="dash-btn dash-btn-primary" onClick={openReview}>
            📝 시험지 작성
          </button>
          <button type="button" className="dash-btn dash-btn-primary" onClick={openExamUpload}>
            ⬆ 시험지 업로드
          </button>
          <button type="button" className="dash-btn" onClick={() => openHelp('exam')}>
            양식 · 만들기 안내
          </button>
        </StreamCard>

        <StreamCard
          stream={inflow.shadow} color={STREAM_COLOR.shadow}
          title="교사 실데이터" sub="실서비스 섀도우 수집"
          empty="아직 없음 — 킨더버스 연결(Shadow) 전이에요. 게이트 통과 후 시작됩니다."
        />
      </div>
    </section>
  )
}
