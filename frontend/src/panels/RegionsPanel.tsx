/**
 * 좌측 패널 — Zoom 0 개요 + Zoom 1 Region 상세 (§7-1·§7-2, 레퍼런스 좌측 패널).
 *
 * 상단: KTIB global(마지막 Arena run만 — null="—", 원칙 8). 하단: 7 region 리스트(고정 순서),
 * 선택 시 §7-2 상세(Reliability/Coverage/Gold·Synthetic 분리/Top Weak Nodes).
 * Gold/Synthetic 카운트는 실데이터. Reliability·Coverage·Weak 랭킹은 Arena 산출 —
 * 미실행이면 "—"로, 지어내지 않는다(정보 정직성).
 */
import { useBrainStore } from '../brain3d/store'
import { REGIONS, type RegionId } from '../brain3d/regions'

const SUBTITLE: Record<RegionId, string> = {
  PLAY: 'Imagination · Exploration',
  OBSERVATION: 'Attention · Awareness',
  DOCUMENT: 'Records · Expression',
  VISUAL: 'Patterns · Images',
  COMMUNICATION: 'Language · Sharing',
  OPERATION: 'Logic · Execution',
  REFLECTION: 'Self-Awareness · Growth',
}

const TOP_WEAK_N = 4
const pct = (v: number | null | undefined) => (v == null ? '—' : `${Math.round(v * 100)}%`)
const num = (v: number) => v.toLocaleString('en-US')

export function RegionsPanel() {
  const brain = useBrainStore((s) => s.brain)
  const ktib = useBrainStore((s) => s.ktibGlobal)
  const selectedRegionId = useBrainStore((s) => s.selectedRegionId)
  const selectRegion = useBrainStore((s) => s.selectRegion)

  const regionOf = (id: RegionId) => brain?.regions.find((r) => r.region === id) ?? null
  const detail = selectedRegionId ? regionOf(selectedRegionId) : null

  // Top Weak Nodes: Arena heldout이 없으면 훈련량 낮은 순(대체 정렬) — 명시 라벨
  const weakNodes = selectedRegionId
    ? (brain?.nodes ?? [])
        .filter((n) => n.region === selectedRegionId)
        .slice()
        .sort((a, b) => a.evidence_total - b.evidence_total)
        .slice(0, TOP_WEAK_N)
    : []

  return (
    <aside className="side-panel side-panel-left">
      <section className="panel-card">
        <div className="panel-eyebrow">OVERALL BRAIN SCORE</div>
        <div className="brain-score">
          <span className="brain-score-value">{ktib == null ? '—' : Math.round(ktib * 100)}</span>
          <span className="brain-score-max">/100</span>
        </div>
        <div className="panel-note">
          {ktib == null ? 'Arena 미실행 — 측정 전' : 'KTIB First Intent Accuracy'}
        </div>
      </section>

      <section className="panel-card">
        <div className="panel-head">
          <span className="panel-eyebrow">BRAIN REGIONS</span>
          <span className="panel-count">7 Areas</span>
        </div>
        <ul className="region-list">
          {REGIONS.map((r) => {
            const data = regionOf(r.id)
            const active = selectedRegionId === r.id
            return (
              <li key={r.id}>
                <button
                  type="button"
                  className={`region-row${active ? ' region-row-active' : ''}`}
                  style={active ? { borderColor: r.color } : undefined}
                  onClick={() => selectRegion(active ? null : r.id)}
                >
                  <span className="region-swatch" style={{ backgroundColor: r.color }} />
                  <span className="region-row-text">
                    <span className="region-row-name">{r.label}</span>
                    <span className="region-row-sub">{SUBTITLE[r.id]}</span>
                  </span>
                  <span className="region-row-score" style={{ color: r.color }}>
                    {pct(data?.reliability)}
                  </span>
                </button>
              </li>
            )
          })}
        </ul>
      </section>

      {detail && (
        <section className="panel-card region-detail">
          <div className="panel-head">
            <span className="panel-eyebrow">{selectedRegionId} REGION</span>
          </div>
          <dl className="stat-rows">
            <div className="stat-row">
              <dt>Region Reliability</dt>
              <dd>{pct(detail.reliability)}</dd>
            </div>
            <div className="stat-row">
              <dt>Coverage</dt>
              <dd className="muted">—</dd>
            </div>
            <div className="stat-row">
              <dt>Gold Episodes</dt>
              <dd>{num(detail.gold_evidence)}</dd>
            </div>
            <div className="stat-row">
              <dt>Synthetic Episodes</dt>
              <dd className="muted-strong">{num(detail.synthetic_evidence)}</dd>
            </div>
          </dl>
          <div className="panel-subhead">
            TOP WEAK NODES
            <span className="panel-hint">Arena 측정 후 랭킹 · 현재 훈련량 낮은 순</span>
          </div>
          {weakNodes.length === 0 ? (
            <div className="panel-empty">이 region에 노드가 없습니다</div>
          ) : (
            <ul className="weak-list">
              {weakNodes.map((n) => (
                <li key={n.node_id} className="weak-row">
                  <span className="weak-name">{n.intent_id}</span>
                  <span className="weak-score muted">{pct(n.heldout_accuracy)}</span>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}
    </aside>
  )
}
