/**
 * 화면 씨드 스튜디오 — 킨더버스 화면(발화가 나오는 상황)의 기본값을 웹에서 작성 (2026-07-17 사용자 요청).
 *
 * - 원천은 seeds/situation_seeds_v1.yaml — 서버가 전체 재검증(어휘·vs-1.0·도메인 커버리지)을
 *   통과시킨 저장만 허용한다(우회 없음). 이력은 git 커밋.
 * - 모든 값은 등록된 어휘에서 **선택**한다 — 오타로 어휘를 오염시킬 수 없다.
 * - 최소기준(카드 ≥1 · 사진↔서술 정합 · 선택 수 정합)을 채운 씨드만 다음 증산에서
 *   LLM 확장의 앵커가 된다. [✨ 확장 미리보기]로 저장 없이 확인 가능(실 LLM 1회).
 * - PIN·작성자 없이는 작성·수정·삭제·미리보기 불가 — 미입력 시 입력창 하이라이트(기존 관례).
 */
import { useEffect, useMemo, useRef, useState } from 'react'

import {
  bulkUpsertSeeds,
  createSeed,
  deleteSeed,
  deleteVocab,
  expandPreview,
  fetchSeedCatalog,
  type ExpandPreview,
  type SeedCatalog,
  type SeedDraft,
  type SeedItem,
  type SeedVisualSemantics,
  type SeedWorkspaceState,
  updateSeed,
  upsertVocab,
  type VocabTable,
} from '../api/situationSeeds'

import { buildSeedCsv, parseSeedRows, vsKo } from './seedCsv'

/** 사진 서술 폼 한 블록 — 제출 시 vs-1.0 항목으로 조립된다(단일 선택 → 배열 1개). */
interface VsDraft {
  scene: string
  activity: string
  material: string   // '' = 재료 표시 안 함
  observed: string
  interaction: string
  group: string
}

const EMPTY_VS: VsDraft = {
  scene: 'INDOOR_CLASSROOM', activity: 'FREE_PLAY', material: '',
  observed: 'OBSERVE', interaction: 'PEER_COLLABORATIVE', group: 'SMALL_GROUP',
}

interface Props {
  onClose: () => void
}

export function SituationSeedPanel({ onClose }: Props) {
  const [catalog, setCatalog] = useState<SeedCatalog | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [msg, setMsg] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)

  const [pin, setPin] = useState('')
  const [editor, setEditor] = useState('')
  const [authMiss, setAuthMiss] = useState({ pin: false, name: false })

  const [formOpen, setFormOpen] = useState(false)
  const [editingId, setEditingId] = useState<string | null>(null) // null = 새 씨드
  const [seedId, setSeedId] = useState('')
  const [domains, setDomains] = useState<string[]>([])
  const [surface, setSurface] = useState('')
  const [counts, setCounts] = useState<Record<string, number>>({})
  const [selType, setSelType] = useState('')
  const [selCount, setSelCount] = useState(1)
  const [actions, setActions] = useState<string[]>([])
  const [actionPick, setActionPick] = useState('')
  const [vsBlocks, setVsBlocks] = useState<VsDraft[]>([])

  const [deletingId, setDeletingId] = useState<string | null>(null) // 두 번 클릭 삭제(오클릭 방지)
  const fileRef = useRef<HTMLInputElement>(null)
  const [vocabOpen, setVocabOpen] = useState(false)
  // 어휘 라벨 인라인 수정 초안 + 표별 새 항목 입력 — 키: `${table}:${id}`
  const [labelDrafts, setLabelDrafts] = useState<Record<string, string>>({})
  const [newVocab, setNewVocab] = useState<Record<string, { id: string; label: string }>>({})
  const [preview, setPreview] = useState<ExpandPreview | null>(null)
  const [previewBusy, setPreviewBusy] = useState<string | null>(null)

  const load = () => {
    fetchSeedCatalog()
      .then((c) => { setCatalog(c); setError(null) })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => void load(), [])

  const vocab = catalog?.vocabulary
  const surfaceKeys = useMemo(() => Object.keys(vocab?.surface_types ?? {}), [vocab])
  const objectKeys = useMemo(() => Object.keys(vocab?.object_kinds ?? {}), [vocab])
  const actionKeys = useMemo(() => Object.keys(vocab?.actions ?? {}), [vocab])

  const authed = pin.trim().length > 0 && editor.trim().length > 0
  /** 작성·수정·삭제·미리보기 전 게이트 — 비면 해당 입력창 하이라이트 + 안내(진행 막음). */
  const requireAuth = (): boolean => {
    const pinEmpty = !pin.trim()
    const nameEmpty = !editor.trim()
    if (pinEmpty || nameEmpty) {
      setAuthMiss({ pin: pinEmpty, name: nameEmpty })
      setMsg(null)
      setError('먼저 🔒 관리자 비밀번호와 작성자 이름을 입력해주세요.')
      return false
    }
    setAuthMiss({ pin: false, name: false })
    setError(null)
    return true
  }

  /** 씨드 상황을 검수 화면과 같은 문장으로 — 어휘 라벨은 서버 vocabulary가 원천. */
  const summaryLines = (ws: SeedWorkspaceState): string[] => {
    if (!vocab) return []
    const lines: string[] = []
    lines.push(`보고 있던 화면: ${vocab.surface_types[ws.surface_type] ?? ws.surface_type}`)
    const cards = Object.entries(ws.objects_summary ?? {})
      .map(([k, n]) => `${vocab.object_kinds[k] ?? k} ${n}`)
    if (cards.length) lines.push(`화면에 놓인 카드: ${cards.join(' · ')}`)
    const sel = ws.selection as { type?: string; count?: number }
    if (sel?.type) lines.push(`선택 중: ${vocab.object_kinds[sel.type] ?? sel.type} ${sel.count ?? 1}개`)
    if (ws.recent_actions?.length) {
      lines.push(`직전 행동: ${ws.recent_actions.map((a) => vocab.actions[a] ?? a).join(' → ')}`)
    }
    return lines
  }

  // --- 폼 조립 ---

  const resetForm = () => {
    setEditingId(null)
    setSeedId('')
    setDomains([])
    setSurface(surfaceKeys[0] ?? '')
    setCounts({})
    setSelType('')
    setSelCount(1)
    setActions([])
    setActionPick('')
    setVsBlocks([])
  }

  const openNewForm = () => {
    if (!requireAuth()) return
    resetForm()
    setSeedId('')
    setFormOpen(true)
    setMsg(null)
  }

  const openEditForm = (s: SeedItem) => {
    if (!requireAuth()) return
    setEditingId(s.seed_id)
    setSeedId(s.seed_id)
    setDomains(s.domains)
    setSurface(s.workspace_state.surface_type)
    setCounts({ ...s.workspace_state.objects_summary })
    const sel = s.workspace_state.selection as { type?: string; count?: number }
    setSelType(sel?.type ?? '')
    setSelCount(sel?.count ?? 1)
    setActions([...s.workspace_state.recent_actions])
    setVsBlocks(s.workspace_state.visual_semantics.map((v) => ({
      scene: v.scene_type?.[0] ?? 'UNKNOWN',
      activity: v.activity_types?.[0] ?? 'UNKNOWN',
      material: v.materials?.[0] ?? '',
      observed: v.observed_actions?.[0] ?? 'UNKNOWN',
      interaction: v.interaction_pattern?.[0] ?? 'UNKNOWN',
      group: v.group_size_band ?? 'UNKNOWN',
    })))
    setFormOpen(true)
    setMsg(null)
  }

  const photoCount = counts.photo ?? 0
  const totalCards = Object.values(counts).reduce((a, b) => a + b, 0)

  /** 최소기준 체크리스트(작성 중 실시간) — 서버 판정과 같은 규칙, 표현만 폼에 맞춤. */
  const checklist: Array<{ ok: boolean; text: string }> = [
    { ok: totalCards >= 1, text: '화면에 카드 1개 이상 (사진·글 등)' },
    {
      ok: photoCount === 0 || vsBlocks.length >= 1,
      text: '사진이 있으면 사진 서술 1개 이상 (없으면 서술 없음)',
    },
    {
      ok: !selType || (selCount <= (counts[selType] ?? 0)),
      text: '선택한 수 ≤ 화면의 해당 카드 수',
    },
  ]
  const readyDraft = checklist.every((c) => c.ok)

  const buildDraft = (): SeedDraft => {
    const objects: Record<string, number> = {}
    for (const [k, n] of Object.entries(counts)) if (n > 0) objects[k] = n
    const vs: SeedVisualSemantics[] = photoCount > 0
      ? vsBlocks.map((b, i) => ({
          object_ref: `photo_${i + 1}`,
          schema_version: 'vs-1.0',
          extractor_version: 'SYNTH_BUILDER_v1',
          scene_type: [b.scene],
          activity_types: [b.activity],
          ...(b.material ? { materials: [b.material] } : {}),
          observed_actions: [b.observed],
          interaction_pattern: [b.interaction],
          group_size_band: b.group,
          identity_removed: true,
        }))
      : []
    return {
      seed_id: seedId.trim(),
      domains,
      workspace_state: {
        surface_type: surface,
        objects_summary: objects,
        selection: selType ? { type: selType, count: selCount } : {},
        recent_actions: actions,
        visual_semantics: vs,
      },
    }
  }

  const submit = async () => {
    if (!requireAuth()) return
    if (!seedId.trim()) { setError('씨드 이름(id)을 입력하세요 — 예: photo_album_field_trip'); return }
    setBusy(true)
    setError(null)
    try {
      const input = { pin: pin.trim(), editor: editor.trim(), seed: buildDraft() }
      if (editingId) await updateSeed(input)
      else await createSeed(input)
      setMsg(editingId ? `수정 저장 완료 — ${seedId}` : `새 씨드 저장 완료 — ${seedId}`)
      setFormOpen(false)
      resetForm()
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const remove = async (sid: string) => {
    if (!requireAuth()) return
    if (deletingId !== sid) { setDeletingId(sid); return } // 첫 클릭 = 확인 대기
    setBusy(true)
    setError(null)
    try {
      await deleteSeed({ pin: pin.trim(), editor: editor.trim(), seedId: sid })
      setMsg(`삭제 완료 — ${sid}`)
      setDeletingId(null)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setDeletingId(null)
    } finally {
      setBusy(false)
    }
  }

  const runPreview = async (sid: string) => {
    if (!requireAuth()) return
    setPreviewBusy(sid)
    setPreview(null)
    setError(null)
    try {
      setPreview(await expandPreview({ pin: pin.trim(), seedId: sid }))
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setPreviewBusy(null)
    }
  }

  const saveVocab = async (table: VocabTable, vocabId: string, labelKo: string) => {
    if (!requireAuth()) return
    if (!vocabId.trim() || !labelKo.trim()) { setError('어휘 id(영문)와 한글 라벨을 모두 입력하세요.'); return }
    setBusy(true)
    setError(null)
    try {
      await upsertVocab({ pin: pin.trim(), editor: editor.trim(), table, vocabId: vocabId.trim(), labelKo: labelKo.trim() })
      setMsg(`어휘 저장 완료 — ${vocabId} (폼·CSV·검수 화면에 바로 반영돼요)`)
      setLabelDrafts((d) => { const n = { ...d }; delete n[`${table}:${vocabId.trim()}`]; return n })
      setNewVocab((d) => ({ ...d, [table]: { id: '', label: '' } }))
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const removeVocab = async (table: VocabTable, vocabId: string) => {
    if (!requireAuth()) return
    setBusy(true)
    setError(null)
    try {
      await deleteVocab({ pin: pin.trim(), editor: editor.trim(), table, vocabId })
      setMsg(`어휘 삭제 완료 — ${vocabId}`)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e)) // 사용 중이면 씨드 id와 함께 거부 사유가 온다
    } finally {
      setBusy(false)
    }
  }

  const download = () => {
    if (!catalog) return
    if (!requireAuth()) return // 내려받기도 비밀번호·이름 필수(의도 목록 CSV와 동일 관례)
    const blob = new Blob(['\uFEFF' + buildSeedCsv(catalog)], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `situation_seeds_${catalog.version}.csv`
    a.click()
    URL.revokeObjectURL(url)
    setMsg('CSV 폼을 내려받았어요 — 엑셀에서 행을 고치거나 추가한 뒤 [⬆ CSV 업로드]하세요.')
  }

  const onUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (fileRef.current) fileRef.current.value = ''
    if (!file || !catalog) return
    if (!requireAuth()) return
    setBusy(true)
    setError(null)
    setMsg(null)
    try {
      // 인코딩 자동 인식(엑셀 CP949 대비)
      const buf = await file.arrayBuffer()
      let text: string
      try {
        text = new TextDecoder('utf-8', { fatal: true }).decode(buf)
      } catch {
        text = new TextDecoder('euc-kr').decode(buf)
      }
      const { drafts, errors } = parseSeedRows(text, catalog)
      if (errors.length) {
        const head = errors.slice(0, 5).join('\n')
        setError(`CSV에 문제가 있어 반영하지 않았어요 (부분 반영 없음):\n${head}${errors.length > 5 ? `\n…외 ${errors.length - 5}건` : ''}`)
        return
      }
      if (!drafts.length) { setMsg('반영할 행이 없어요 — 씨드id가 채워진 행이 필요해요.'); return }
      const r = await bulkUpsertSeeds({ pin: pin.trim(), editor: editor.trim(), seeds: drafts })
      setMsg(`✓ CSV 반영 완료 — 새 씨드 ${r.created}개 · 수정 ${r.updated}개 (총 ${r.total}개)`)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const readyTotal = catalog?.seeds.filter((s) => s.ready).length ?? 0

  return (
    <div className="gym-backdrop" role="dialog" aria-label="화면 씨드 스튜디오">
      <div className="gym-modal help-modal">
        <div className="gym-head">
          <strong className="gym-title">
            🖥 화면 씨드 스튜디오 {catalog ? `(${catalog.seeds.length}개 · 확장 가능 ${readyTotal})` : ''}
          </strong>
          <span className="intent-head-actions">
            <button type="button" className="dash-btn intent-btn" disabled={busy || !catalog}
                    onClick={download}>⬇ CSV 폼 받기</button>
            <button type="button" className="dash-btn intent-btn" disabled={busy || !catalog}
                    onClick={() => { if (requireAuth()) fileRef.current?.click() }}>
              ⬆ CSV 업로드
            </button>
            <input ref={fileRef} type="file" accept=".csv,.txt" hidden onChange={onUpload} />
            <button type="button" className="gym-close" aria-label="닫기" onClick={onClose}>✕</button>
          </span>
        </div>
        <div className="help-body"><div className="help-doc">
        <p className="help-note">
          씨드는 <strong>발화가 나오는 킨더버스 화면의 기본값</strong>이에요. 여기서 작성하면{' '}
          <code>seeds/situation_seeds_v1.yaml</code>(원천 파일)에 저장되고, <strong>최소기준을 채운
          씨드는 다음 증산 때 AI가 변형 {catalog?.scenario_variants ?? '?'}개씩으로 확장</strong>해
          다양한 실제 상황 시나리오가 됩니다. 모든 값은 등록된 어휘에서 고르기만 해요 — 새 어휘(화면
          종류·행동·카드)가 필요하면 <strong>[🗂 어휘 관리]</strong>에서 먼저 등록하세요.{' '}
          <strong>[⬇ CSV 폼 받기]</strong>로 현재 씨드를 엑셀 양식으로 받아 행을 고치거나 새 행을
          추가하고, <strong>[⬆ CSV 업로드]</strong>하면 한 번에 반영돼요(한 행이라도 틀리면 전체 보류).
        </p>

        <div className="help-form">
          <label className="help-field">🔒 관리자 비밀번호
            <input className={`help-input${authMiss.pin ? ' input-missing' : ''}`} type="password"
                   value={pin} placeholder="작성하려면 입력"
                   onChange={(e) => { setPin(e.target.value); setAuthMiss((m) => ({ ...m, pin: false })) }} />
          </label>
          <label className="help-field">작성자 이름
            <input className={`help-input${authMiss.name ? ' input-missing' : ''}`}
                   value={editor} placeholder="예: 명배영"
                   onChange={(e) => { setEditor(e.target.value); setAuthMiss((m) => ({ ...m, name: false })) }} />
          </label>
          <span className={`dash-chip${authed ? '' : ' dash-dim'}`}>
            {authed ? '✏️ 작성 모드 켜짐 — 저장 시 서버가 비밀번호를 검증해요'
                    : '🔒 비밀번호·이름을 입력하면 작성할 수 있어요'}
          </span>
        </div>

        {error && <p className="gym-error">{error}</p>}
        {msg && <p className="gold-review-msg">{msg}</p>}

        <div className="seed-toolbar">
          <span className="seed-toolbar-note dash-card-sub">
            영역마다 씨드 {catalog?.scenario_variants ?? 4}개 이상을 권장해요 — 부족하면 같은
            씨드가 되풀이 사용돼요.
          </span>
          <button type="button" className="dash-btn intent-btn" disabled={busy}
                  onClick={() => { if (vocabOpen) { setVocabOpen(false); return } if (requireAuth()) setVocabOpen(true) }}>
            {vocabOpen ? '어휘 닫기' : '🗂 어휘 관리 (화면·행동·카드)'}
          </button>
          <button type="button" className="dash-btn dash-btn-primary intent-btn" disabled={busy}
                  onClick={() => { if (formOpen) { setFormOpen(false); return } openNewForm() }}>
            {formOpen ? '폼 닫기' : '＋ 새 씨드 만들기'}
          </button>
        </div>

        {vocabOpen && catalog && vocab && (
          <div className="seed-section">
            <div className="seed-section-head">
              <strong className="seed-section-title">🗂 어휘 관리</strong>
              <span className="seed-section-sub">
                수정하면 작성 폼 · CSV 폼 · 검수 화면 라벨에 모두 자동 반영돼요.{' '}
                <strong>id는 킨더버스 화면 계약과 동일</strong>(영문 소문자)해야 하고,
                씨드가 쓰는 id는 삭제할 수 없어요(라벨만 수정).
              </span>
            </div>
            <div className="seed-vocab-grid">
              {([
                ['surface_types', '보고 있던 화면', vocab.surface_types],
                ['actions', '직전 행동', vocab.actions],
                ['object_kinds', '카드 종류', vocab.object_kinds],
              ] as Array<[VocabTable, string, Record<string, string>]>).map(([table, title, entries]) => (
                <div key={table} className="seed-vocab-card">
                  <div className="seed-vocab-card-head">
                    <strong>{title}</strong>
                    <span className="dash-chip">{Object.keys(entries).length}개</span>
                  </div>
                  {Object.entries(entries).map(([vid, label]) => {
                    const draftKey = `${table}:${vid}`
                    const draft = labelDrafts[draftKey] ?? label
                    return (
                      <div key={vid} className="seed-vocab-row">
                        <code className="seed-vocab-id" title={vid}>{vid}</code>
                        <input className="help-input" value={draft}
                               aria-label={`${title} ${vid} 라벨`}
                               onChange={(e) => setLabelDrafts((d) => ({ ...d, [draftKey]: e.target.value }))} />
                        <span className="seed-vocab-actions">
                          <button type="button" className="dash-btn intent-btn seed-btn-sm"
                                  disabled={busy || draft === label}
                                  onClick={() => saveVocab(table, vid, draft)}>저장</button>
                          <button type="button" className="dash-btn intent-btn seed-btn-sm" disabled={busy}
                                  onClick={() => removeVocab(table, vid)}>삭제</button>
                        </span>
                      </div>
                    )
                  })}
                  <div className="seed-vocab-row seed-vocab-add">
                    <input className="help-input" placeholder="새 id (영문: art_board)"
                           aria-label={`${title} 새 id`}
                           value={newVocab[table]?.id ?? ''}
                           onChange={(e) => setNewVocab((d) => ({ ...d, [table]: { id: e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_'), label: d[table]?.label ?? '' } }))} />
                    <input className="help-input" placeholder="한글 라벨 (예: 미술 보드 화면)"
                           aria-label={`${title} 새 라벨`}
                           value={newVocab[table]?.label ?? ''}
                           onChange={(e) => setNewVocab((d) => ({ ...d, [table]: { id: d[table]?.id ?? '', label: e.target.value } }))} />
                    <span className="seed-vocab-actions">
                      <button type="button" className="dash-btn dash-btn-primary intent-btn seed-btn-sm"
                              disabled={busy}
                              onClick={() => saveVocab(table, newVocab[table]?.id ?? '', newVocab[table]?.label ?? '')}>
                        ＋ 추가
                      </button>
                    </span>
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {formOpen && catalog && vocab && (
          <div className="seed-section seed-form">
            <div className="seed-section-head">
              <strong className="seed-section-title">
                {editingId ? `✏️ 씨드 수정 — ${editingId}` : '＋ 새 씨드 만들기'}
              </strong>
              <span className="seed-section-sub">발화가 나오는 킨더버스 화면 한 장면을 조립해요</span>
            </div>

            <div className="seed-form-grid2">
              <label className="seed-field">씨드 이름 (영문 id{editingId ? ' — 수정 중엔 불변' : ''})
                <input className="help-input" value={seedId} disabled={!!editingId}
                       placeholder="예: photo_album_field_trip"
                       onChange={(e) => setSeedId(e.target.value.toLowerCase().replace(/[^a-z0-9_]/g, '_'))} />
              </label>
              <label className="seed-field">보고 있던 화면
                <select className="help-input" value={surface}
                        onChange={(e) => setSurface(e.target.value)}>
                  {surfaceKeys.map((k) => (
                    <option key={k} value={k}>{vocab.surface_types[k]}</option>
                  ))}
                </select>
              </label>
            </div>

            <div className="seed-fieldset">
              <span className="seed-fieldset-title">쓰일 영역 <em>(모두 해제 = 전체 영역)</em></span>
              <div className="seed-chip-row">
                {catalog.domains.map((d) => (
                  <button key={d} type="button"
                          className={`dash-chip seed-chip${domains.includes(d) ? ' seed-chip-on' : ''}`}
                          onClick={() => setDomains((cur) =>
                            cur.includes(d) ? cur.filter((x) => x !== d) : [...cur, d])}>
                    {d}
                  </button>
                ))}
              </div>
            </div>

            <div className="seed-fieldset">
              <span className="seed-fieldset-title">화면 구성 <em>(화면에 놓인 카드 수와 선택 상태)</em></span>
              <div className="seed-form-row">
                {objectKeys.map((k) => (
                  <label key={k} className="seed-field">{vocab.object_kinds[k]} 수
                    <input className="help-input" type="number" min={0} max={99}
                           value={counts[k] ?? 0}
                           onChange={(e) => setCounts((c) => ({ ...c, [k]: Math.max(0, Number(e.target.value) || 0) }))} />
                  </label>
                ))}
              </div>
              <div className="seed-form-grid4">
                <label className="seed-field">선택 중인 카드
                  <select className="help-input" value={selType}
                          onChange={(e) => setSelType(e.target.value)}>
                    <option value="">선택 없음</option>
                    {objectKeys.map((k) => (
                      <option key={k} value={k}>{vocab.object_kinds[k]}</option>
                    ))}
                  </select>
                </label>
                {selType && (
                  <label className="seed-field">선택한 수
                    <input className="help-input" type="number" min={1} max={99}
                           value={selCount}
                           onChange={(e) => setSelCount(Math.max(1, Number(e.target.value) || 1))} />
                  </label>
                )}
              </div>
            </div>

            <div className="seed-fieldset">
              <span className="seed-fieldset-title">직전 행동 <em>(순서대로 — 칩을 클릭하면 제거)</em></span>
              <div className="seed-chip-row">
                {actions.length === 0 && <span className="dash-card-sub">아직 없음 — 아래에서 골라 추가하세요</span>}
                {actions.map((a, i) => (
                  <button key={`${a}-${i}`} type="button" className="dash-chip seed-chip seed-chip-on"
                          title="클릭하면 제거"
                          onClick={() => setActions((cur) => cur.filter((_, j) => j !== i))}>
                    {i + 1}. {vocab.actions[a]} ✕
                  </button>
                ))}
              </div>
              <div className="seed-action-picker">
                <select className="help-input seed-action-pick" value={actionPick}
                        onChange={(e) => setActionPick(e.target.value)}>
                  <option value="">— 행동 고르기 —</option>
                  {actionKeys.map((k) => (
                    <option key={k} value={k}>{vocab.actions[k]}</option>
                  ))}
                </select>
                <button type="button" className="dash-btn intent-btn" disabled={!actionPick}
                        onClick={() => { if (actionPick) { setActions((c) => [...c, actionPick]); setActionPick('') } }}>
                  ＋ 행동 추가
                </button>
              </div>
            </div>

            {photoCount > 0 && (
              <div className="seed-fieldset">
                <span className="seed-fieldset-title">
                  사진 서술 <em>(화면 속 사진에 찍힌 것 — 사진 {photoCount}장 · 서술 {vsBlocks.length}개)</em>
                </span>
                {vsBlocks.map((b, i) => (
                  <div key={i} className="seed-vs-block">
                    <div className="seed-vs-block-head">
                      <span className="dash-chip">사진 {i + 1}</span>
                      <button type="button" className="dash-btn intent-btn seed-btn-sm"
                              onClick={() => setVsBlocks((cur) => cur.filter((_, j) => j !== i))}>
                        서술 제거
                      </button>
                    </div>
                    <div className="seed-form-grid3">
                      {([
                        ['scene', 'scene_type', '장소'],
                        ['activity', 'activity_types', '활동'],
                        ['material', 'materials', '재료(선택)'],
                        ['observed', 'observed_actions', '아이들 행동'],
                        ['interaction', 'interaction_pattern', '상호작용'],
                        ['group', 'group_size_band', '인원'],
                      ] as Array<[keyof VsDraft, string, string]>).map(([field, vkey, label]) => (
                        <label key={field} className="seed-field">{label}
                          <select className="help-input" value={b[field]}
                                  onChange={(e) => setVsBlocks((cur) =>
                                    cur.map((x, j) => (j === i ? { ...x, [field]: e.target.value } : x)))}>
                            {field === 'material' && <option value="">표시 안 함</option>}
                            {(catalog.vs_vocabulary[vkey] ?? []).map((v) => (
                              <option key={v} value={v}>{vsKo(v)}</option>
                            ))}
                          </select>
                        </label>
                      ))}
                    </div>
                  </div>
                ))}
                <button type="button" className="dash-btn intent-btn seed-add-inline"
                        onClick={() => setVsBlocks((cur) => [...cur, { ...EMPTY_VS }])}>
                  ＋ 사진 서술 추가
                </button>
              </div>
            )}

            <ul className="seed-checklist">
              {checklist.map((c) => (
                <li key={c.text} className={c.ok ? 'seed-check-ok' : 'seed-check-no'}>
                  {c.ok ? '✅' : '⚠️'} {c.text}
                </li>
              ))}
              <li className={readyDraft ? 'seed-check-ok' : 'seed-check-no'}>
                {readyDraft
                  ? '✨ 최소기준 충족 — 저장하면 다음 증산에서 자동 확장돼요'
                  : 'ℹ️ 기준 미달이어도 저장은 돼요 — 단, 확장 없이 원본만 쓰여요'}
              </li>
            </ul>

            <div className="seed-form-actions">
              <button type="button" className="dash-btn intent-btn" disabled={busy}
                      onClick={() => { setFormOpen(false); resetForm() }}>
                취소
              </button>
              <button type="button" className="dash-btn dash-btn-primary intent-btn" disabled={busy}
                      onClick={submit}>
                {editingId ? '수정 저장' : '씨드 저장'}
              </button>
            </div>
          </div>
        )}

        {!catalog && !error && <p className="dash-card-sub">씨드를 불러오는 중…</p>}

        <div className="seed-list">
          {catalog?.seeds.map((s) => (
            <div key={s.seed_id} className="seed-card">
              <div className="seed-card-head">
                <strong>{s.seed_id}</strong>
                <span className={`dash-chip${s.ready ? ' seed-chip-on' : ' dash-dim'}`}>
                  {s.ready ? '✨ 확장 가능' : '⚠️ 최소기준 미달'}
                </span>
                <span className="dash-card-sub">
                  {s.domains.length ? s.domains.join(' · ') : '전체 영역'}
                </span>
              </div>
              {summaryLines(s.workspace_state).map((line) => (
                <div key={line} className="review-situation-line">{line}</div>
              ))}
              {!s.ready && s.unmet.map((u) => (
                <div key={u} className="seed-unmet">⚠️ {u}</div>
              ))}
              <div className="seed-card-actions">
                <button type="button" className="dash-btn intent-btn" disabled={busy}
                        onClick={() => openEditForm(s)}>✏️ 수정</button>
                <button type="button" className="dash-btn intent-btn" disabled={busy}
                        onClick={() => remove(s.seed_id)}>
                  {deletingId === s.seed_id ? '정말 삭제할까요?' : '🗑 삭제'}
                </button>
                {s.ready && (
                  <button type="button" className="dash-btn intent-btn"
                          disabled={busy || previewBusy !== null}
                          onClick={() => runPreview(s.seed_id)}>
                    {previewBusy === s.seed_id ? '확장 중…' : `✨ 확장 미리보기 (${catalog.scenario_variants}개)`}
                  </button>
                )}
              </div>
              {preview?.anchor_seed_id === s.seed_id && (
                <div className="seed-preview">
                  <p className="dash-card-sub">
                    방금 실 AI 호출 1회로 만든 확장 예시예요 — <strong>저장되지 않았어요</strong>.
                    실제 확장은 다음 증산 때 자동으로 일어나요.
                  </p>
                  {preview.variants.map((v, i) => (
                    <div key={i} className="seed-preview-variant">
                      <span className="dash-chip">변형 {i + 1}</span>
                      {summaryLines(v).map((line) => (
                        <div key={line} className="review-situation-line">{line}</div>
                      ))}
                    </div>
                  ))}
                </div>
              )}
            </div>
          ))}
        </div>
        </div></div>
      </div>
    </div>
  )
}
