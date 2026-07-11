/**
 * 최소 CSV 파서 + 시험지 행 변환 — 구글 시트/엑셀에서 받은 CSV를 업로드 행으로.
 *
 * 따옴표 필드(쉼표·줄바꿈 포함) 처리, BOM 제거. 열은 헤더 키워드로 유연 매칭한다
 * (전문가가 열 순서를 바꾸거나 이름을 조금 바꿔도 동작).
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
