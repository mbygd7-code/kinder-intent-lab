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
        <span className="persona-title">혼동 관계 (§5-6)</span>
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
          가설 {hypothesized} · 측정 {payload.measured_count}
          {mode === 'focus' && ' — 노드를 선택하면 그 노드의 가설 edge가 보여요'}
        </p>
      ) : (
        <p className="persona-empty">
          {status === 'error' ? '혼동 edge 미연결' : '혼동 edge 불러오는 중…'}
        </p>
      )}
    </div>
  )
}
