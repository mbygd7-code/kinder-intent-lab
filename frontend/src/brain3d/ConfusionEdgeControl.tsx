/**
 * 혼동 관계 HUD 칩 — §5-6 edge 표시 모드 토글 + 정직 카운트.
 *
 * '가설 N · 측정 M'은 실 DB 상태 그대로다 — 전부 가설(측정 0)이어도 그것이 현황이다.
 * focus(기본) = 확정 ∪ 측정 ∪ 선택 노드 인접, all = 가설 지형 전체.
 */
import { useBrainStore } from './store'

export function ConfusionEdgeControl() {
  const payload = useBrainStore((s) => s.confusionEdges)
  const status = useBrainStore((s) => s.confusionEdgesStatus)
  const mode = useBrainStore((s) => s.edgeDisplayMode)
  const setMode = useBrainStore((s) => s.setEdgeDisplayMode)

  const hypothesized = payload ? payload.total - payload.measured_count : null
  return (
    <div className="persona-card edge-card">
      <div className="persona-head">
        <span className="persona-title">헷갈리는 의도 연결</span>
        <button
          type="button"
          className="view-toggle persona-toggle"
          disabled={!payload}
          aria-pressed={mode === 'all'}
          onClick={() => setMode(mode === 'all' ? 'focus' : 'all')}
        >
          {mode === 'all' ? '핵심만 보기' : '전체 보기'}
        </button>
      </div>
      {payload ? (
        <p className="persona-empty edge-counts">
          추측 {hypothesized}개 · 시험으로 확인 {payload.measured_count}개
          {mode === 'focus' && ' — 점을 누르면 그 의도의 연결이 보여요'}
        </p>
      ) : (
        <p className="persona-empty">
          {status === 'error' ? '연결 정보를 못 불러왔어요' : '연결 정보를 불러오는 중…'}
        </p>
      )}
    </div>
  )
}
