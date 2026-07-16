/**
 * 시험지(KTIB) 업로드 — 폼 + 독립 모달.
 *
 * 원래 도움말(ExamGuide) 안에만 있었으나, 교사가 찾기 쉽게 메인 톱바 버튼으로도 연다
 * (2026-07-12). 폼(ExamUpload)은 도움말과 톱바 모달이 공유한다 — 동작 동일.
 *
 * 흐름: 파일 선택(CSV·YAML) → 검증(dry-run) → 결과 확인 → [등록 확정]으로 commit.
 * 정직성: 결과 문구·건수는 백엔드 응답 그대로. CSV는 작성자·승인자 필수(감사 추적).
 * BENCHMARK_HOLDOUT 제약(GOLD∧LABELED∧비합성)은 백엔드가 지키며, 여기선 우회하지 않는다.
 */
import { useEffect, useRef, useState } from 'react'

import {
  fetchKtibUploadDetail,
  fetchKtibUploads,
  uploadKtib,
  uploadKtibRows,
  type KtibUploadDetail,
  type KtibUploadRecord,
  type KtibUploadResult,
} from '../api/observatory'
import { canonicalName, examSheetToRows, type ExamSheetResult } from './csv'

/** "2026.07.16 14:30" — 이력 항목의 사람이 읽는 시각 */
function fmtWhen(iso: string | null): string {
  if (!iso) return ''
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}.${p(d.getMonth() + 1)}.${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}`
}

export function ExamUpload() {
  const [busy, setBusy] = useState(false)
  const [reviewerA, setReviewerA] = useState('')
  const [reviewerB, setReviewerB] = useState('')
  // 확정 단계가 다시 쓸 수 있게 제출 함수를 보관 (YAML/시트 공통)
  const [submit, setSubmit] = useState<((commit: boolean) => Promise<KtibUploadResult>) | null>(null)
  const [summary, setSummary] = useState<ExamSheetResult | null>(null) // 시트 자동 집계(kappa 포함)
  const [result, setResult] = useState<KtibUploadResult | null>(null)
  const [error, setError] = useState<string | null>(null)
  const fileRef = useRef<HTMLInputElement>(null)
  // 업로드 이력 — 등록(commit)된 것만. 목록은 경량, 원문은 항목을 펼칠 때 상세로 가져온다.
  const [uploads, setUploads] = useState<KtibUploadRecord[]>([])
  const [openUpload, setOpenUpload] = useState<KtibUploadDetail | null>(null)

  const loadUploads = () =>
    fetchKtibUploads()
      .then(setUploads)
      .catch(() => {
        /* 이력 조회 실패는 업로드 폼을 막지 않는다 — 조용히 비워 둔다 */
      })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => void loadUploads(), [])

  const run = async (fn: (commit: boolean) => Promise<KtibUploadResult>, commit: boolean) => {
    setBusy(true)
    setError(null)
    try {
      const r = await fn(commit)
      setResult(r)
      if (!r.ok) setError(r.message)
      else if (commit) void loadUploads() // 등록 성공 → 이력 즉시 갱신
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
      setResult(null)
    } finally {
      setBusy(false)
    }
  }

  const toggleDetail = (id: string) => {
    if (openUpload?.upload_id === id) {
      setOpenUpload(null)
      return
    }
    setOpenUpload(null)
    fetchKtibUploadDetail(id)
      .then(setOpenUpload)
      .catch(() => {
        /* 상세 조회 실패는 무시 — 목록은 그대로 */
      })
  }

  const onFile = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0]
    if (fileRef.current) fileRef.current.value = '' // 같은 파일 재선택 허용
    if (!file) return
    setResult(null)
    setSummary(null)
    setError(null)
    setSubmit(null)
    // 인코딩 자동 인식: 한국어 Windows 엑셀의 기본 "CSV(쉼표로 분리)"는 UTF-8이 아니라
    // ANSI(CP949)로 저장된다. UTF-8로 엄격 디코딩해 보고 실패하면 euc-kr(=CP949)로 읽는다 —
    // 교사가 저장 형식을 몰라도 한글이 깨지지 않게.
    const buf = await file.arrayBuffer()
    let text: string
    try {
      text = new TextDecoder('utf-8', { fatal: true }).decode(buf)
    } catch {
      text = new TextDecoder('euc-kr').decode(buf)
    }
    // 엑셀 형식(.xlsx/.xls)은 ZIP 바이너리라 파싱 불가 — 확장자와 매직 바이트('PK') 둘 다 검사
    // (확장자만 바꾼 파일까지 잡는다). 엑셀에서 CSV로 저장하도록 정확히 안내한다.
    if (/\.xlsx?$/i.test(file.name) || text.startsWith('PK')) {
      setError(
        '엑셀 파일(.xlsx)은 그대로 올릴 수 없어요. 엑셀에서 [파일 → 다른 이름으로 저장 → ' +
          'CSV UTF-8(쉼표로 분리)]로 저장한 뒤, 그 .csv 파일을 올려주세요. ' +
          '(구글 시트: 파일 → 다운로드 → 쉼표로 구분된 값)',
      )
      return
    }
    const isCsv = /\.csv$/i.test(file.name) || (!/\.ya?ml$/i.test(file.name) && text.includes(','))

    if (!isCsv) {
      // YAML(고급) — 파일이 자체 헤더·검수자·kappa를 담는다
      const fn = (commit: boolean) => uploadKtib(text, commit)
      setSubmit(() => fn)
      await run(fn, false)
      return
    }

    // 쉬운 시트(O/X) 경로 — 검수자 두 분 이름이 먼저 필요하고, kappa는 자동 계산한다
    const a = reviewerA.trim()
    const b = reviewerB.trim()
    if (!a || !b) {
      setError('먼저 위에 검수자 두 분의 이름을 입력해주세요.')
      return
    }
    if (canonicalName(a) === canonicalName(b)) {
      setError('검수자 두 분은 서로 다른 사람이어야 해요 (같은 이름·대소문자만 다른 건 한 사람으로 봐요).')
      return
    }
    let sheet: ExamSheetResult
    try {
      sheet = examSheetToRows(text, a, b)
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
      return
    }
    setSummary(sheet)
    if (sheet.accepted.length === 0) {
      setError('두 검수자가 모두 O로 통과시킨 질문이 아직 없어요 — 등록할 문항이 없어요.')
      return
    }
    // kappa가 null(판정이 전부 동일)이어도 막지 않는다 — 그 경우 관측 일치율로 인증한다(§3-3 v1.6).
    // 최종 통과/거부는 백엔드가 판정한다(임계값은 config 단일 원천 — 프론트 미하드코딩).
    const fn = (commit: boolean) =>
      uploadKtibRows({
        authored_by: a, approved_by: b, episodes: sheet.accepted, commit,
        source_document: text, // 올린 원문 그대로 — 이력 보관용
      })
    setSubmit(() => fn)
    await run(fn, false) // 서버 검증(dry-run)
  }

  const confirmed = result?.ok && !result.dry_run
  const kappaText =
    summary == null ? '' : summary.kappa === null ? '계산 불가' : summary.kappa.toFixed(2)
  // 교사가 이해하는 1차 지표는 '일치율(%)'이다 — kappa는 판정이 쏠리면 음수로 퇴화해 오해를 부른다.
  const agreementText =
    summary == null || summary.agreementRate === null
      ? '—'
      : `${(summary.agreementRate * 100).toFixed(1)}%`
  return (
    <>
      <h3>시험지 업로드</h3>
      <p>
        쉬운 양식(엑셀·구글시트)에 <strong>질문을 쓰고, 검수자 두 분이 O/X만 체크</strong>하면
        일치도(점수)는 <strong>자동 계산</strong>돼요. 파일을 올리면 <strong>검증 → 등록</strong>{' '}
        순으로 반영됩니다. (채점은 운영자가 별도로 실행)
      </p>
      <div className="help-form">
        <label className="help-field">
          검수자 A 이름
          <input
            className="help-input"
            value={reviewerA}
            onChange={(e) => setReviewerA(e.target.value)}
            placeholder="예: 김유아"
          />
        </label>
        <label className="help-field">
          검수자 B 이름
          <input
            className="help-input"
            value={reviewerB}
            onChange={(e) => setReviewerB(e.target.value)}
            placeholder="예: 이교사 (A와 다른 사람)"
          />
        </label>
      </div>
      <div className="help-download">
        <button
          type="button"
          className="view-toggle help-dl-btn"
          disabled={busy}
          onClick={() => fileRef.current?.click()}
        >
          ⬆ 작성한 양식 올리기 (엑셀·CSV)
        </button>
        <input ref={fileRef} type="file" accept=".csv,.yaml,.yml,.txt" hidden onChange={onFile} />
      </div>

      {/* 시트 자동 집계 — 올리기만 하면 점수(kappa)가 여기 바로 나온다 */}
      {summary && (
        <table className="help-table exam-summary">
          <tbody>
            <tr><td>작성한 질문</td><td>{summary.questionsFilled}개</td></tr>
            <tr><td>✅ 두 분 모두 O (등록 대상)</td><td><strong>{summary.bothAgree}개</strong></td></tr>
            <tr><td>✋ 의견 갈림 / 둘 다 X</td><td>{summary.disagreements} / {summary.bothReject}개</td></tr>
            {summary.needJudgment > 0 && (
              <tr><td>⌛ 아직 검수 안 함</td><td>{summary.needJudgment}개</td></tr>
            )}
            <tr>
              <td>두 분 판정 일치율 (자동)</td>
              <td><strong>{agreementText}</strong></td>
            </tr>
            <tr>
              <td className="help-dim">일치도 지표 (kappa · 참고)</td>
              <td>{kappaText}</td>
            </tr>
          </tbody>
        </table>
      )}
      {summary && (
        <p className="help-note">
          등록 기준: 두 분의 <strong>판정 일치율이 높으면</strong> 등록돼요. (kappa는 판정이 한쪽으로
          쏠리면 실제로는 잘 맞아도 낮게 나오는 지표라, 일치율을 함께 봅니다.) 일치율이 낮으면 의견이
          갈린 문항을 정리해 주세요.
        </p>
      )}

      {busy && <p className="help-note">처리 중…</p>}
      {error && <p className="help-upload-err">⚠ {error}</p>}
      {result?.ok && !error && (
        <div className="help-note help-upload-ok">
          {confirmed ? '✓ ' : ''}
          {result.message}
          {result.dry_run && submit && (
            <div className="help-upload-confirm">
              <button
                type="button"
                className="view-toggle help-dl-btn"
                disabled={busy}
                onClick={() => run(submit, true)}
              >
                ✓ 등록 확정
              </button>
            </div>
          )}
        </div>
      )}

      {/* 업로드 이력 — 등록된 것만. 항목을 펼치면 올린 원문 그대로 확인·회수 */}
      {uploads.length > 0 && (
        <div className="exam-history">
          <h3>📋 업로드 이력 <span className="help-dim">({uploads.length}건)</span></h3>
          <ul className="exam-history-list">
            {uploads.map((u) => {
              const open = openUpload?.upload_id === u.upload_id
              const rate = u.agreement_rate == null ? '—' : `${(u.agreement_rate * 100).toFixed(1)}%`
              return (
                <li key={u.upload_id} className="exam-history-item">
                  <button
                    type="button"
                    className="exam-history-head"
                    onClick={() => toggleDetail(u.upload_id)}
                    aria-expanded={open}
                  >
                    <span className="exam-history-when">{fmtWhen(u.created_at)}</span>
                    <span className="exam-history-meta">
                      신규 {u.inserted}문항 · 일치율 {rate}
                      {u.ktib_version ? ` · ${u.ktib_version}` : ''}
                    </span>
                    <span className="exam-history-by">{u.authored_by}</span>
                    <span className="exam-history-caret">{open ? '▾' : '▸'}</span>
                  </button>
                  {open && openUpload && openUpload.upload_id === u.upload_id && (
                    <div className="exam-history-detail">
                      <p className="help-note">
                        작성 <strong>{openUpload.authored_by}</strong> · 승인{' '}
                        <strong>{openUpload.approved_by}</strong> · 검수{' '}
                        {openUpload.reviewers.join(', ') || '—'} · 중복 제외{' '}
                        {openUpload.skipped_duplicate} · 등록 후 시험지 {openUpload.eligible_total}문항
                      </p>
                      {openUpload.source_document ? (
                        <>
                          <p className="help-note help-dim">올린 원문:</p>
                          <pre className="exam-history-doc">{openUpload.source_document}</pre>
                        </>
                      ) : (
                        <p className="help-note help-dim">이 업로드는 원문이 보관되지 않았어요.</p>
                      )}
                    </div>
                  )}
                </li>
              )
            })}
          </ul>
        </div>
      )}
    </>
  )
}

/**
 * 톱바에서 여는 독립 시험지 업로드 모달 — 도움말을 거치지 않고 바로 업로드.
 * 시작 양식 다운로드도 함께 둬서 "받아서 채우고 올리기"가 한 화면에서 끝난다.
 * 자세한 형식·규칙은 도움말 → "시험 문항 만들기"로 안내(중복 문서화 회피).
 */
export function ExamUploadModal({
  onClose,
  onOpenHelp,
}: {
  onClose: () => void
  /** 자세한 안내로 이동 — 이 모달을 닫고 도움말(시험 문항 탭)을 연다 */
  onOpenHelp?: () => void
}) {
  return (
    <div className="gym-backdrop" role="dialog" aria-label="시험지 업로드">
      <div className="gym-modal help-modal">
        <div className="help-head">
          <strong className="help-title">시험지 업로드</strong>
          <button type="button" className="gym-close" onClick={onClose} aria-label="닫기">
            ✕
          </button>
        </div>
        <div className="help-body">
          <div className="help-doc">
            <p className="help-note">
              전문가가 만든 <strong>시험지(KTIB)</strong>를 올리는 곳이에요. 아래 양식을 받아
              질문을 채우고(<strong>위험 의도 7개부터</strong> 권장), 검수자 두 분이
              O/X만 체크하면 됩니다. 점수는 자동으로 계산돼요.
            </p>

            <div className="help-download">
              <a className="view-toggle help-dl-btn" href="/ktib_critical7_template.csv" download>
                ⭐ CRITICAL 7개 먼저 (권장 · 7×30칸)
              </a>
              <a className="view-toggle help-dl-btn" href="/ktib_exam_template.csv" download>
                ⬇ 전체 양식 (70×10칸)
              </a>
            </div>

            <ExamUpload />

            <p className="help-note">
              작성법(의도는 그대로 두기 · 질문은 교사 말투로 · O/X 체크 · kappa 자동)이 궁금하면{' '}
              {onOpenHelp ? (
                <button type="button" className="help-inline-link" onClick={onOpenHelp}>
                  도움말 → 시험 문항 만들기
                </button>
              ) : (
                <strong>도움말 → 시험 문항 만들기</strong>
              )}
              에서 그림과 함께 볼 수 있어요.
            </p>
          </div>
        </div>
      </div>
    </div>
  )
}
