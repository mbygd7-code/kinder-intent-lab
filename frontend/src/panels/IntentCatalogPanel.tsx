/**
 * 의도 목록·수정 제안 — 70개 의도의 카탈로그 (2026-07-17 사용자 요청).
 *
 * 계층 분리(정직성): 한글 이름·화면 설명은 **표시 계층** — 비밀번호(PIN) 확인 후 즉시 수정
 * (온톨로지 버전·의미 정의는 불변, 거버넌스 기록). 정의 변경·추가·이동·삭제는 **제안 대기열**
 * 로만 — 승인해도 '반영 예약'이고 실반영은 운영 경로(버전 규칙)다. intent_id는 수정 불가.
 */
import { useEffect, useMemo, useRef, useState } from 'react'

import {
  bulkDisplayEdit,
  decideChangeRequest,
  fetchChangeRequests,
  fetchIntentCatalog,
  type IntentCatalog,
  type IntentChangeRequest,
  type IntentItem,
  saveIntentDisplay,
  submitChangeRequest,
} from '../api/ontologyAdmin'
import { parseCsv } from './csv'
import { labelOf, setIntentLabelOverrides } from './intentLabels'

const KIND_KO: Record<string, string> = {
  DEFINITION: '정의(의미) 변경', ADD: '새 의도 추가', MOVE: '영역 이동',
  DELETE: '삭제·병합', OTHER: '기타',
}

interface Props {
  onClose: () => void
}

export function IntentCatalogPanel({ onClose }: Props) {
  const [catalog, setCatalog] = useState<IntentCatalog | null>(null)
  const [requests, setRequests] = useState<IntentChangeRequest[]>([])
  const [query, setQuery] = useState('')
  const [pin, setPin] = useState('')
  const [editor, setEditor] = useState('')
  // 비밀번호·수정자 이름이 비었는데 수정/추가를 시도하면 해당 칸을 하이라이트한다
  const [authMiss, setAuthMiss] = useState({ pin: false, name: false })
  const [editId, setEditId] = useState<string | null>(null) // 이름·설명 인라인 편집 중
  const [editName, setEditName] = useState('')
  const [editDesc, setEditDesc] = useState('')
  const [proposeId, setProposeId] = useState<string | null>(null) // 제안 폼 대상('' = 일반)
  const [addOpen, setAddOpen] = useState(false) // + 새 의도 추가(구조화 제안 → 승인 후 반영)
  const [addDomain, setAddDomain] = useState('') // 영역 선택 → 접두어 자동
  const [addSuffix, setAddSuffix] = useState('') // 접두어 뒤 이름 부분만 입력
  const [addName, setAddName] = useState('')
  const [addDesc, setAddDesc] = useState('')
  const [kind, setKind] = useState<'DEFINITION' | 'ADD' | 'MOVE' | 'DELETE' | 'OTHER'>('DEFINITION')
  const [proposal, setProposal] = useState('')
  const [proposer, setProposer] = useState('')
  const [busy, setBusy] = useState(false)
  const [msg, setMsg] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  const load = () => {
    fetchIntentCatalog()
      .then((c) => {
        setCatalog(c)
        // 이름 오버레이를 앱 전역 라벨에 반영(즉석 문답·검수 화면도 새 이름 사용)
        const ov: Record<string, string> = {}
        for (const i of c.items) if (i.name_ko) ov[i.intent_id] = i.name_ko
        setIntentLabelOverrides(ov)
      })
      .catch((e) => setError(e instanceof Error ? e.message : String(e)))
    fetchChangeRequests().then(setRequests).catch(() => {})
  }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => void load(), [])

  // 영역 → 지배 접두어(기존 의도 id에서 도출). 새 의도 id는 이 접두어 + 이름부분으로 조립한다
  // — 접두어(영역)는 규칙이라 '선택', 뒤 이름만 '입력'. 전체 id를 자유 타이핑하지 않는다.
  const domainPrefix = useMemo(() => {
    const counts = new Map<string, Map<string, number>>()
    for (const i of catalog?.items ?? []) {
      const pre = i.intent_id.split('_')[0]
      const m = counts.get(i.domain) ?? new Map<string, number>()
      m.set(pre, (m.get(pre) ?? 0) + 1)
      counts.set(i.domain, m)
    }
    const out = new Map<string, string>()
    for (const [dom, m] of counts) {
      out.set(dom, [...m.entries()].sort((a, b) => b[1] - a[1])[0][0])
    }
    return out
  }, [catalog])
  const domainList = useMemo(() => [...domainPrefix.keys()].sort(), [domainPrefix])
  const existingIds = useMemo(
    () => new Set((catalog?.items ?? []).map((i) => i.intent_id)),
    [catalog],
  )
  const newFullId = addDomain ? `${domainPrefix.get(addDomain) ?? ''}_${addSuffix.trim()}` : ''

  const authed = pin.trim().length > 0 && editor.trim().length > 0
  /** 수정·추가 전 게이트: 비밀번호·이름이 없으면 빈 칸을 하이라이트하고 안내(진행 막음). */
  const requireAuth = (): boolean => {
    const pinEmpty = !pin.trim()
    const nameEmpty = !editor.trim()
    if (pinEmpty || nameEmpty) {
      setAuthMiss({ pin: pinEmpty, name: nameEmpty })
      setMsg(null)
      setError('먼저 🔒 관리자 비밀번호와 수정자 이름을 입력해주세요.')
      return false
    }
    setAuthMiss({ pin: false, name: false })
    setError(null)
    return true
  }

  const groups = useMemo(() => {
    if (!catalog) return []
    const q = query.trim().toLowerCase()
    const hit = (i: IntentItem) =>
      !q || i.intent_id.includes(q) || labelOf(i.intent_id).toLowerCase().includes(q) ||
      i.definition.toLowerCase().includes(q)
    const by = new Map<string, IntentItem[]>()
    for (const i of catalog.items) if (hit(i)) by.set(i.domain, [...(by.get(i.domain) ?? []), i])
    return [...by.entries()]
  }, [catalog, query])

  const startEdit = (i: IntentItem) => {
    if (!requireAuth()) return
    setEditId(i.intent_id)
    setEditName(i.name_ko ?? labelOf(i.intent_id))
    setEditDesc(i.description_ko ?? '')
    setMsg(null)
    setError(null)
  }

  const saveEdit = async () => {
    if (!editId || !requireAuth()) return
    setBusy(true)
    setError(null)
    try {
      await saveIntentDisplay({
        intent_id: editId, pin, edited_by: editor || '운영자',
        name_ko: editName, description_ko: editDesc,
      })
      setMsg(`✓ "${editName}" 저장 완료 — 앱 전체에 바로 반영돼요 (기록 남음)`)
      setEditId(null)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const sendProposal = async () => {
    if (!requireAuth()) return
    setBusy(true)
    setError(null)
    try {
      await submitChangeRequest({
        kind, proposal, proposed_by: proposer,
        intent_id: proposeId || null,
      })
      setMsg('✓ 제안이 접수됐어요 — 아래 대기열에서 확인할 수 있어요')
      setProposal('')
      setProposeId(null)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const decide = async (rid: string, decision: 'approve' | 'reject') => {
    if (!requireAuth()) return
    setBusy(true)
    setError(null)
    try {
      const r = await decideChangeRequest({
        request_id: rid, pin, decision, decided_by: editor || '운영자',
      })
      setMsg(`✓ ${r.message}`)
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const sendAdd = async () => {
    if (!requireAuth()) return
    setBusy(true)
    setError(null)
    try {
      if (!addDomain) throw new Error('영역을 먼저 선택해주세요')
      if (!/^[a-z][a-z0-9_]{1,38}$/.test(addSuffix.trim())) {
        throw new Error('이름 부분은 영문 소문자·숫자·밑줄로 (예: field_trip_plan)')
      }
      if (existingIds.has(newFullId)) throw new Error(`이미 있는 ID예요: ${newFullId}`)
      if (!addName.trim() || !addDesc.trim()) throw new Error('한글 이름과 설명을 채워주세요')
      await submitChangeRequest({
        kind: 'ADD', proposed_by: proposer,
        proposal: `id: ${newFullId} · 영역: ${addDomain} · 이름: ${addName.trim()} · `
          + `설명: ${addDesc.trim()}`,
      })
      setMsg(`✓ 새 의도 제안(${newFullId}) 접수 — 승인되면 버전 규칙에 따라 정식 추가됩니다`)
      setAddOpen(false)
      setAddDomain('')
      setAddSuffix('')
      setAddName('')
      setAddDesc('')
      load()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const fileRef = useRef<HTMLInputElement>(null)
  const CSV_HEADER = ['의도 id (그대로 두세요)', '영역 (그대로)', '이름 (수정 가능)',
    '화면 설명 (수정 가능 · 비우면 원래 정의 사용)', '원래 정의 (참고 · 수정 불가)']

  const download = () => {
    if (!catalog) return
    if (!requireAuth()) return // 내려받기도 비밀번호·이름 필수(누가 가져갔는지 남기는 관례)
    const esc = (v: unknown) => `"${String(v ?? '').replaceAll('"', '""')}"`
    const lines = [CSV_HEADER.join(',')]
    for (const i of [...catalog.items].sort((a, b) => (a.intent_id < b.intent_id ? -1 : 1))) {
      lines.push([
        esc(i.intent_id), esc(i.domain), esc(i.name_ko ?? labelOf(i.intent_id)),
        esc(i.description_ko ?? ''), esc(i.definition),
      ].join(','))
    }
    const blob = new Blob(['﻿' + lines.join('\n')], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `intents_${catalog.ontology_version}.csv`
    a.click()
    URL.revokeObjectURL(url)
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
      const rows = parseCsv(text)
      const byId = new Map(catalog.items.map((i) => [i.intent_id, i]))
      // 바뀐 것만 전송 — 현재 표시값과 비교(이름=오버레이∨정적라벨, 설명=오버레이만)
      const edits = []
      for (const cells of rows.slice(1)) {
        const id = (cells[0] ?? '').replace(/^﻿/, '').trim()
        if (!id) continue
        const item = byId.get(id)
        if (!item) { edits.push({ intent_id: id }); continue } // 없는 id → 서버가 건너뜀 집계
        const name = (cells[2] ?? '').trim()
        const desc = (cells[3] ?? '').trim()
        const curName = item.name_ko ?? labelOf(id)
        const curDesc = item.description_ko ?? ''
        const edit: { intent_id: string; name_ko?: string; description_ko?: string } = { intent_id: id }
        let changed = false
        if (name && name !== curName) { edit.name_ko = name; changed = true }
        if (desc !== curDesc) { edit.description_ko = desc; changed = true }
        if (changed) edits.push(edit)
      }
      if (edits.length === 0) {
        setMsg('바뀐 이름·설명이 없어요 — 반영할 변경이 없습니다.')
        return
      }
      const r = await bulkDisplayEdit({ pin, edited_by: editor, rows: edits })
      setMsg(`✓ ${r.message}`)
      load()
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setBusy(false)
    }
  }

  const pending = requests.filter((r) => r.status === 'PENDING')

  return (
    <div className="gym-backdrop" role="dialog" aria-label="의도 목록">
      <div className="gym-modal help-modal">
        <div className="gym-head">
          <strong className="gym-title">
            🗂 의도 목록 {catalog ? `(${catalog.total}개 · ${catalog.ontology_version})` : ''}
          </strong>
          <span className="intent-head-actions">
            <button type="button" className="dash-btn intent-btn" disabled={busy || !catalog}
                    onClick={download}>⬇ CSV 받기</button>
            <button type="button" className="dash-btn intent-btn" disabled={busy}
                    onClick={() => { if (requireAuth()) fileRef.current?.click() }}>
              ⬆ CSV로 일괄 변경
            </button>
            <input ref={fileRef} type="file" accept=".csv,.txt" hidden onChange={onUpload} />
            <button type="button" className="gym-close" aria-label="닫기" onClick={onClose}>✕</button>
          </span>
        </div>
        <div className="help-body"><div className="help-doc">
        <p className="help-note">
          <strong>이름·화면 설명</strong>은 비밀번호 확인 후 바로 수정돼요(기록 남음).{' '}
          <strong>정의 변경·이동·삭제·새 의도</strong>는 제안으로 접수돼 승인 후 반영됩니다.{' '}
          <strong>기존 의도의 id</strong>는 바꿀 수 없고(시험 정답이 참조), 새 의도만 새 id를 받아요.
          {' '}<strong>[⬇ CSV 받기]</strong>로 목록을 받아 이름·설명을 엑셀에서 고치고{' '}
          <strong>[⬆ CSV로 일괄 변경]</strong>하면 한 번에 반영돼요(구조 변경은 CSV로 안 돼요 — 제안으로).
        </p>

        <div className="help-form">
          <label className="help-field">🔒 관리자 비밀번호
            <input className={`help-input${authMiss.pin ? ' input-missing' : ''}`} type="password"
                   value={pin} placeholder="수정하려면 입력"
                   onChange={(e) => { setPin(e.target.value); setAuthMiss((m) => ({ ...m, pin: false })) }} />
          </label>
          <label className="help-field">수정자 이름
            <input className={`help-input${authMiss.name ? ' input-missing' : ''}`}
                   value={editor} placeholder="예: 명배영"
                   onChange={(e) => { setEditor(e.target.value); setAuthMiss((m) => ({ ...m, name: false })) }} />
          </label>
          <span className={`dash-chip${authed ? '' : ' dash-dim'}`}>
            {authed ? '✏️ 수정 모드 켜짐 — 저장 시 서버가 비밀번호를 검증해요'
                    : '🔒 비밀번호·이름을 입력하면 수정할 수 있어요'}
          </span>
        </div>

        <div className="intent-toolbar">
          <input className="live-quiz-input" value={query} placeholder="의도 검색 (이름·id·정의)"
                 onChange={(e) => setQuery(e.target.value)} />
          <button type="button" className="dash-btn dash-btn-primary intent-btn" disabled={busy}
                  onClick={() => {
                    if (addOpen) { setAddOpen(false); return }
                    if (requireAuth()) { setAddOpen(true); setMsg(null) }
                  }}>
            ＋ 새 의도 추가
          </button>
        </div>

        {addOpen && (
          <div className="intent-edit intent-add">
            <label className="help-field">영역 (접두어 자동)
              <select className="help-input" value={addDomain}
                      onChange={(e) => setAddDomain(e.target.value)}>
                <option value="">— 영역 선택 —</option>
                {domainList.map((d) => (
                  <option key={d} value={d}>{d} ({domainPrefix.get(d)}_…)</option>
                ))}
              </select>
            </label>
            <label className="help-field">이름 부분 (ID 뒤 — 영문)
              <div className="intent-id-compose">
                <span className="intent-id-prefix">
                  {addDomain ? `${domainPrefix.get(addDomain)}_` : '영역_'}
                </span>
                <input className="help-input" value={addSuffix} placeholder="field_trip_plan"
                       disabled={!addDomain}
                       onChange={(e) => setAddSuffix(e.target.value.toLowerCase())} />
              </div>
            </label>
            {newFullId && addSuffix.trim() && (
              <p className="help-note help-dim intent-id-preview">
                만들어질 ID: <span className="intent-id-chip">{newFullId}</span>
              </p>
            )}
            <label className="help-field">한글 이름
              <input className="help-input" value={addName} placeholder="예: 현장학습 계획 쓰기"
                     onChange={(e) => setAddName(e.target.value)} />
            </label>
            <label className="help-field">설명 (무엇을 해주는 의도인지)
              <input className="help-input" value={addDesc}
                     placeholder="예: 장소·일정·안전 항목이 담긴 현장학습 계획안 초안을 쓴다"
                     onChange={(e) => setAddDesc(e.target.value)} />
            </label>
            <label className="help-field">제안자
              <input className="help-input" value={proposer} placeholder="예: 명배영"
                     onChange={(e) => setProposer(e.target.value)} />
            </label>
            <div className="intent-edit-actions">
              <button type="button" className="dash-btn dash-btn-primary intent-btn" disabled={busy}
                      onClick={sendAdd}>접수</button>
              <button type="button" className="dash-btn intent-btn"
                      onClick={() => { setAddOpen(false); setAddDomain(''); setAddSuffix('') }}>
                취소
              </button>
            </div>
            <p className="help-note help-dim">
              접수되면 아래 대기열에 쌓이고, 승인 시 버전 규칙에 따라 정식 등록돼요(자동 등록 없음).
            </p>
          </div>
        )}

        {groups.map(([domain, items]) => (
          <div key={domain}>
            <h3>{domain} <span className="help-dim">({items.length})</span></h3>
            {items.map((i) => (
              <div key={i.intent_id} className="intent-row">
                <div className="intent-row-head">
                  <span className="intent-id-chip">{i.intent_id}</span>
                  <strong>{labelOf(i.intent_id)}</strong>
                  <span className="intent-row-actions">
                    <button type="button" className="dash-btn intent-btn" disabled={busy}
                            onClick={() => startEdit(i)}>✏️ 이름·설명</button>
                    <button type="button" className="dash-btn intent-btn" disabled={busy}
                            onClick={() => { if (requireAuth()) { setProposeId(i.intent_id); setMsg(null) } }}>
                      💬 제안
                    </button>
                  </span>
                </div>
                <p className="dash-card-sub">{i.description_ko ?? i.definition}</p>
                {editId === i.intent_id && (
                  <div className="help-form intent-edit">
                    <label className="help-field">한글 이름
                      <input className="help-input" value={editName}
                             onChange={(e) => setEditName(e.target.value)} />
                    </label>
                    <label className="help-field">화면 설명
                      <input className="help-input" value={editDesc}
                             placeholder="비우면 원 정의 표시"
                             onChange={(e) => setEditDesc(e.target.value)} />
                    </label>
                    <div className="intent-edit-actions">
                      <button type="button" className="dash-btn dash-btn-primary intent-btn"
                              disabled={busy} onClick={saveEdit}>저장</button>
                      <button type="button" className="dash-btn intent-btn"
                              onClick={() => setEditId(null)}>취소</button>
                    </div>
                  </div>
                )}
                {proposeId === i.intent_id && (
                  <div className="help-form intent-edit">
                    <label className="help-field">제안 종류
                      <select className="help-input" value={kind}
                              onChange={(e) => setKind(e.target.value as typeof kind)}>
                        {Object.entries(KIND_KO).map(([k, ko]) => (
                          <option key={k} value={k}>{ko}</option>
                        ))}
                      </select>
                    </label>
                    <label className="help-field">제안 내용
                      <input className="help-input" value={proposal}
                             placeholder="무엇을 어떻게 바꾸면 좋을지"
                             onChange={(e) => setProposal(e.target.value)} />
                    </label>
                    <label className="help-field">제안자
                      <input className="help-input" value={proposer} placeholder="예: 조선생"
                             onChange={(e) => setProposer(e.target.value)} />
                    </label>
                    <div className="intent-edit-actions">
                      <button type="button" className="dash-btn dash-btn-primary intent-btn"
                              disabled={busy} onClick={sendProposal}>접수</button>
                      <button type="button" className="dash-btn intent-btn"
                              onClick={() => setProposeId(null)}>취소</button>
                    </div>
                  </div>
                )}
              </div>
            ))}
          </div>
        ))}

        <h3>📥 변경 제안 대기열 <span className="help-dim">(대기 {pending.length}건)</span></h3>
        {requests.length === 0 && <p className="help-note help-dim">아직 제안이 없어요.</p>}
        {requests.slice(0, 30).map((r) => (
          <div key={r.request_id} className="intent-row">
            <p className="dash-card-sub">
              [{KIND_KO[r.kind] ?? r.kind}] {r.intent_id ? `${labelOf(r.intent_id)} — ` : ''}
              {r.proposal} <span className="help-dim">· {r.proposed_by} · {r.status}</span>
              {r.status === 'PENDING' && (
                <span className="intent-row-actions">
                  <button type="button" className="dash-btn intent-btn" disabled={busy}
                          onClick={() => decide(r.request_id, 'approve')}>승인</button>
                  <button type="button" className="dash-btn intent-btn" disabled={busy}
                          onClick={() => decide(r.request_id, 'reject')}>반려</button>
                </span>
              )}
            </p>
          </div>
        ))}

        {busy && <p className="help-note">처리 중…</p>}
        {error && <p className="help-upload-err">⚠ {error}</p>}
        {msg && <p className="help-note help-upload-ok">{msg}</p>}
        </div></div>
      </div>
    </div>
  )
}
