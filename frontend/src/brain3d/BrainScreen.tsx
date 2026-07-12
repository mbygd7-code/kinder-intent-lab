/**
 * Brain 뷰 진입점 — Observatory API에서 실 노드를 받아 §7-5 인코딩으로 렌더.
 *
 * 데이터 정직성: 실 데이터(live)만 무배지로 보여준다. 백엔드 미연결이면 에러 칩 +
 * 명시적 "데모 노드 보기" 버튼 — 데모(mock)는 MOCK 배지를 계속 띄운다(실데이터로 오인 방지).
 * WebGL 판정은 첫 렌더 전에 동기(useState initializer) — 미지원이면 2D 강제 + 토글 숨김.
 * BrainCanvas는 lazy import(three 분리 청크).
 */
import { lazy, Suspense, useEffect, useMemo, useRef, useState } from 'react'

import {
  fetchBrainState,
  fetchConfusionEdges,
  fetchPersonaOverlay,
  type ObservatoryBrain,
} from '../api/observatory'
import { LiveQuizPanel } from '../panels/LiveQuizPanel'
import { Brain2DFallback } from './Brain2DFallback'
import { ConfusionEdgeControl } from './ConfusionEdgeControl'
import { visualFromNode, type NodeVisual } from './encodings'
import { layoutNodes, type NodeSeed, type PlacedNode } from './layout'
import { LegendChip } from './LegendChip'
import { makeMockNodes } from './mockNodes'
import type { ParticleMetrics } from './particles'
import { PersonaOverlayControl } from './PersonaOverlayControl'
import { useBrainStore } from './store'

const BrainCanvas = lazy(() =>
  import('./BrainCanvas').then((m) => ({ default: m.BrainCanvas })),
)

function webglAvailable(): boolean {
  try {
    const canvas = document.createElement('canvas')
    return Boolean(canvas.getContext('webgl2') ?? canvas.getContext('webgl'))
  } catch {
    return false
  }
}

interface BrainData {
  nodes: PlacedNode[]
  visuals: ReadonlyMap<string, NodeVisual>
  /** evidence 파티클 원천(particles.ts) — 노드별 훈련 근거 지표 */
  metrics: ReadonlyMap<string, ParticleMetrics>
}

function fromApi(brain: ObservatoryBrain): BrainData {
  const seeds: NodeSeed[] = brain.nodes.map((n) => ({
    nodeId: n.node_id,
    intentId: n.intent_id,
    region: n.region,
  }))
  const visuals = new Map(brain.nodes.map((n) => [n.node_id, visualFromNode(n)]))
  const metrics = new Map<string, ParticleMetrics>(
    brain.nodes.map((n) => [
      n.node_id,
      {
        evidence_total: n.evidence_total,
        evidence_diversity: n.evidence_diversity,
        gold_count: n.gold_count,
        expert_count: n.evidence_buckets?.expert ?? 0,
      },
    ]),
  )
  return { nodes: layoutNodes(seeds), visuals, metrics }
}

export function BrainScreen() {
  const [webglOk] = useState(webglAvailable) // 마운트 전 1회 동기 판정
  const [data, setData] = useState<BrainData>({
    nodes: [],
    visuals: new Map(),
    metrics: new Map(),
  })
  const viewMode = useBrainStore((s) => s.viewMode)
  const setViewMode = useBrainStore((s) => s.setViewMode)
  const dataSource = useBrainStore((s) => s.dataSource)
  const setDataSource = useBrainStore((s) => s.setDataSource)
  const setRegionScores = useBrainStore((s) => s.setRegionScores)
  const setBrainMeta = useBrainStore((s) => s.setBrainMeta)
  const setBrain = useBrainStore((s) => s.setBrain)
  const setPersonaOverlay = useBrainStore((s) => s.setPersonaOverlay)
  const setPersonaOverlayError = useBrainStore((s) => s.setPersonaOverlayError)
  const setConfusionEdges = useBrainStore((s) => s.setConfusionEdges)
  const setConfusionEdgesError = useBrainStore((s) => s.setConfusionEdgesError)
  const personaOverlay = useBrainStore((s) => s.personaOverlay)
  const overlayClusterId = useBrainStore((s) => s.overlayClusterId)
  const reloadNonce = useBrainStore((s) => s.reloadNonce) // Gym 제출 후 bump → 재조회
  const bumpReload = useBrainStore((s) => s.bumpReload)
  const [liveQuizOpen, setLiveQuizOpen] = useState(false)
  const hudRef = useRef<HTMLDivElement>(null)

  // 우측 노드 패널이 상단 HUD(토글·오버레이·선택칩)를 가리지 않게 — 실측 HUD 높이를
  // --hud-h로 발행하면 CSS가 그만큼 패널 top을 내린다. 상태별 높이 변화(선택칩·오버레이
  // 펼침·MOCK 배지)를 ResizeObserver가 따라간다.
  useEffect(() => {
    const el = hudRef.current
    if (!el) return
    const apply = () => {
      document.documentElement.style.setProperty('--hud-h', `${el.offsetHeight}px`)
    }
    apply()
    // jsdom 등 ResizeObserver 미지원 환경에선 초기 1회 측정만 (테스트 안전)
    if (typeof ResizeObserver === 'undefined') return
    const ro = new ResizeObserver(apply)
    ro.observe(el)
    return () => {
      ro.disconnect()
      document.documentElement.style.removeProperty('--hud-h')
    }
  }, [])

  // reloadNonce가 오르면 refetch — 노드 배치는 node_id 결정론(layoutNodes)이라 자리 유지,
  // 훈련된 노드의 size/density/pending ring만 갱신된다(§6-7 [6] 즉시 반영)
  useEffect(() => {
    const ctrl = new AbortController()
    fetchBrainState(ctrl.signal)
      .then((brain) => {
        setData(fromApi(brain))
        setBrain(brain) // 패널이 읽는 원본
        setRegionScores(
          Object.fromEntries(brain.regions.map((r) => [r.region, r.reliability])),
        )
        setBrainMeta({
          ktibGlobal: brain.ktib_global,
          brainVersion: brain.brain_version,
          brainStage: brain.brain_stage, // §7-6 — Arena 산출 그대로
          brainStageName: brain.brain_stage_name,
        })
        setDataSource('live')
      })
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return
        // 제출 후 재조회(bump)의 일시 실패는 '백엔드 미연결' 화면으로 뒤집지 않는다 —
        // 이미 라이브 데이터를 그리는 중이면 실데이터(다소 이전 상태)를 유지하는 게 정직하다
        if (useBrainStore.getState().dataSource === 'live') {
          console.warn('brain 재조회 실패 — 기존 라이브 상태 유지:', err)
          return
        }
        console.warn('observatory API 미연결:', err)
        setDataSource('error')
      })
    return () => ctrl.abort()
  }, [reloadNonce, setBrain, setBrainMeta, setDataSource, setRegionScores])

  // T5.4 persona-overlay(§7-6·§4-2) — 부가 채널이라 실패해도 dataSource(뇌 화면)는 안 건드린다
  useEffect(() => {
    const ctrl = new AbortController()
    fetchPersonaOverlay(ctrl.signal)
      .then((overlay) => {
        if (!Array.isArray(overlay?.clusters)) throw new Error('persona overlay 형식 아님')
        setPersonaOverlay(overlay)
      })
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return
        console.warn('persona overlay 미연결:', err)
        setPersonaOverlayError() // 이미 ready면 store가 기존 실데이터를 유지한다
      })
    return () => ctrl.abort()
  }, [reloadNonce, setPersonaOverlay, setPersonaOverlayError])

  // §5-6 혼동 edge(§7-5 Thickness/Flicker 원천) — 부가 채널: 실패해도 뇌 화면은 유지
  useEffect(() => {
    const ctrl = new AbortController()
    fetchConfusionEdges(ctrl.signal)
      .then((payload) => {
        if (!Array.isArray(payload?.edges)) throw new Error('confusion edges 형식 아님')
        setConfusionEdges(payload)
      })
      .catch((err: unknown) => {
        if (ctrl.signal.aborted) return
        console.warn('confusion edges 미연결:', err)
        setConfusionEdgesError() // 이미 ready면 store가 기존 실데이터를 유지한다
      })
    return () => ctrl.abort()
  }, [reloadNonce, setConfusionEdges, setConfusionEdgesError])

  // 선택된 클러스터의 intent_id → prior 맵 — OFF(null 선택)면 null → 기본 §7-5 인코딩 그대로
  const overlayPriors = useMemo<ReadonlyMap<string, number> | null>(() => {
    if (overlayClusterId == null || !personaOverlay) return null
    const cluster = personaOverlay.clusters.find((c) => c.cluster_id === overlayClusterId)
    return cluster ? new Map(Object.entries(cluster.priors)) : null
  }, [personaOverlay, overlayClusterId])

  const loadMock = () => {
    // 명시적 데모 — MOCK 배지가 계속 표시된다 (실데이터 오인 방지).
    // metrics는 비운다: 데모에 evidence 파티클을 지어내지 않는다.
    setData({ nodes: layoutNodes(makeMockNodes()), visuals: new Map(), metrics: new Map() })
    setDataSource('mock')
  }

  const effectiveMode = webglOk ? viewMode : '2d'

  return (
    <div className="brain-screen">
      {effectiveMode === '3d' ? (
        <Suspense fallback={<p className="rotate-hint">3D 로딩…</p>}>
          <BrainCanvas
            nodes={data.nodes}
            visuals={data.visuals}
            metrics={data.metrics}
            overlayPriors={overlayPriors}
          />
        </Suspense>
      ) : (
        <Brain2DFallback nodes={data.nodes} overlayPriors={overlayPriors} />
      )}

      {/* 상단 우측 코너 고정 — 높이를 측정해(--hud-h) 우측 노드 패널이 그 아래에서 시작하게 한다.
          토글은 하단 중앙 독으로 옮겼고, 선택 노드 이름은 아래 SELECTED NODE 카드가 담당(중복 제거). */}
      <div className="brain-hud" ref={hudRef}>
        {/* T5.4 Persona Overlay(§7-6) — 뇌가 그려진 뒤에만(로딩/에러 화면엔 오버레이 대상이 없다) */}
        {(dataSource === 'live' || dataSource === 'mock') && <PersonaOverlayControl />}
        {/* §5-6 혼동 edge 토글·카운트 — 실데이터(live)에서만 (데모 노드와 실 edge는 짝이 안 맞는다) */}
        {dataSource === 'live' && <ConfusionEdgeControl />}
        {/* 즉석 문답(§6-7 [4]) — 라이브 추론이 필요하므로 실데이터(live)에서만 */}
        {dataSource === 'live' && (
          <button type="button" className="view-toggle" onClick={() => setLiveQuizOpen(true)}>
            💬 즉석 문답
          </button>
        )}
        {(dataSource === 'live' || dataSource === 'mock') && <LegendChip />}
        {dataSource === 'mock' && <span className="badge badge-mock">MOCK</span>}
        {dataSource === 'error' && (
          <div className="error-chip">
            <span>백엔드 미연결 — 실 노드를 불러올 수 없습니다</span>
            <button type="button" className="view-toggle" onClick={loadMock}>
              데모 노드 보기
            </button>
          </div>
        )}
      </div>

      {/* 뷰 전환 토글 — 하단 중앙 (구 "Drag to rotate brain" 자리) */}
      {webglOk && (
        <div className="view-toggle-dock">
          <button
            type="button"
            className="view-toggle"
            onClick={() => setViewMode(effectiveMode === '3d' ? '2d' : '3d')}
          >
            {effectiveMode === '3d' ? '2D 지도로 보기' : '3D 뇌로 보기'}
          </button>
        </div>
      )}

      {liveQuizOpen && (
        <LiveQuizPanel
          onClose={() => setLiveQuizOpen(false)}
          onComplete={bumpReload} // 훈련 evidence 저장 시에만 — 노드 size/pending 갱신(§6-7 [6])
        />
      )}
    </div>
  )
}
