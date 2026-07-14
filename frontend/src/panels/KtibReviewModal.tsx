/**
 * 시험지 2차 검수 모달 (§3-3·§8-2) — 웹에서 1~5 평점으로 검수하는 2대 컴퓨터 흐름.
 *
 * ① 문항 작성: 영역별로 질문을 쓰고 작성자(A)가 1~5 평가 → 제출하면 "검수 대기"로 간다.
 * ② 검수 대기: 다른 사람이 올린 배치를 blind로(작성자 점수 안 보임) 1~5 평가 → 제출하면
 *    서버가 가중 kappa·총점을 계산해 준다. 두 명 검수 완료 + 일치도 통과면 [등록] 활성.
 * ③ 내 제출: 내가 올린 배치의 상태(대기중/검수완료/등록됨) — 등록 가능하면 여기서도 등록.
 *
 * 정직성: 점수(kappa)는 서버가 계산한 값만 표시한다. 2차 검수자는 작성자 점수를 보지 못한다
 * (anti-anchoring). 등록은 dry-run(검증)→확정 2단계 — 공유 시험지에 함부로 쓰지 않는다.
 */
import { useCallback, useEffect, useMemo, useState } from 'react'

import {
  createCandidateBatch,
  listCandidates,
  registerCandidateBatch,
  submitSecondReview,
  type BatchSummary,
  type CandidateItemIn,
  type PendingBatch,
  type RegisterResult,
} from '../api/ktibReview'
import { REGIONS, type RegionId } from '../brain3d/regions'
import { useBrainStore } from '../brain3d/store'
import { ArenaRunButton } from '../dashboard/ArenaRunButton'
import { labelOf } from './intentLabels'

type Tab = 'write' | 'pending' | 'mine'
const MAX_PER_INTENT = 10

/** 1~5 바로 선택기 — 클릭한 숫자만 강조 */
function RatingPicker({
  value,
  onChange,
  disabled,
}: {
  value: number | null
  onChange: (n: number) => void
  disabled?: boolean
}) {
  return (
    <span className="rating-pick" role="radiogroup" aria-label="1~5 점수">
      {[1, 2, 3, 4, 5].map((n) => (
        <button
          key={n}
          type="button"
          disabled={disabled}
          className={`rating-dot${value === n ? ' rating-dot-on' : ''}`}
          aria-pressed={value === n}
          onClick={() => onChange(n)}
        >
          {n}
        </button>
      ))}
    </span>
  )
}

const STATUS_KO: Record<BatchSummary['status'], string> = {
  AWAITING_SECOND: '2차 검수 대기중',
  SECOND_DONE: '검수 완료',
  REGISTERED: '등록됨',
}

const kappaText = (k: number | null) => (k == null ? '계산 불가' : k.toFixed(2))

export function KtibReviewModal({
  onClose,
  onComplete,
}: {
  onClose: () => void
  /** 등록(commit) 성공 시 — 뇌 상태 refetch */
  onComplete?: () => void
}) {
  const brain = useBrainStore((s) => s.brain)
  const [name, setName] = useState('')
  const [tab, setTab] = useState<Tab>('write')

  // 영역→의도 목록 (brain.nodes에서 파생 — 정적 맵이 없으므로. 미로딩이면 빈 목록)
  const intentsByRegion = useMemo(() => {
    const map = new Map<RegionId, string[]>(REGIONS.map((r) => [r.id, []]))
    for (const n of brain?.nodes ?? []) {
      const arr = map.get(n.region as RegionId)
      if (arr && !arr.includes(n.intent_id)) arr.push(n.intent_id)
    }
    return map
  }, [brain])

  return (
    <div className="gym-backdrop" role="dialog" aria-label="시험지 검수">
      <div className="gym-modal help-modal">
        <div className="help-head">
          <strong className="help-title">시험지 검수 (1~5 평점)</strong>
          <div className="help-tabs">
            {(
              [
                ['write', '① 문항 작성'],
                ['pending', '② 검수 대기'],
                ['mine', '③ 내 제출'],
              ] as const
            ).map(([t, lbl]) => (
              <button
                key={t}
                type="button"
                className={`view-toggle help-tab${tab === t ? ' help-tab-active' : ''}`}
                aria-pressed={tab === t}
                onClick={() => setTab(t)}
              >
                {lbl}
              </button>
            ))}
          </div>
          {/* 채점 트리거 — 문항 등록 흐름 끝에서 바로 실행(운영자 PIN 게이트, 대시보드와 공유) */}
          <ArenaRunButton />
          <button type="button" className="gym-close" onClick={onClose} aria-label="닫기">
            ✕
          </button>
        </div>

        <div className="help-body">
          <label className="help-field review-name">
            검수자 이름 (내 이름)
            <input
              className="help-input"
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="예: 김유아"
            />
          </label>

          {tab === 'write' && (
            <WriteTab
              name={name}
              intentsByRegion={intentsByRegion}
              hasBrain={!!brain}
            />
          )}
          {tab === 'pending' && <PendingTab name={name} onComplete={onComplete} />}
          {tab === 'mine' && <MineTab name={name} onComplete={onComplete} />}
        </div>
      </div>
    </div>
  )
}

// ---------- ① 문항 작성 (A) ----------

type Draft = { q: string; r: number | null }

function WriteTab({
  name,
  intentsByRegion,
  hasBrain,
}: {
  name: string
  intentsByRegion: Map<RegionId, string[]>
  hasBrain: boolean
}) {
  // 의도별 초안 행들. 접근 시 1행으로 초기화(빈칸 다 안 채워도 됨).
  const [drafts, setDrafts] = useState<Record<string, Draft[]>>({})
  const [openRegion, setOpenRegion] = useState<RegionId | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)

  const rowsOf = (intent: string): Draft[] => drafts[intent] ?? [{ q: '', r: null }]
  const setRows = (intent: string, rows: Draft[]) =>
    setDrafts((d) => ({ ...d, [intent]: rows }))

  const filledCount = useMemo(() => {
    let n = 0
    for (const rows of Object.values(drafts)) n += rows.filter((r) => r.q.trim()).length
    return n
  }, [drafts])

  const submit = async () => {
    setError(null)
    setNotice(null)
    if (!name.trim()) {
      setError('먼저 위에 검수자 이름을 입력해주세요.')
      return
    }
    const items: CandidateItemIn[] = []
    for (const [intent, rows] of Object.entries(drafts)) {
      for (const row of rows) {
        const q = row.q.trim()
        if (!q) continue
        if (row.r == null) {
          setError(`"${labelOf(intent)}"에 쓴 질문에 1~5 점수를 매겨주세요.`)
          return
        }
        items.push({ intent, teacher_prompt: q, rating: row.r })
      }
    }
    if (items.length === 0) {
      setError('작성한 질문이 없어요. 질문을 쓰고 1~5로 평가한 뒤 제출하세요.')
      return
    }
    setBusy(true)
    try {
      const res = await createCandidateBatch(name.trim(), items)
      setDrafts({})
      setOpenRegion(null)
      setNotice(
        `${res.item_count}개 문항을 제출했어요. 이제 "② 검수 대기"에서 다른 선생님이 2차 검수하면 등록할 수 있어요.`,
      )
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  if (!hasBrain) {
    return (
      <p className="help-note">
        뇌 데이터를 불러오는 중이에요(백엔드 연결 필요). 연결되면 영역별로 문항을 쓸 수 있어요.
      </p>
    )
  }

  return (
    <div className="help-doc">
      <p className="help-note">
        영역을 펼쳐 그 의도에 맞는 <strong>질문(교사 말투)</strong>을 쓰고, 작성자로서{' '}
        <strong>1~5</strong>로 평가하세요. 다 채우지 않아도 돼요 — 쓴 것만 제출됩니다. 제출하면
        다른 선생님의 2차 검수를 기다립니다.
      </p>

      {REGIONS.map((region) => {
        const intents = intentsByRegion.get(region.id) ?? []
        const open = openRegion === region.id
        const regionFilled = intents.reduce(
          (n, it) => n + rowsOf(it).filter((r) => r.q.trim()).length,
          0,
        )
        return (
          <div key={region.id} className="review-region">
            <button
              type="button"
              className="review-region-head"
              onClick={() => setOpenRegion(open ? null : region.id)}
            >
              <span className="region-swatch" style={{ backgroundColor: region.color }} />
              <span className="review-region-name">
                {region.label} · {region.ko}
              </span>
              {regionFilled > 0 && <span className="review-region-count">{regionFilled}</span>}
              <span className="review-region-caret">{open ? '▾' : '▸'}</span>
            </button>

            {open && (
              <div className="review-region-body">
                {intents.map((intent) => {
                  const rows = rowsOf(intent)
                  return (
                    <div key={intent} className="review-intent">
                      <div className="review-intent-label">{labelOf(intent)}</div>
                      {rows.map((row, i) => (
                        <div key={i} className="review-write-row">
                          <input
                            className="help-input review-q"
                            value={row.q}
                            placeholder="이 의도에 맞는 교사 말투 질문"
                            onChange={(e) => {
                              const next = rows.slice()
                              next[i] = { ...next[i], q: e.target.value }
                              setRows(intent, next)
                            }}
                          />
                          <RatingPicker
                            value={row.r}
                            onChange={(n) => {
                              const next = rows.slice()
                              next[i] = { ...next[i], r: n }
                              setRows(intent, next)
                            }}
                          />
                        </div>
                      ))}
                      {rows.length < MAX_PER_INTENT && (
                        <button
                          type="button"
                          className="review-add-row"
                          onClick={() => setRows(intent, [...rows, { q: '', r: null }])}
                        >
                          + 문항 추가
                        </button>
                      )}
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        )
      })}

      {error && <p className="help-upload-err">⚠ {error}</p>}
      {notice && <p className="help-note help-upload-ok">✓ {notice}</p>}
      <button type="button" className="cta-train" disabled={busy} onClick={submit}>
        {busy ? '제출 중…' : `제출 (2차 검수 요청) · 작성 ${filledCount}문항`}
      </button>
    </div>
  )
}

// ---------- 등록(dry-run→확정) 공용 ----------

function RegisterControl({
  batchId,
  name,
  onDone,
}: {
  batchId: string
  name: string
  onDone: () => void
}) {
  const [busy, setBusy] = useState(false)
  const [dry, setDry] = useState<RegisterResult | null>(null)
  const [error, setError] = useState<string | null>(null)

  const run = async (commit: boolean) => {
    setBusy(true)
    setError(null)
    try {
      const res = await registerCandidateBatch(batchId, name.trim(), commit)
      if (!res.ok) {
        setError(res.message)
        setDry(null)
        return
      }
      if (commit) {
        setDry(null)
        onDone()
      } else {
        setDry(res)
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="review-register">
      {!dry ? (
        <button type="button" className="cta-train" disabled={busy} onClick={() => run(false)}>
          {busy ? '확인 중…' : '📥 시험지로 등록'}
        </button>
      ) : (
        <div className="help-note help-upload-ok">
          {dry.message}
          <div className="help-upload-confirm">
            <button
              type="button"
              className="view-toggle help-dl-btn"
              disabled={busy}
              onClick={() => run(true)}
            >
              ✓ 등록 확정
            </button>
          </div>
        </div>
      )}
      {error && <p className="help-upload-err">⚠ {error}</p>}
    </div>
  )
}

// ---------- ② 검수 대기 (B) ----------

function PendingTab({ name, onComplete }: { name: string; onComplete?: () => void }) {
  const [pending, setPending] = useState<PendingBatch[]>([])
  const [loading, setLoading] = useState(false)
  const [openId, setOpenId] = useState<string | null>(null)
  const [ratings, setRatings] = useState<Record<string, number | null>>({})
  const [result, setResult] = useState<BatchSummary | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    if (!name.trim()) {
      setPending([])
      return
    }
    setLoading(true)
    setError(null)
    try {
      setPending((await listCandidates(name.trim())).pending)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [name])

  useEffect(() => {
    void reload()
  }, [reload])

  const openBatch = pending.find((b) => b.batch_id === openId) ?? null

  const openReview = (b: PendingBatch) => {
    setOpenId(b.batch_id)
    setResult(null)
    setError(null)
    setRatings(Object.fromEntries(b.items.map((it) => [it.item_id, null])))
  }

  const submit = async () => {
    if (!openBatch) return
    const missing = openBatch.items.some((it) => ratings[it.item_id] == null)
    if (missing) {
      setError('모든 문항에 1~5 점수를 매겨주세요.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      const res = await submitSecondReview(
        openBatch.batch_id,
        name.trim(),
        openBatch.items.map((it) => ({ item_id: it.item_id, rating: ratings[it.item_id]! })),
      )
      setResult(res)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  if (!name.trim()) {
    return <p className="help-note">위에 검수자 이름을 입력하면 나에게 온 검수 대기 목록이 보여요.</p>
  }

  // 검수 상세 화면
  if (openBatch) {
    return (
      <div className="help-doc">
        <button type="button" className="view-toggle" onClick={() => setOpenId(null)}>
          ← 목록으로
        </button>
        <p className="help-note">
          <strong>{openBatch.created_by}</strong> 님이 올린 {openBatch.item_count}문항이에요.{' '}
          <strong>작성자 점수는 보이지 않습니다</strong> — 직접 1~5로 평가해 주세요.
        </p>
        {result ? (
          <div className="help-note help-upload-ok">
            <div>
              검수 완료 · 검수 일치도(kappa) <strong>{kappaText(result.agreement_kappa)}</strong> ·
              두 분 모두 높게 평가한 문항 <strong>{result.accepted_count}개</strong>
            </div>
            {result.registerable ? (
              <RegisterControl
                batchId={result.batch_id}
                name={name}
                onDone={() => {
                  onComplete?.()
                  setOpenId(null)
                  void reload()
                }}
              />
            ) : (
              <p className="review-blocked">
                {result.agreement_kappa == null
                  ? '두 검수자의 점수가 전부 같아 일치도를 계산할 수 없어요 — 서로 독립적으로 평가했는지 확인해 주세요.'
                  : result.accepted_count === 0
                    ? '두 검수자가 모두 높게 평가한 문항이 없어 등록할 수 없어요.'
                    : '검수 일치도가 기준에 못 미쳐 등록할 수 없어요.'}
              </p>
            )}
          </div>
        ) : (
          <>
            <table className="help-table review-review-table">
              <tbody>
                {openBatch.items.map((it) => (
                  <tr key={it.item_id}>
                    <td className="review-intent-cell">{labelOf(it.intent)}</td>
                    <td>{it.teacher_prompt}</td>
                    <td className="review-rate-cell">
                      <RatingPicker
                        value={ratings[it.item_id] ?? null}
                        onChange={(n) => setRatings((r) => ({ ...r, [it.item_id]: n }))}
                      />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {error && <p className="help-upload-err">⚠ {error}</p>}
            <button type="button" className="cta-train" disabled={busy} onClick={submit}>
              {busy ? '제출 중…' : '2차 검수 제출'}
            </button>
          </>
        )}
      </div>
    )
  }

  // 대기 목록
  return (
    <div className="help-doc">
      {loading && <p className="help-note">불러오는 중…</p>}
      {error && <p className="help-upload-err">⚠ {error}</p>}
      {!loading && pending.length === 0 && (
        <p className="help-note">2차 검수를 기다리는 시험지가 없어요. (내가 올린 건 여기 안 떠요)</p>
      )}
      {pending.map((b) => (
        <button key={b.batch_id} type="button" className="review-pending-card" onClick={() => openReview(b)}>
          <span>
            <strong>{b.created_by}</strong> 님의 시험지 · {b.item_count}문항
          </span>
          <span className="review-pending-go">검수하기 →</span>
        </button>
      ))}
    </div>
  )
}

// ---------- ③ 내 제출 (A) ----------

function MineTab({ name, onComplete }: { name: string; onComplete?: () => void }) {
  const [mine, setMine] = useState<BatchSummary[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const reload = useCallback(async () => {
    if (!name.trim()) {
      setMine([])
      return
    }
    setLoading(true)
    setError(null)
    try {
      setMine((await listCandidates(name.trim())).mine)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setLoading(false)
    }
  }, [name])

  useEffect(() => {
    void reload()
  }, [reload])

  if (!name.trim()) {
    return <p className="help-note">위에 검수자 이름을 입력하면 내가 올린 시험지 상태가 보여요.</p>
  }

  return (
    <div className="help-doc">
      {loading && <p className="help-note">불러오는 중…</p>}
      {error && <p className="help-upload-err">⚠ {error}</p>}
      {!loading && mine.length === 0 && (
        <p className="help-note">아직 올린 시험지가 없어요. "① 문항 작성"에서 만들어 제출해 보세요.</p>
      )}
      {mine.map((b) => (
        <div key={b.batch_id} className="review-mine-card">
          <div className="review-mine-head">
            <span className="review-mine-status">{STATUS_KO[b.status]}</span>
            <span className="review-mine-meta">
              {b.item_count}문항
              {b.status !== 'AWAITING_SECOND' && (
                <>
                  {' · '}일치도 {kappaText(b.agreement_kappa)}
                  {' · '}등록 대상 {b.accepted_count}개
                </>
              )}
              {b.ktib_version && <> · 시험지 {b.ktib_version}</>}
            </span>
          </div>
          {b.status === 'SECOND_DONE' && b.registerable && (
            <RegisterControl
              batchId={b.batch_id}
              name={name}
              onDone={() => {
                onComplete?.()
                void reload()
              }}
            />
          )}
        </div>
      ))}
    </div>
  )
}
