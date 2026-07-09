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
}

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
  ktib_global: number | null // §7-1 중앙 수치 — 마지막 Arena run만
  regions: ObservatoryRegion[]
  nodes: ObservatoryNode[]
}

export async function fetchBrainState(signal?: AbortSignal): Promise<ObservatoryBrain> {
  const res = await fetch('/v1/observatory/brain', { signal })
  if (!res.ok) throw new Error(`observatory API ${res.status}`)
  return (await res.json()) as ObservatoryBrain
}
