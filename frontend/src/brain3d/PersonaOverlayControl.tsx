/**
 * T5.4 Persona Overlay 토글/범례 (§7-6) — brain-hud에 뜨는 DOM 컨트롤.
 *
 * 정직성 규칙:
 * - 클러스터가 없으면(=Persona Discovery 미실행) 토글을 숨기지 않고 **비활성 + 사유 표기**.
 * - prior는 §5-5 사전 배수(측정 정확도 아님) — 범례에 명시하고, prior_cap을 함께 보여
 *   시각 강조가 무한한 영향으로 읽히지 않게 한다.
 * - 절대 규칙 3: 오버레이는 부가 채널 — 노드 밝기(Arena held-out 정확도)는 오버레이
 *   ON에서도 encodings.ts 값 그대로다. 범례에도 그렇게 적는다.
 */
import { BOOST_COLOR, DAMP_COLOR } from './personaOverlay'
import { useBrainStore } from './store'

export function PersonaOverlayControl() {
  const overlay = useBrainStore((s) => s.personaOverlay)
  const status = useBrainStore((s) => s.personaOverlayStatus)
  const clusterId = useBrainStore((s) => s.overlayClusterId)
  const setOverlayCluster = useBrainStore((s) => s.setOverlayCluster)

  const clusters = overlay?.clusters ?? []
  const canToggle = status === 'ready' && clusters.length > 0
  const current = clusters.find((c) => c.cluster_id === clusterId) ?? null
  const on = current !== null

  return (
    <div className="persona-card">
      <div className="persona-head">
        <span className="persona-title">선생님 성향 렌즈</span>
        <button
          type="button"
          className="view-toggle persona-toggle"
          disabled={!canToggle}
          aria-pressed={on}
          onClick={() => setOverlayCluster(on ? null : clusters[0].cluster_id)}
        >
          {on ? '렌즈 끄기' : '렌즈 켜기'}
        </button>
      </div>

      {!canToggle && (
        <p className="persona-empty">
          {status === 'loading' && '성향 정보를 불러오는 중…'}
          {status === 'error' && '성향 정보를 못 불러왔어요 — 연결을 확인해 주세요'}
          {status === 'ready' && '아직 성향 분석 전이에요 — 선생님들의 훈련 기록이 쌓이면 열려요'}
        </p>
      )}

      {on && overlay && current && (
        <div className="persona-legend">
          <label className="persona-cluster-pick">
            <span>성향 그룹</span>
            <select
              value={current.cluster_id}
              onChange={(e) => setOverlayCluster(e.target.value)}
            >
              {clusters.map((c) => (
                <option key={c.cluster_id} value={c.cluster_id}>
                  {c.cluster_id}
                </option>
              ))}
            </select>
          </label>
          <div className="persona-legend-row">
            <span>선생님 수</span>
            {/* member_count null = 미집계 — 0으로 지어내지 않는다 */}
            <strong>{current.member_count == null ? '—' : current.member_count}</strong>
          </div>
          <div className="persona-legend-row">
            <span className="persona-swatch" style={{ backgroundColor: BOOST_COLOR }} />
            <span>이 성향 선생님들이 자주 쓰는 의도</span>
          </div>
          <div className="persona-legend-row">
            <span className="persona-swatch" style={{ backgroundColor: DAMP_COLOR }} />
            <span>이 성향 선생님들이 드물게 쓰는 의도</span>
          </div>
          <div className="persona-legend-row">
            <span className="persona-swatch persona-swatch-neutral" />
            <span>표시 없음 = 특별한 치우침 없음</span>
          </div>
          <p className="persona-cap-note">
            참고용 경향 표시일 뿐 정확도(밝기)가 아니에요 — 영향 크기도{' '}
            {overlay.prior_cap}까지로 제한돼요. 점의 밝기는 렌즈와 무관하게 그대로예요.
          </p>
        </div>
      )}
    </div>
  )
}
