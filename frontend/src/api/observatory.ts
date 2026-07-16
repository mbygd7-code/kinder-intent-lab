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
  /** §3-1 버킷별 개수(synthetic/weak_behavioral/human_confirmed/gold/expert) — 파티클 원천 */
  evidence_buckets?: Record<string, number>
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

// --- 노드 방향성 혼동쌍 (§5-6 confusion_edges 실데이터) ---

export type ConfusionState = 'hypothesized' | 'observed' | 'confirmed'

export interface ConfusionEdge {
  to_predicted: string
  confusion_rate: number | null // §5-6 — Arena 측정 전이면 null (지어내지 않음)
  state: ConfusionState
  origin: string | null // SKEPTIC | CONSENSUS_DISAGREEMENT | GYM_CORRECTION | ARENA_MATRIX
}

/**
 * from_true=이 노드인 방향성 혼동쌍. measured=false면 아직 Arena가 이 노드를 재지 않아
 * 전부 가설(rate null)이다 — mock이 아니라 실제 SKEPTIC 가설 edge다(§5-6).
 */
export interface NodeConfusions {
  intent_id: string
  measured: boolean
  edges: ConfusionEdge[]
}

export async function fetchNodeConfusions(
  intentId: string,
  signal?: AbortSignal,
): Promise<NodeConfusions> {
  const res = await fetch(`/v1/observatory/node/${encodeURIComponent(intentId)}/confusions`, {
    signal,
  })
  if (!res.ok) throw new Error(`node confusions ${res.status}`)
  return (await res.json()) as NodeConfusions
}

/** 전체 방향성 혼동 edge (§5-6) — 3D edge 레이어(§7-5 Thickness/Flicker) 원천. */
export interface GlobalConfusionEdge {
  edge_id: string
  from_intent: string
  to_intent: string
  confusion_rate: number | null // Arena 측정 전 null (지어내지 않음)
  state: ConfusionState
  origin: string | null
}

export interface GlobalConfusionEdges {
  total: number
  measured_count: number // rate 비null 개수 — HUD가 '가설 N · 측정 M'으로 정직 표기
  edges: GlobalConfusionEdge[]
}

export async function fetchConfusionEdges(
  signal?: AbortSignal,
): Promise<GlobalConfusionEdges> {
  const res = await fetch('/v1/observatory/confusion-edges', { signal })
  if (!res.ok) throw new Error(`confusion edges ${res.status}`)
  return (await res.json()) as GlobalConfusionEdges
}

// --- 시험지(KTIB) 업로드 (§8-2) ---

export interface KtibUploadResult {
  ok: boolean
  dry_run: boolean
  inserted: number
  skipped_duplicate: number
  eligible_total: number
  ktib_version: string | null
  message: string
}

/** 구조화(CSV/시트에서 변환한) 한 문항 행 */
export interface KtibRow {
  intent: string
  teacher_prompt: string
  reviewers: string[]
  agreement_kappa: number | null
  /** O/X 승인 검수의 관측 일치율(§3-3 v1.6) — kappa가 퇴화해도 이 값으로 인증 가능 */
  agreement_rate?: number | null
  lang?: string
}

async function postKtibUpload(body: Record<string, unknown>): Promise<KtibUploadResult> {
  const res = await fetch('/v1/observatory/ktib/upload', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok) {
    // 형식 오류(400)는 detail 문구를 그대로 보여준다
    let detail = `업로드 실패 (${res.status})`
    try {
      const j = (await res.json()) as { detail?: string }
      if (j?.detail) detail = j.detail
    } catch {
      /* JSON 아님 — 기본 문구 유지 */
    }
    throw new Error(detail)
  }
  return (await res.json()) as KtibUploadResult
}

/** 시험지 YAML 업로드. commit=false=검증만(dry-run), true=실제 등록·동결. */
export function uploadKtib(yamlText: string, commit: boolean): Promise<KtibUploadResult> {
  return postKtibUpload({ yaml_text: yamlText, commit })
}

/** CSV/시트에서 변환한 구조화 문항 업로드 (작성자·승인자는 별도 입력). */
export function uploadKtibRows(input: {
  authored_by: string
  approved_by: string
  episodes: KtibRow[]
  commit: boolean
  /** 올린 파일 원문 — 이력에 보관해 나중에 열람·회수한다(§ 마이그레이션 0018) */
  source_document?: string
}): Promise<KtibUploadResult> {
  return postKtibUpload(input)
}

// --- 시험지 업로드 이력 (기록 + 원문 보관 · 리스트 · 열람) ---

/** 이력 목록 한 줄 — 원문(source_document)은 상세에서만 온다(경량). */
export interface KtibUploadRecord {
  upload_id: string
  created_at: string | null
  authored_by: string
  approved_by: string
  reviewers: string[]
  origin_channel: string
  dataset_split: string
  inserted: number
  skipped_duplicate: number
  agreement_rate: number | null
  agreement_kappa: number | null
  ktib_version: string | null
  eligible_total: number
}

/** 상세 = 목록 + 올린 원문 그대로 */
export interface KtibUploadDetail extends KtibUploadRecord {
  source_document: string | null
}

/** 업로드 이력 목록(최근 순). 등록(commit)된 것만 남는다. */
export async function fetchKtibUploads(signal?: AbortSignal): Promise<KtibUploadRecord[]> {
  const res = await fetch('/v1/observatory/ktib/uploads', { signal })
  if (!res.ok) throw new Error(`ktib uploads ${res.status}`)
  return ((await res.json()) as { uploads: KtibUploadRecord[] }).uploads
}

/** 업로드 상세 — 올린 원문까지. */
export async function fetchKtibUploadDetail(
  uploadId: string,
  signal?: AbortSignal,
): Promise<KtibUploadDetail> {
  const res = await fetch(`/v1/observatory/ktib/uploads/${encodeURIComponent(uploadId)}`, { signal })
  if (!res.ok) throw new Error(`ktib upload detail ${res.status}`)
  return (await res.json()) as KtibUploadDetail
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
