/**
 * 화면 씨드 CSV — 기본 폼 다운로드 + 엑셀 작성분 일괄 업로드 (2026-07-17 사용자 요청).
 *
 * - 값은 한글 라벨·영문 id 둘 다 인식한다(엑셀에서 한글로 쓰면 된다).
 * - 영역은 `+`로 구분(빈칸=전체), 직전 행동은 `>`로 순서 표기.
 * - 사진 서술은 CSV로 1개(첫 사진)까지 — 2개 이상인 씨드는 비고에 표시되고,
 *   서술 열을 그대로 두고 올리면 기존 서술 전체를 보존한다(조용한 유실 방지).
 * - 반영은 서버 bulk 문(전체 검증 통과 시에만 원자 저장) — 부분 반영 없음.
 */
import type {
  SeedCatalog,
  SeedDraft,
  SeedItem,
  SeedVisualSemantics,
} from '../api/situationSeeds'
import { parseCsv } from './csv'

/** vs-1.0 통제 어휘 한글 라벨 — 어휘 자체는 서버(vs_vocabulary)가 원천, 여기는 표시만. */
export const VS_KO: Record<string, string> = {
  INDOOR_CLASSROOM: '교실 안', OUTDOOR_YARD: '바깥 마당', HALLWAY: '복도', GYM_ROOM: '강당',
  ART_CORNER: '미술 영역', READING_CORNER: '책 영역',
  NATURE_SORTING: '자연물 분류', BLOCK_PLAY: '블록 놀이', ROLE_PLAY: '역할 놀이',
  DRAWING_PAINTING: '그리기·물감', BOOK_READING: '책 읽기', MUSIC_MOVEMENT: '음률·신체',
  SAND_WATER_PLAY: '모래·물놀이', BOARD_GAME: '보드게임', FREE_PLAY: '자유 놀이',
  MEAL_SNACK: '식사·간식', CIRCLE_TIME: '모임 시간',
  LEAF: '나뭇잎', TRAY: '쟁반', BLOCK: '블록', PAPER: '종이', CRAYON: '크레용', PAINT: '물감',
  BOOK: '책', SAND: '모래', WATER: '물', FABRIC: '천', RECYCLED: '재활용품', TOY_FIGURE: '장난감 인형',
  SORT: '분류하기', COMPARE: '비교하기', STACK: '쌓기', DRAW: '그리기', CUT: '자르기',
  POUR: '붓기', OBSERVE: '관찰하기', TALK: '이야기하기', SHARE: '나누기', BUILD: '만들기',
  PRETEND: '흉내 놀이',
  SOLO: '혼자', PEER_PARALLEL: '나란히 따로', PEER_COLLABORATIVE: '또래 협력',
  TEACHER_GUIDED: '교사 주도', GROUP_CIRCLE: '다 같이 모여',
  INDIVIDUAL: '1명', PAIR: '2명', SMALL_GROUP: '소그룹', LARGE_GROUP: '대그룹',
  UNKNOWN: '모름',
}
export const vsKo = (v: string) => VS_KO[v] ?? v

const VS_COLS = [
  ['사진 장소', 'scene_type'],
  ['사진 활동', 'activity_types'],
  ['사진 재료(빈칸=생략)', 'materials'],
  ['아이들 행동', 'observed_actions'],
  ['상호작용', 'interaction_pattern'],
  ['인원', 'group_size_band'],
] as const

const esc = (v: unknown) => `"${String(v ?? '').replaceAll('"', '""')}"`

/** vs 항목을 CSV 6칸 투영으로 — 다운로드·"열이 그대로면 보존" 비교 양쪽에서 쓴다. */
function vsCells(v: SeedVisualSemantics | undefined): string[] {
  if (!v) return ['', '', '', '', '', '']
  return [
    vsKo(v.scene_type?.[0] ?? ''),
    vsKo(v.activity_types?.[0] ?? ''),
    vsKo(v.materials?.[0] ?? ''),
    vsKo(v.observed_actions?.[0] ?? ''),
    vsKo(v.interaction_pattern?.[0] ?? ''),
    vsKo(v.group_size_band ?? ''),
  ]
}

export function buildSeedCsv(catalog: SeedCatalog): string {
  const objectKinds = Object.keys(catalog.vocabulary.object_kinds)
  const header = [
    '씨드id', '영역(+구분, 빈칸=전체)', '화면',
    ...objectKinds.map((k) => `${catalog.vocabulary.object_kinds[k]} 수`),
    '선택 카드(빈칸=없음)', '선택 수', '직전 행동(>로 순서)',
    ...VS_COLS.map(([label]) => label),
    '비고(업로드시 무시)',
  ]
  const lines = [header.map(esc).join(',')]
  for (const s of catalog.seeds) {
    const ws = s.workspace_state
    const sel = ws.selection as { type?: string; count?: number }
    const extraVs = ws.visual_semantics.length > 1
      ? `사진 서술 ${ws.visual_semantics.length}개 — 나머지는 웹에서 수정` : ''
    lines.push([
      s.seed_id,
      s.domains.join('+'),
      catalog.vocabulary.surface_types[ws.surface_type] ?? ws.surface_type,
      ...objectKinds.map((k) => String(ws.objects_summary[k] ?? 0)),
      sel?.type ? (catalog.vocabulary.object_kinds[sel.type] ?? sel.type) : '',
      sel?.type ? String(sel.count ?? 1) : '',
      ws.recent_actions.map((a) => catalog.vocabulary.actions[a] ?? a).join(' > '),
      ...vsCells(ws.visual_semantics[0]),
      [extraVs, s.ready ? '' : '최소기준 미달'].filter(Boolean).join(' · '),
    ].map(esc).join(','))
  }
  return lines.join('\n')
}

/** 한글 라벨·영문 id 어느 쪽이든 id로 — 못 찾으면 null. */
function reverse(table: Record<string, string>): (raw: string) => string | null {
  const map = new Map<string, string>()
  for (const [id, ko] of Object.entries(table)) {
    map.set(id.toLowerCase(), id)
    map.set(ko.trim(), id)
  }
  return (raw: string) => map.get(raw.trim()) ?? map.get(raw.trim().toLowerCase()) ?? null
}

function reverseVs(allowed: string[]): (raw: string) => string | null {
  const map = new Map<string, string>()
  for (const v of allowed) {
    map.set(v.toLowerCase(), v)
    map.set(vsKo(v), v)
  }
  return (raw: string) => map.get(raw.trim()) ?? map.get(raw.trim().toLowerCase()) ?? null
}

export interface ParsedSeedCsv {
  drafts: SeedDraft[]
  errors: string[]
}

export function parseSeedRows(text: string, catalog: SeedCatalog): ParsedSeedCsv {
  const grid = parseCsv(text)
  if (grid.length < 2) return { drafts: [], errors: ['CSV에 데이터 행이 없어요 (헤더 + 씨드 행 필요)'] }

  const header = grid[0].map((h) => h.trim())
  const col = (re: RegExp) => header.findIndex((h) => re.test(h))
  const iId = col(/씨드\s*id/i)
  const iDomains = col(/영역/)
  const iSurface = header.findIndex((h) => h === '화면' || /^화면\b/.test(h))
  const iSelType = col(/선택\s*카드/)
  const iSelCount = col(/선택\s*수/)
  const iActions = col(/직전\s*행동/)
  if ([iId, iDomains, iSurface, iSelType, iSelCount, iActions].some((i) => i < 0)) {
    return { drafts: [], errors: ['헤더가 달라요 — [⬇ CSV 폼 받기]로 받은 양식을 그대로 쓰세요'] }
  }
  const objectKinds = Object.keys(catalog.vocabulary.object_kinds)
  const iObjects = objectKinds.map((k) => {
    const label = catalog.vocabulary.object_kinds[k]
    return [k, header.findIndex((h) => h.includes(label) && h.includes('수'))] as const
  })
  const iVs = VS_COLS.map(([label, field]) =>
    [field, header.findIndex((h) => h.includes(label.split('(')[0]))] as const)

  const surfaceOf = reverse(catalog.vocabulary.surface_types)
  const objectOf = reverse(catalog.vocabulary.object_kinds)
  const actionOf = reverse(catalog.vocabulary.actions)
  const vsOf: Record<string, (raw: string) => string | null> = {}
  for (const [, field] of VS_COLS) vsOf[field] = reverseVs(catalog.vs_vocabulary[field] ?? [])
  const existing = new Map<string, SeedItem>(catalog.seeds.map((s) => [s.seed_id, s]))

  const drafts: SeedDraft[] = []
  const errors: string[] = []
  for (let r = 1; r < grid.length; r++) {
    const cells = grid[r]
    const rowNo = r + 1 // 엑셀 행 번호
    const id = (cells[iId] ?? '').replace(/^﻿/, '').trim()
    if (!id || id.startsWith('#')) continue
    const fail = (why: string) => errors.push(`${rowNo}행(${id}): ${why}`)

    const domains: string[] = []
    let rowBroken = false
    for (const d of (cells[iDomains] ?? '').split(/[+·|]/).map((x) => x.trim()).filter(Boolean)) {
      const up = d.toUpperCase()
      if (!catalog.domains.includes(up)) {
        fail(`모르는 영역 '${d}' — 가능: ${catalog.domains.join(', ')}`)
        rowBroken = true
      } else domains.push(up)
    }

    const surface = surfaceOf(cells[iSurface] ?? '')
    if (!surface) {
      fail(`모르는 화면 '${(cells[iSurface] ?? '').trim()}' — 가능: ${Object.values(catalog.vocabulary.surface_types).join(', ')}`)
      rowBroken = true
    }

    const objects: Record<string, number> = {}
    for (const [kind, idx] of iObjects) {
      const raw = idx >= 0 ? (cells[idx] ?? '').trim() : ''
      if (!raw) continue
      const n = Number(raw)
      if (!Number.isInteger(n) || n < 0) { fail(`${catalog.vocabulary.object_kinds[kind]} 수 '${raw}'는 숫자가 아니에요`); rowBroken = true; continue }
      if (n > 0) objects[kind] = n
    }

    const selRaw = (cells[iSelType] ?? '').trim()
    let selection: SeedDraft['workspace_state']['selection'] = {}
    if (selRaw) {
      const selType = objectOf(selRaw)
      if (!selType) { fail(`모르는 선택 카드 '${selRaw}' — 가능: ${Object.values(catalog.vocabulary.object_kinds).join(', ')}`); rowBroken = true }
      else {
        const cnt = Number((cells[iSelCount] ?? '').trim() || '1')
        selection = { type: selType, count: Number.isInteger(cnt) && cnt > 0 ? cnt : 1 }
      }
    }

    const actions: string[] = []
    for (const a of (cells[iActions] ?? '').split(/[>→]/).map((x) => x.trim()).filter(Boolean)) {
      const act = actionOf(a)
      if (!act) { fail(`모르는 행동 '${a}' — 가능: ${Object.values(catalog.vocabulary.actions).join(', ')}`); rowBroken = true }
      else actions.push(act)
    }

    // 사진 서술: 6칸 중 하나라도 채워지면 1개 조립(재료만 선택). 기존 씨드에서 열이
    // 그대로면(다운로드 원형) 원래 서술 전체를 보존한다 — 2개 이상 서술의 조용한 유실 방지.
    const rawVs = iVs.map(([, idx]) => (idx >= 0 ? (cells[idx] ?? '').trim() : ''))
    const prev = existing.get(id)
    let visual: SeedVisualSemantics[] = []
    if (prev && vsCells(prev.workspace_state.visual_semantics[0]).every((v, i) => v.trim() === rawVs[i])) {
      visual = prev.workspace_state.visual_semantics
    } else if (rawVs.some(Boolean)) {
      const got: Record<string, string | null> = {}
      for (let i = 0; i < iVs.length; i++) {
        const field = iVs[i][0]
        got[field] = rawVs[i] ? vsOf[field](rawVs[i]) : null
        if (rawVs[i] && !got[field]) {
          fail(`모르는 ${VS_COLS[i][0].split('(')[0]} '${rawVs[i]}' — 가능: ${(catalog.vs_vocabulary[field] ?? []).map(vsKo).join(', ')}`)
          rowBroken = true
        }
      }
      const need = ['scene_type', 'activity_types', 'observed_actions', 'interaction_pattern', 'group_size_band']
      const missing = need.filter((f) => !got[f])
      if (missing.length && !rowBroken) { fail('사진 서술을 쓰려면 장소·활동·아이들 행동·상호작용·인원을 모두 채워주세요 (재료만 선택)'); rowBroken = true }
      if (!rowBroken) {
        visual = [{
          object_ref: 'photo_1',
          schema_version: 'vs-1.0',
          extractor_version: 'SYNTH_BUILDER_v1',
          scene_type: [got.scene_type!],
          activity_types: [got.activity_types!],
          ...(got.materials ? { materials: [got.materials] } : {}),
          observed_actions: [got.observed_actions!],
          interaction_pattern: [got.interaction_pattern!],
          group_size_band: got.group_size_band!,
          identity_removed: true,
        }]
      }
    }

    if (rowBroken) continue
    drafts.push({
      seed_id: id,
      domains,
      workspace_state: {
        surface_type: surface!,
        objects_summary: objects,
        selection,
        recent_actions: actions,
        visual_semantics: visual,
      },
    })
  }
  return { drafts, errors }
}
