/**
 * 우측 패널 — Zoom 2 Node 상세 + Weakness Diagnosis Engine (§7-3, 레퍼런스 우측 패널).
 *
 * 실데이터: 노드의 evidence 지표(총량/gold/다양성/exemplar) + **WHY-WEAK 4축 실계산**(T4.1,
 * /v1/observatory/node/{intent}/diagnosis) — 데이터 없는 축은 "—"(지어내지 않음).
 * mock(labeled): 방향성 혼동 목록만 — confusion_edges(§5-6) 미적재 구간이라 "미리보기·mock".
 */
import { useEffect, useMemo, useState } from 'react'

import { openGymSession, type GymMode, type GymSessionStart } from '../api/gym'
import { fetchNodeDiagnosis, type DiagnosisAxis, type NodeDiagnosis } from '../api/observatory'
import { REGION_BY_ID, type RegionId } from '../brain3d/regions'
import { useBrainStore } from '../brain3d/store'
import { goldDataLevel, mockDiagnosis, type WeakLevel } from './diagnosis'
import { GymOverlay } from './GymOverlay'
import { GYM_MODE_LABEL_KO, labelOf } from './intentLabels'

const pct = (v: number) => `${Math.round(v * 100)}%`
const LEVEL_CLASS: Record<WeakLevel, string> = { HIGH: 'lvl-high', MED: 'lvl-med', LOW: 'lvl-low' }
const GYM_MODES: GymMode[] = ['guess_my_intent', 'choose_right_meaning', 'correction_drill']

function Axis({ label, axis }: { label: string; axis: DiagnosisAxis | undefined }) {
  // §7-3 실계산 — 데이터 없으면 "—"(지어내지 않음)
  const level = axis?.level ?? null
  return (
    <div className="axis-row">
      <span className="axis-label">{label}</span>
      <span className={`axis-level ${level ? LEVEL_CLASS[level] : 'lvl-none'}`}>
        {level ?? '—'}
      </span>
    </div>
  )
}

export function NodePanel() {
  const brain = useBrainStore((s) => s.brain)
  const selectedNodeId = useBrainStore((s) => s.selectedNodeId)
  const [showBrief, setShowBrief] = useState(false)
  const [gymSession, setGymSession] = useState<GymSessionStart | null>(null)
  const [starting, setStarting] = useState<GymMode | null>(null)
  const [gymError, setGymError] = useState<string | null>(null)
  const [why, setWhy] = useState<NodeDiagnosis | null>(null) // §7-3 4축 실계산

  const node = brain?.nodes.find((n) => n.node_id === selectedNodeId) ?? null

  // 노드 선택이 바뀌면 4축 진단을 실제 계산으로 가져온다
  useEffect(() => {
    if (!node) {
      setWhy(null)
      return
    }
    const ctrl = new AbortController()
    setWhy(null)
    fetchNodeDiagnosis(node.intent_id, ctrl.signal)
      .then(setWhy)
      .catch((e: unknown) => {
        if (!ctrl.signal.aborted) console.warn('node diagnosis 미연결:', e)
      })
    return () => ctrl.abort()
  }, [node])

  const allIntents = useMemo(() => (brain?.nodes ?? []).map((n) => n.intent_id), [brain])
  const diag = useMemo(
    () => (node ? mockDiagnosis(node.node_id, allIntents, node.intent_id) : null),
    [node, allIntents],
  )

  if (!node || !diag) return null
  // 미지의 region 문자열이 와도 패널이 통째로 죽지 않게 방어(계약상 7개 고정이지만 신규 코드)
  const color = REGION_BY_ID[node.region as RegionId]?.color ?? '#94a3b8'

  const startGym = async (mode: GymMode) => {
    setStarting(mode)
    setGymError(null)
    try {
      // origin: 실 gold_count + 상위(mock) 혼동으로 진단·타깃 구성 (§7-4 강화하기)
      const diagnosis = [
        ...(goldDataLevel(node.gold_count) === 'LOW' ? ['GOLD_LOW'] : []),
        ...(diag.confusions.length ? ['CONFUSION_HIGH'] : []),
      ]
      const session = await openGymSession('TR_local', mode, {
        node: node.intent_id,
        region: node.region,
        diagnosis,
        target_confusion: diag.confusions[0]?.intentId ?? null,
      })
      setGymSession(session)
    } catch (e) {
      setGymError(String(e))
    } finally {
      setStarting(null)
    }
  }

  // 노드 전환 직후 한 프레임 동안 이전 노드의 실계산 레벨이 잔류하지 않게 intent로 게이트
  // (why 초기화는 effect에서 paint 후에야 돈다 — 지금 노드가 아니면 "—"로 보인다)
  const currentWhy = why?.intent_id === node.intent_id ? why : null

  return (
    <aside className="side-panel side-panel-right">
      <section className="panel-card">
        <div className="panel-head">
          <span className="panel-eyebrow">SELECTED NODE</span>
        </div>
        <div className="node-title" style={{ color }}>
          <span className="region-swatch" style={{ backgroundColor: color }} />
          {node.intent_id}
        </div>
        <div className="node-region">{node.region}</div>

        <div className="panel-subhead">KEY METRICS</div>
        <div className="metric-grid">
          <div className="metric">
            <span className="metric-value">{node.evidence_total.toLocaleString('en-US')}</span>
            <span className="metric-label">Evidence Total</span>
          </div>
          <div className="metric">
            <span className="metric-value">{node.gold_count}</span>
            <span className="metric-label">Gold</span>
          </div>
          <div className="metric">
            <span className="metric-value">{pct(node.evidence_diversity)}</span>
            <span className="metric-label">Diversity</span>
          </div>
          <div className="metric">
            <span className="metric-value">{node.exemplar_count}</span>
            <span className="metric-label">Exemplars</span>
          </div>
        </div>
      </section>

      <section className="panel-card">
        <div className="panel-subhead">
          대표 혼동 관계 <span className="dir-hint">(방향성)</span>
          <span className="mock-badge">미리보기 · mock</span>
        </div>
        {diag.confusions.length === 0 ? (
          <div className="panel-empty">혼동 관계 데이터 없음 (측정 전)</div>
        ) : (
          <ul className="confusion-list">
            {diag.confusions.map((c) => (
              <li key={c.intentId} className="confusion-row">
                <span className="confusion-arrow" style={{ color }}>→</span>
                <span className="confusion-name">{labelOf(c.intentId)}</span>
                <span className="confusion-rate">{pct(c.rate)}</span>
              </li>
            ))}
          </ul>
        )}
      </section>

      <section className="panel-card">
        <div className="panel-subhead">
          WHY THIS NODE IS WEAK
          <span className="calc-badge">§7-3 실계산</span>
        </div>
        {/* T4.1: 4축 실계산. 데이터 없는 축은 "—"(지어내지 않음) */}
        <div className="axis-rows">
          <Axis label="Ambiguous Language" axis={currentWhy?.ambiguous_language} />
          <Axis label="Screen Context Coverage" axis={currentWhy?.screen_context_coverage} />
          <Axis label="Persona Diversity" axis={currentWhy?.persona_diversity} />
          <Axis label="Gold Data" axis={currentWhy?.gold_data} />
        </div>

        <button type="button" className="cta-train" onClick={() => setShowBrief((v) => !v)}>
          🚀 강화하기
        </button>
        {showBrief && (
          <div className="train-brief">
            <div className="brief-row">
              <span>헷갈리는 짝</span>
              <strong>
                {labelOf(node.intent_id)}
                {diag.confusions[0] ? ` ↔ ${labelOf(diag.confusions[0].intentId)}` : ''}
              </strong>
            </div>
            {/* §8-1 Gym 모드 선택 → 세션 시작 (실 백엔드) */}
            <div className="gym-mode-pick">훈련 방식을 골라 주세요</div>
            <div className="gym-mode-buttons">
              {GYM_MODES.map((mode) => (
                <button
                  key={mode}
                  type="button"
                  className="gym-mode-btn"
                  disabled={starting !== null}
                  onClick={() => startGym(mode)}
                >
                  {starting === mode ? '여는 중…' : GYM_MODE_LABEL_KO[mode]}
                </button>
              ))}
            </div>
            {gymError && <p className="gym-error">시작 중 문제가 생겼어요. 다시 시도해 주세요.</p>}
          </div>
        )}
      </section>

      {gymSession && (
        <GymOverlay session={gymSession} onClose={() => setGymSession(null)} />
      )}
    </aside>
  )
}
