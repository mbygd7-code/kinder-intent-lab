/**
 * Observatory API 클라이언트 — GET /v1/observatory/brain.
 * 타입은 schemas/observatory_brain.schema.json 파생(수동 미러 — 필드 추가 시 스키마가 원천).
 * dev에선 vite 프록시(/v1 → 127.0.0.1:8000)를 탄다.
 */
import type { RegionId } from '../brain3d/regions'

export interface ObservatoryRegion {
  region: RegionId
  reliability: number | null // Arena heldout 집계 — 미실행 null
  node_count: number
  gold_evidence: number
  synthetic_evidence: number
  stage: GrowthStage // §7-6 — 전부 Arena 산출에서 유도
  stage_name: string
  measured_count: number // heldout이 측정된 노드 수 (미측정 ≠ 0%)
}

/**
 * §7-6 성장 스테이지. region은 0~3만 나온다:
 * 4(Semantic Cross-Region Flow)는 region *쌍* 사이의 흐름이고,
 * 5(Whole Brain Resonance)는 global 지표라 — 둘 다 brain_stage로만 온다.
 * 백엔드가 준 값을 그대로 표시한다(보간·추측 금지).
 */
export type GrowthStage = 0 | 1 | 2 | 3 | 4 | 5

export interface ObservatoryNode {
  node_id: string
  intent_id: string
  region: RegionId
  evidence_total: number
  evidence_diversity: number
  gold_count: number
  exemplar_count: number
  heldout_accuracy: number | null // §7-5 Brightness 원천 — Arena만 기록
  calibration_ece?: number | null
  last_arena_run?: string | null
  pending_evaluation: boolean
}

export interface ObservatoryBrain {
  brain_version: string
  ontology_version: string
  ktib_global: number | null // §7-1 중앙 수치 — 마지막 brain arena run만 (베이스라인 run 제외)
  brain_stage: GrowthStage // §7-6 — 5 = KTIB 목표 도달
  brain_stage_name: string
  regions: ObservatoryRegion[]
  nodes: ObservatoryNode[]
}

export async function fetchBrainState(signal?: AbortSignal): Promise<ObservatoryBrain> {
  const res = await fetch('/v1/observatory/brain', { signal })
  if (!res.ok) throw new Error(`observatory API ${res.status}`)
  return (await res.json()) as ObservatoryBrain
}

// --- T5.4 Persona Overlay (§4-2·§7-6) ---

/**
 * 클러스터별 persona prior 분포. §5-5에서 LLM 밖에서 activation에 곱해지는 배수이고,
 * 측정된 클러스터별 정확도(Persona Lift/Harm)가 아니다 — 그 지표는 아직 정의되지 않았다.
 */
export interface PersonaOverlayCluster {
  cluster_id: string
  member_count: number | null
  state_version: string
  priors: Record<string, number> // intent_id → prior
}

export interface PersonaOverlay {
  state_version: string | null
  prior_cap: number // §5-5 persona_prior_cap — 오버레이 강조가 과장되지 않도록 함께 온다
  clusters: PersonaOverlayCluster[]
}

export async function fetchPersonaOverlay(signal?: AbortSignal): Promise<PersonaOverlay> {
  const res = await fetch('/v1/observatory/persona-overlay', { signal })
  if (!res.ok) throw new Error(`persona overlay ${res.status}`)
  return (await res.json()) as PersonaOverlay
}

// --- T4.1 Weakness 진단 4축 (§7-3 실계산) ---

export type WeakLevel = 'HIGH' | 'MED' | 'LOW'

export interface DiagnosisAxis {
  value: number | null // §7-3 원값 — null=데이터 없음(계산 불가)
  level: WeakLevel | null
}

export interface NodeDiagnosis {
  intent_id: string
  ambiguous_language: DiagnosisAxis
  screen_context_coverage: DiagnosisAxis
  persona_diversity: DiagnosisAxis
  gold_data: DiagnosisAxis
}

export async function fetchNodeDiagnosis(
  intentId: string,
  signal?: AbortSignal,
): Promise<NodeDiagnosis> {
  const res = await fetch(`/v1/observatory/node/${encodeURIComponent(intentId)}/diagnosis`, {
    signal,
  })
  if (!res.ok) throw new Error(`node diagnosis ${res.status}`)
  return (await res.json()) as NodeDiagnosis
}
