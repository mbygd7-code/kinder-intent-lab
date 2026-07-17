/**
 * 화면 씨드 웹 관리 API — /v1/situation-seeds.
 *
 * 씨드 = 킨더버스 화면(발화가 나오는 상황)의 수동 기본값. 저장은 서버가 전체 파일을
 * 재검증한 뒤에만 이뤄지고(어휘·vs-1.0·도메인 커버리지), 최소기준을 채운 씨드만
 * 다음 증산에서 LLM 확장의 앵커가 된다.
 */

export interface SeedWorkspaceState {
  surface_type: string
  objects_summary: Record<string, number>
  selection: { type?: string; count?: number } | Record<string, never>
  recent_actions: string[]
  visual_semantics: SeedVisualSemantics[]
}

export interface SeedVisualSemantics {
  object_ref: string
  schema_version: string
  extractor_version: string
  scene_type?: string[]
  activity_types?: string[]
  materials?: string[]
  observed_actions?: string[]
  interaction_pattern?: string[]
  group_size_band?: string
  spatial_pattern?: string[]
  identity_removed: true
}

export interface SeedItem {
  seed_id: string
  domains: string[]
  workspace_state: SeedWorkspaceState
  ready: boolean
  unmet: string[]
}

export interface SeedCatalog {
  version: string
  domains: string[]
  scenario_variants: number
  vocabulary: {
    surface_types: Record<string, string>
    object_kinds: Record<string, string>
    actions: Record<string, string>
  }
  vs_vocabulary: Record<string, string[]>
  seeds: SeedItem[]
}

export interface SeedDraft {
  seed_id: string
  domains: string[]
  workspace_state: SeedWorkspaceState
}

async function _json<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail = `요청 실패 (${res.status})`
    try {
      const j = (await res.json()) as { detail?: string }
      if (j?.detail) detail = j.detail
    } catch {
      /* JSON 아님 — 기본 문구 */
    }
    throw new Error(detail)
  }
  return (await res.json()) as T
}

export async function fetchSeedCatalog(signal?: AbortSignal): Promise<SeedCatalog> {
  return _json<SeedCatalog>(await fetch('/v1/situation-seeds', { signal }))
}

export async function createSeed(input: { pin: string; editor: string; seed: SeedDraft }) {
  return _json<{ ok: boolean; total: number }>(await fetch('/v1/situation-seeds/seeds', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  }))
}

export async function updateSeed(input: { pin: string; editor: string; seed: SeedDraft }) {
  return _json<{ ok: boolean }>(
    await fetch(`/v1/situation-seeds/seeds/${encodeURIComponent(input.seed.seed_id)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    }),
  )
}

export async function deleteSeed(input: { pin: string; editor: string; seedId: string }) {
  return _json<{ ok: boolean }>(
    await fetch(`/v1/situation-seeds/seeds/${encodeURIComponent(input.seedId)}/delete`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ pin: input.pin, editor: input.editor }),
    }),
  )
}

export interface ExpandPreview {
  anchor_seed_id: string
  domain: string
  variants: SeedWorkspaceState[]
}

export async function expandPreview(input: { pin: string; seedId: string }): Promise<ExpandPreview> {
  return _json<ExpandPreview>(await fetch('/v1/situation-seeds/expand-preview', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ pin: input.pin, seed_id: input.seedId }),
  }))
}

export async function bulkUpsertSeeds(input: {
  pin: string
  editor: string
  seeds: SeedDraft[]
}): Promise<{ ok: boolean; created: number; updated: number; total: number }> {
  return _json(await fetch('/v1/situation-seeds/seeds/bulk', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(input),
  }))
}

export type VocabTable = 'surface_types' | 'object_kinds' | 'actions'

export async function upsertVocab(input: {
  pin: string
  editor: string
  table: VocabTable
  vocabId: string
  labelKo: string
}): Promise<{ ok: boolean; updated: boolean }> {
  return _json(await fetch('/v1/situation-seeds/vocabulary', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      pin: input.pin, editor: input.editor,
      table: input.table, vocab_id: input.vocabId, label_ko: input.labelKo,
    }),
  }))
}

export async function deleteVocab(input: {
  pin: string
  editor: string
  table: VocabTable
  vocabId: string
}): Promise<{ ok: boolean }> {
  return _json(await fetch('/v1/situation-seeds/vocabulary/delete', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      pin: input.pin, editor: input.editor, table: input.table, vocab_id: input.vocabId,
    }),
  }))
}
