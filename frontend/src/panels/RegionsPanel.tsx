/**
 * 좌측 패널 — Zoom 0 개요 + Zoom 1 Region 상세 (§7-1·§7-2, 레퍼런스 좌측 패널).
 *
 * 상단: KTIB global(마지막 Arena run만 — null="—", 원칙 8). 하단: 7 region 리스트(고정 순서),
 * 선택 시 §7-2 상세(Reliability/Coverage/Gold·Synthetic 분리/Top Weak Nodes).
 * Gold/Synthetic 카운트는 실데이터. Reliability·Coverage·Weak 랭킹은 Arena 산출 —
 * 미실행이면 "—"로, 지어내지 않는다(정보 정직성).
 *
 * T5.4 성장 스테이지(§7-6): 뇌 전체 stage 배지 + region별 stage_name + 측정 노드 수.
 * 전부 Arena 산출값 그대로 — 미측정 region은 "Dormant"(잠자는 상태)로, 실패가 아니다.
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
  const hoveredRegionId = useBrainStore((s) => s.hoveredRegionId)
  const setHoveredRegion = useBrainStore((s) => s.setHoveredRegion)

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
        <div className="panel-head">
          <span className="panel-eyebrow">OVERALL BRAIN SCORE</span>
          {/* §7-6 뇌 전체 성장 스테이지 — Arena 산출 그대로, API 전엔 미표기 */}
          {brain?.brain_stage_name != null && (
            <span className="stage-badge">{brain.brain_stage_name}</span>
          )}
        </div>
        <div className="brain-score">
          <span className="brain-score-value">{ktib == null ? '—' : Math.round(ktib * 100)}</span>
          <span className="brain-score-max">/100</span>
        </div>
        <div className="panel-note">
          {ktib == null ? 'Arena 미실행 — 잠에서 깨어나길 기다리는 뇌' : 'KTIB First Intent Accuracy'}
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
            const hovered = hoveredRegionId === r.id
            return (
              <li key={r.id}>
                <button
                  type="button"
                  className={`region-row${active ? ' region-row-active' : ''}${hovered ? ' region-row-hovered' : ''}`}
                  style={active || hovered ? { borderColor: r.color } : undefined}
                  onClick={() => selectRegion(active ? null : r.id)}
                  onMouseEnter={() => setHoveredRegion(r.id)}
                  onMouseLeave={() => setHoveredRegion(null)}
                >
                  <span className="region-swatch" style={{ backgroundColor: r.color }} />
                  <span className="region-row-text">
                    <span className="region-row-name">{r.label}</span>
                    <span className="region-row-sub">{SUBTITLE[r.id]}</span>
                  </span>
                  <span className="region-row-right">
                    <span className="region-row-score" style={{ color: r.color }}>
                      {pct(data?.reliability)}
                    </span>
                    {/* §7-6 region 성장 스테이지 — 미측정=Dormant(실패 아님), API 전 미표기 */}
                    {data?.stage_name != null && (
                      <span className="region-row-stage">{data.stage_name}</span>
                    )}
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
              <dt>Growth Stage</dt>
              {/* §7-6 — Arena 산출 stage_name 그대로 (Stage 4는 백엔드가 내보내지 않는다) */}
              <dd>{`${detail.stage} · ${detail.stage_name}`}</dd>
            </div>
            <div className="stat-row">
              <dt>Measured Nodes</dt>
              {/* heldout 측정된 노드 수 / 전체 — 미측정은 0%가 아니라 '아직 Arena 전' */}
              <dd>{`${detail.measured_count} / ${detail.node_count}`}</dd>
            </div>
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
