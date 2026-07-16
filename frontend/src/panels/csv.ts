/**
 * 최소 CSV 파서 + 시험지 행 변환 — 구글 시트/엑셀에서 받은 CSV를 업로드 행으로.
 *
 * 따옴표 필드(쉼표·줄바꿈 포함) 처리, BOM 제거. 열은 헤더 키워드로 유연 매칭한다
 * (전문가가 열 순서를 바꾸거나 이름을 조금 바꿔도 동작).
 *
 * 교사 친화 양식(2026-07-12): kappa를 직접 적게 하지 않는다 — 두 검수자가 O/X만 체크하면
 * Cohen's kappa를 여기서 자동 계산한다(examSheetToRows). 계산식은 백엔드 aggregator.review의
 * cohens_kappa와 동일 규칙(pe≥1이면 계산 불가 → null, 반올림 없음).
 */
import type { KtibRow } from '../api/observatory'

export function parseCsv(text: string): string[][] {
  const t = text.replace(/^﻿/, '') // BOM 제거
  const rows: string[][] = []
  let row: string[] = []
  let field = ''
  let inQuotes = false
  for (let i = 0; i < t.length; i++) {
    const c = t[i]
    if (inQuotes) {
      if (c === '"') {
        if (t[i + 1] === '"') {
          field += '"'
          i++
        } else inQuotes = false
      } else field += c
    } else if (c === '"') inQuotes = true
    else if (c === ',') {
      row.push(field)
      field = ''
    } else if (c === '\r') {
      /* CRLF의 CR 무시 */
    } else if (c === '\n') {
      row.push(field)
      rows.push(row)
      row = []
      field = ''
    } else field += c
  }
  if (field.length > 0 || row.length > 0) {
    row.push(field)
    rows.push(row)
  }
  // 완전 공백 행 제거
  return rows.filter((r) => r.some((cell) => cell.trim() !== ''))
}

export function ktibRowsFromCsv(text: string): KtibRow[] {
  const grid = parseCsv(text)
  if (grid.length < 2) throw new Error('CSV에 문항이 없어요 (헤더 + 데이터 행이 필요해요)')
  const header = grid[0].map((h) => h.trim())
  const findCol = (re: RegExp) => header.findIndex((h) => re.test(h))
  const iIntent = findCol(/의도\s*id|^intent/i)
  const iPrompt = findCol(/발화|prompt|문제|말/i)
  const iKappa = findCol(/일치|kappa/i)
  const revCols = header
    .map((h, idx) => ({ h, idx }))
    .filter((x) => /검수|review/i.test(x.h))
    .map((x) => x.idx)
  if (iIntent < 0 || iPrompt < 0) {
    throw new Error('CSV에 "의도 id"와 "시험 발화" 열이 필요해요')
  }
  const rows: KtibRow[] = []
  for (let r = 1; r < grid.length; r++) {
    const cells = grid[r]
    const intent = (cells[iIntent] ?? '').trim()
    const prompt = (cells[iPrompt] ?? '').trim()
    if (!intent && !prompt) continue // 빈 행 스킵
    const reviewers = revCols.map((c) => (cells[c] ?? '').trim()).filter(Boolean)
    const kappaRaw = iKappa >= 0 ? (cells[iKappa] ?? '').trim() : ''
    const kappa = kappaRaw === '' ? null : Number(kappaRaw)
    rows.push({
      intent,
      teacher_prompt: prompt,
      reviewers,
      agreement_kappa: kappa !== null && Number.isFinite(kappa) ? kappa : null,
    })
  }
  if (rows.length === 0) throw new Error('CSV에 채워진 문항이 없어요')
  return rows
}

// ---------- 교사 친화 양식: O/X 체크 → kappa 자동 계산 ----------

/** 검수자 이름 정규화 — 백엔드 canonical_reviewer와 같은 규칙(공백 제거 + 소문자화).
 *  "김검수"/"김검수 "/"KIM"↔"kim"을 같은 사람으로 판별해 별칭으로 2인 위장을 막는다. */
export function canonicalName(name: string): string {
  return (name ?? '').trim().toLowerCase()
}

/** 한 칸의 O/X 판정 — 다양한 표기를 관대하게 받는다. 빈칸/미지 = '' (미판정). */
export function readMark(v: string): 'O' | 'X' | '' {
  const s = (v ?? '').trim().toUpperCase()
  if (s === '') return ''
  if (['O', '○', '●', 'ㅇ', 'V', '✓', '✔', 'Y', 'YES', '예', '네', '맞음', '맞다', '1', 'T', 'TRUE', '○'].includes(s))
    return 'O'
  if (['X', '✗', '✘', 'ㄴ', 'N', 'NO', '아니오', '아니요', '아님', '틀림', '0', 'F', 'FALSE'].includes(s))
    return 'X'
  return '' // 알 수 없는 표기는 미판정으로 둔다(지어내지 않음)
}

/**
 * Cohen's kappa — 두 검수자의 판정 배열 일치도. 정의 불가(pe≥1)면 null.
 * 백엔드 aggregator.review.cohens_kappa와 동일 규칙(반올림 없음, 완전 일치를 1.0으로 치지 않음).
 */
export function cohensKappa(a: readonly string[], b: readonly string[]): number | null {
  const n = a.length
  if (n === 0 || n !== b.length) return null
  let observed = 0
  for (let i = 0; i < n; i++) if (a[i] === b[i]) observed++
  observed /= n
  const ca: Record<string, number> = {}
  const cb: Record<string, number> = {}
  for (const x of a) ca[x] = (ca[x] ?? 0) + 1
  for (const x of b) cb[x] = (cb[x] ?? 0) + 1
  let expected = 0
  for (const k of new Set([...Object.keys(ca), ...Object.keys(cb)]))
    expected += ((ca[k] ?? 0) / n) * ((cb[k] ?? 0) / n)
  if (expected >= 1) return null // 변별력 없는 배치 — 계산 불가(완전 동일 판정)
  return (observed - expected) / (1 - expected)
}

export interface ExamSheetResult {
  /** 두 검수자 모두 O + 질문이 채워진 문항 (업로드 대상). kappa·검수자 이름 부착 */
  accepted: KtibRow[]
  /** 자동 계산된 검수 일치도. null = 계산 불가(둘 다 판정한 문항이 없거나 판정이 전부 동일) */
  kappa: number | null
  /** 관측 일치율 = (둘 다 O + 둘 다 X) / judged. O/X 승인의 인증 척도(§3-3 v1.6). null = judged 0 */
  agreementRate: number | null
  questionsFilled: number // 질문이 채워진 문항 수
  judged: number          // 두 검수자가 모두 O/X를 매긴 문항 수(kappa 계산 대상)
  bothAgree: number       // 둘 다 O (= accepted)
  bothReject: number      // 둘 다 X (버릴 문항)
  disagreements: number   // O/X 갈림
  needJudgment: number    // 질문은 있는데 한쪽이라도 판정 안 함
}

/**
 * 교사 친화 양식 → 업로드 행. 각 문항을 두 검수자가 O/X로만 체크하면:
 *  - kappa = 두 검수자 O/X 판정의 Cohen's kappa(자동 계산) — 교사가 숫자를 적지 않는다
 *  - accepted = 질문이 있고 둘 다 O인 문항(= 두 검수자가 정답에 동의). 여기에 kappa·이름 부착
 * 이름은 파일이 아니라 업로드 폼에서 받는다(reviewerA/B). 두 이름이 같으면 검수 성립 안 됨.
 */
export function examSheetToRows(
  text: string,
  reviewerA: string,
  reviewerB: string,
): ExamSheetResult {
  const grid = parseCsv(text)
  if (grid.length < 2) throw new Error('양식에 문항이 없어요 (헤더 + 데이터 행이 필요해요)')
  const header = grid[0].map((h) => h.trim())
  const iIntent = header.findIndex((h) => /의도\s*id|^intent/i.test(h))
  const iPrompt = header.findIndex((h) => /질문|발화|prompt|문제/i.test(h))
  const judgeCols = header
    .map((h, idx) => ({ h, idx }))
    .filter((x) => /검수|판정|review|검토/i.test(x.h))
    .map((x) => x.idx)
  if (iIntent < 0 || iPrompt < 0) {
    throw new Error('양식에 "의도 id"와 "시험 질문" 열이 필요해요 (쉬운 양식을 내려받아 쓰세요)')
  }
  if (judgeCols.length < 2) {
    throw new Error('검수자 판정(O/X) 열이 2개 필요해요 (쉬운 양식의 검수자A·검수자B 칸)')
  }
  const [iA, iB] = judgeCols

  const accepted: KtibRow[] = []
  const judgeA: string[] = []
  const judgeB: string[] = []
  let questionsFilled = 0
  let bothAgree = 0
  let bothReject = 0
  let disagreements = 0
  let needJudgment = 0

  for (let r = 1; r < grid.length; r++) {
    const cells = grid[r]
    const intent = (cells[iIntent] ?? '').trim()
    const prompt = (cells[iPrompt] ?? '').trim()
    if (!prompt) continue // 질문 빈칸 = 미작성(부분 작성 허용) — 건너뜀
    questionsFilled++
    const a = readMark(cells[iA] ?? '')
    const b = readMark(cells[iB] ?? '')
    if (a === '' || b === '') {
      needJudgment++
      continue // 한쪽이라도 판정 안 하면 kappa·채택 대상 아님
    }
    // 두 검수자가 모두 판정한 문항만 kappa 표본에 넣는다
    judgeA.push(a)
    judgeB.push(b)
    if (a === 'O' && b === 'O') {
      bothAgree++
      accepted.push({ intent, teacher_prompt: prompt, reviewers: [reviewerA, reviewerB], agreement_kappa: null })
    } else if (a === 'X' && b === 'X') bothReject++
    else disagreements++
  }

  if (questionsFilled === 0) throw new Error('작성된 질문이 하나도 없어요')

  const kappa = cohensKappa(judgeA, judgeB)
  // 관측 일치율 = 두 검수자가 같은 판정을 낸 비율. O/X 승인은 판정이 O로 쏠려 kappa가
  // base-rate 역설로 퇴화하므로, 백엔드는 이 값으로도 인증한다(§3-3 v1.6).
  const agreementRate = judgeA.length ? (bothAgree + bothReject) / judgeA.length : null
  // accepted 행에 배치 kappa·일치율을 부착(백엔드 계약: 문항별 agreement_kappa·agreement_rate)
  for (const row of accepted) {
    row.agreement_kappa = kappa
    row.agreement_rate = agreementRate
  }

  return {
    accepted,
    kappa,
    agreementRate,
    questionsFilled,
    judged: judgeA.length,
    bothAgree,
    bothReject,
    disagreements,
    needJudgment,
  }
}
