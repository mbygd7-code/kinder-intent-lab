/**
 * 우측 패널 — Zoom 2 Node 상세 + Weakness Diagnosis Engine (§7-3, 레퍼런스 우측 패널).
 *
 * 실데이터: 노드의 evidence 지표(총량/gold/다양성/exemplar) + **WHY-WEAK 4축 실계산**(T4.1,
 * /v1/observatory/node/{intent}/diagnosis) — 데이터 없는 축은 "—"(지어내지 않음).
 * 방향성 혼동쌍(§5-6): /v1/observatory/node/{intent}/confusions 실 confusion_edges. rate는
 * Arena만 채우므로 측정 전이면 "측정 전" + 상태칩(가설/관측/확정)으로 정직하게 표기(날조 없음).
 *
 * 강화하기(T4.3, §6-7 클릭-투-트레인): POST /v1/gym/pack(서버측 진단)으로 실 Challenge Pack을
 * 만들어 §7-4 브리핑을 띄우고 → 모드 선택 → 세션 → 제출 완료 시 bumpReload로 뇌 재조회.
 * 브리핑 값은 전부 실 pack 필드 — 없는 필드는 "—"/부재 문구(지어내지 않음).
 */
import { useEffect, useRef, useState } from 'react'

import {
  generatePack,
  openGymSession,
  type GeneratedPackResponse,
  type GymMode,
  type GymSessionStart,
} from '../api/gym'
import {
  fetchNodeConfusions,
  fetchNodeDiagnosis,
  type ConfusionState,
  type DiagnosisAxis,
  type NodeConfusions,
  type NodeDiagnosis,
  type WeakLevel,
} from '../api/observatory'
import { REGION_BY_ID, type RegionId } from '../brain3d/regions'
import { useBrainStore } from '../brain3d/store'
import { GymOverlay } from './GymOverlay'
import { GYM_MODE_LABEL_KO, labelOf } from './intentLabels'

const pct = (v: number) => `${Math.round(v * 100)}%`
const LEVEL_CLASS: Record<WeakLevel, string> = { HIGH: 'lvl-high', MED: 'lvl-med', LOW: 'lvl-low' }

/** §5-6 confusion edge state 한글 칩 — 가설(SKEPTIC) → 관측 → 확정(Arena 검증) */
const CONFUSION_STATE_KO: Record<ConfusionState, string> = {
  hypothesized: '가설',
  observed: '관측',
  confirmed: '확정',
}
const GYM_MODES: GymMode[] = ['guess_my_intent', 'choose_right_meaning', 'correction_drill']

/** §7-4 브리핑 표기 — pack.strategy 코드의 한글 칩(미지 코드는 코드 그대로, 날조 없음) */
const STRATEGY_KO: Record<string, string> = {
  A_DATA_COVERAGE: '데이터 보강',
  B_HUMAN_EVIDENCE: '교사 검증',
  C_CONFUSION: '혼동 구분',
  D_MODEL: '모델 갱신',
}

/** §7-4 브리핑 표기 — difficulty_curve 한글(부재·미지 값은 "—") */
const DIFFICULTY_KO: Record<string, string> = {
  easy: '쉬움',
  medium: '보통',
  medium_to_hard: '보통 → 어려움',
  hard: '어려움',
  adversarial: '도전',
}

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
  const bumpReload = useBrainStore((s) => s.bumpReload)
  // §7-4 브리핑: 실 pack 응답을 intent와 함께 보관 — 노드가 바뀌면 표시에서 게이트된다
  const [brief, setBrief] = useState<{ intent: string; resp: GeneratedPackResponse } | null>(null)
  const [briefLoading, setBriefLoading] = useState(false)
  const [briefError, setBriefError] = useState<string | null>(null)
  const briefSeq = useRef(0) // 토글 오프/노드 전환 후 도착한 늦은 응답 무효화
  const [gymSession, setGymSession] = useState<GymSessionStart | null>(null)
  const [starting, setStarting] = useState<GymMode | null>(null)
  const [gymError, setGymError] = useState<string | null>(null)
  const [why, setWhy] = useState<NodeDiagnosis | null>(null) // §7-3 4축 실계산
  const [confusions, setConfusions] = useState<NodeConfusions | null>(null) // §5-6 실 혼동쌍

  const node = brain?.nodes.find((n) => n.node_id === selectedNodeId) ?? null
  const nodeIntent = node?.intent_id ?? null

  // 노드 선택이 바뀌면 4축 진단(§7-3)과 방향성 혼동쌍(§5-6)을 실데이터로 가져온다
  useEffect(() => {
    if (!node) {
      setWhy(null)
      setConfusions(null)
      return
    }
    const ctrl = new AbortController()
    setWhy(null)
    setConfusions(null)
    fetchNodeDiagnosis(node.intent_id, ctrl.signal)
      .then(setWhy)
      .catch((e: unknown) => {
        if (!ctrl.signal.aborted) console.warn('node diagnosis 미연결:', e)
      })
    fetchNodeConfusions(node.intent_id, ctrl.signal)
      .then(setConfusions)
      .catch((e: unknown) => {
        if (!ctrl.signal.aborted) console.warn('node confusions 미연결:', e)
      })
    return () => ctrl.abort()
  }, [node])

  // 노드 전환 시 브리핑 상태 전체 리셋 — 이전 노드의 로딩 문구/토글 상태/세션 에러가
  // 새 노드에 새어 나오지 않게 한다(리뷰: briefLoading·gymError는 intent 게이트 밖이었다)
  useEffect(() => {
    briefSeq.current += 1 // 진행 중이던 pack 요청 응답은 버린다
    setBrief(null)
    setBriefLoading(false)
    setBriefError(null)
    setGymError(null)
  }, [nodeIntent])

  if (!node) return null
  // 미지의 region 문자열이 와도 패널이 통째로 죽지 않게 방어(계약상 7개 고정이지만 신규 코드)
  const color = REGION_BY_ID[node.region as RegionId]?.color ?? '#94a3b8'

  // 브리핑은 현재 노드의 것일 때만 보여준다(노드 전환 시 이전 pack 잔류 방지 — 정직성 게이트)
  const briefResp = brief?.intent === node.intent_id ? brief.resp : null
  const briefOpen = briefResp !== null || briefLoading

  // 강화하기 토글: 켜기 = POST /v1/gym/pack(T4.2, 서버측 진단)으로 실 pack 생성, 끄기 = 브리핑 제거
  const toggleBrief = () => {
    if (briefOpen) {
      briefSeq.current += 1 // 진행 중이던 요청 응답은 버린다
      setBrief(null)
      setBriefLoading(false)
      setBriefError(null)
      setGymError(null) // 이전 브리핑의 세션 시작 실패가 새 브리핑에 잔류하지 않게
      return
    }
    const seq = ++briefSeq.current
    const intent = node.intent_id
    setBriefLoading(true)
    setBriefError(null)
    setGymError(null)
    generatePack(intent)
      .then((resp) => {
        if (briefSeq.current !== seq) return
        setBrief({ intent, resp })
      })
      .catch(() => {
        if (briefSeq.current !== seq) return
        setBriefError('브리핑을 불러오지 못했어요. 다시 시도해 주세요.')
      })
      .finally(() => {
        if (briefSeq.current === seq) setBriefLoading(false)
      })
  }

  const startGym = async (mode: GymMode) => {
    if (!briefResp) return
    setStarting(mode)
    setGymError(null)
    try {
      // origin: 서버가 브리핑에 준 진단·타깃 그대로 — 세션 pack이 브리핑과 일치한다(§7-4)
      const session = await openGymSession('TR_local', mode, {
        node: node.intent_id,
        region: node.region,
        diagnosis: briefResp.diagnosis_codes,
        target_confusion: briefResp.pack.target_edges?.[0]?.to_predicted ?? null,
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
  // 혼동쌍도 같은 정직성 게이트 — 노드 전환 직후 이전 노드의 목록이 잔류하지 않게 intent로 게이트
  const currentConfusions =
    confusions?.intent_id === node.intent_id ? confusions : null

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
          <span className="calc-badge">§5-6</span>
        </div>
        {/* §5-6 실 confusion_edges — rate는 Arena만 채운다. 측정 전이면 "측정 전"(지어내지 않음) */}
        {currentConfusions === null ? (
          <div className="panel-empty">불러오는 중…</div>
        ) : (currentConfusions.edges?.length ?? 0) === 0 ? (
          <div className="panel-empty">혼동 관계 데이터 없음 (측정 전)</div>
        ) : (
          <>
            <ul className="confusion-list">
              {(currentConfusions.edges ?? []).slice(0, 4).map((c) => (
                <li key={c.to_predicted} className="confusion-row">
                  <span className="confusion-arrow" style={{ color }}>→</span>
                  <span className="confusion-name">{labelOf(c.to_predicted)}</span>
                  <span className={`confusion-state state-${c.state}`}>
                    {CONFUSION_STATE_KO[c.state]}
                  </span>
                  <span
                    className={`confusion-rate${c.confusion_rate === null ? ' unmeasured' : ''}`}
                  >
                    {c.confusion_rate === null ? '측정 전' : pct(c.confusion_rate)}
                  </span>
                </li>
              ))}
            </ul>
            {!currentConfusions.measured && (
              <p className="panel-hint confusion-note">
                Arena 측정 전 — SKEPTIC 가설 단계 혼동쌍 (실측 rate는 Arena run 이후)
              </p>
            )}
          </>
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

        <button type="button" className="cta-train" onClick={toggleBrief}>
          🚀 강화하기
        </button>
        {briefLoading && <p className="brief-loading">훈련 브리핑을 준비하고 있어요…</p>}
        {briefError && <p className="gym-error">{briefError}</p>}
        {briefResp && (
          <div className="train-brief">
            {/* §7-4 브리핑 — 전부 실 pack 필드. 없는 값은 "—"/부재 문구(지어내지 않음) */}
            <p className="brief-heading">
              이 노드를 강화하기 위해 <strong>{briefResp.pack.items}개</strong>의 훈련 문항을
              준비했어요.
            </p>
            <div className="brief-chips">
              {briefResp.pack.strategy.map((code) => (
                <span key={code} className="brief-chip">{STRATEGY_KO[code] ?? code}</span>
              ))}
              {briefResp.diagnosis_codes.map((code) => (
                <span key={code} className="brief-chip brief-chip-diag">{code}</span>
              ))}
            </div>
            <div className="brief-row">
              <span>Target Confusion</span>
              <strong>
                {briefResp.pack.target_edges?.length
                  ? `${labelOf(node.intent_id)} ↔ ${labelOf(briefResp.pack.target_edges[0].to_predicted)}`
                  : '측정된 혼동 관계 없음'}
              </strong>
            </div>
            <div className="brief-row">
              <span>Difficulty</span>
              <strong>
                {briefResp.pack.difficulty_curve
                  ? DIFFICULTY_KO[briefResp.pack.difficulty_curve] ?? '—'
                  : '—'}
              </strong>
            </div>
            <div className="brief-row">
              <span>Persona Mix</span>
              <strong>
                {briefResp.pack.persona_mix?.length
                  ? `${briefResp.pack.persona_mix.length}가지 교사 성향`
                  : '성향 묶음 준비 중'}
              </strong>
            </div>
            {briefResp.needs_human ? (
              <>
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
                {gymError && (
                  <p className="gym-error">시작 중 문제가 생겼어요. 다시 시도해 주세요.</p>
                )}
              </>
            ) : (
              // A/D 전용(needs_human=false): 사람 세션 없이 Foundry 작업지시만 — 정직하게 안내
              <p className="brief-foundry-note">
                이 노드는 데이터 공장(Foundry)에 시나리오 생성만 요청했어요 — 지금은 훈련
                세션이 필요하지 않아요.
              </p>
            )}
          </div>
        )}
      </section>

      {gymSession && (
        <GymOverlay
          session={gymSession}
          onClose={() => setGymSession(null)}
          onComplete={bumpReload} // 제출 성공 시에만 — 훈련된 노드의 size/density/ring 갱신(§6-7 [6])
        />
      )}
    </aside>
  )
}
