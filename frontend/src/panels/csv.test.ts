import { describe, expect, it } from 'vitest'

import {
  canonicalName,
  cohensKappa,
  examSheetToRows,
  ktibRowsFromCsv,
  parseCsv,
  readMark,
} from './csv'

describe('parseCsv', () => {
  it('BOM 제거 + 따옴표 필드(쉼표·따옴표 포함) 처리', () => {
    const csv = '﻿a,b\n"x,y","he said ""hi"""\n'
    expect(parseCsv(csv)).toEqual([
      ['a', 'b'],
      ['x,y', 'he said "hi"'],
    ])
  })

  it('완전 공백 행은 버린다', () => {
    expect(parseCsv('a,b\n\n , \nc,d')).toEqual([
      ['a', 'b'],
      ['c', 'd'],
    ])
  })
})

describe('ktibRowsFromCsv', () => {
  const header = '의도 id,의도(참고),시험 발화(교사 말),검수자1,검수자2,일치도(0~1)'

  it('헤더 키워드로 열을 찾아 행을 변환한다', () => {
    const csv = `${header}\nop_workspace_search,자료 검색,"작년 봄 소풍 사진 어디 있지?",김검수,이검수,0.9`
    const rows = ktibRowsFromCsv(csv)
    expect(rows).toEqual([
      {
        intent: 'op_workspace_search',
        teacher_prompt: '작년 봄 소풍 사진 어디 있지?',
        reviewers: ['김검수', '이검수'],
        agreement_kappa: 0.9,
      },
    ])
  })

  it('빈 발화 행은 건너뛰고, kappa 미기입은 null', () => {
    const csv = `${header}\ndoc_proofread,교정,맞춤법 봐줘,김,이,\n,,,,,\n`
    const rows = ktibRowsFromCsv(csv)
    expect(rows).toHaveLength(1)
    expect(rows[0].agreement_kappa).toBeNull()
  })

  it('필수 열이 없으면 친절한 오류', () => {
    expect(() => ktibRowsFromCsv('이름,값\n김,1')).toThrow(/의도 id.*시험 발화|시험 발화/)
  })
})

describe('readMark (O/X 관대 파싱)', () => {
  it('O 계열은 O, X 계열은 X, 그 외/빈칸은 미판정', () => {
    for (const s of ['O', 'o', '○', 'ㅇ', '✓', 'Y', '예', '맞음', '1']) expect(readMark(s)).toBe('O')
    for (const s of ['X', 'x', '✗', 'ㄴ', 'N', '아니오', '틀림', '0']) expect(readMark(s)).toBe('X')
    for (const s of ['', '  ', '??', '몰라']) expect(readMark(s)).toBe('')
  })
})

describe('canonicalName (검수자 동일인 판별)', () => {
  it('공백·대소문자 차이는 같은 사람', () => {
    expect(canonicalName('  Kim ')).toBe(canonicalName('kim'))
    expect(canonicalName('김검수')).toBe('김검수')
  })
})

describe('cohensKappa', () => {
  it('완전 일치이되 변별 있음 → 1.0', () => {
    expect(cohensKappa(['O', 'O', 'X', 'X'], ['O', 'O', 'X', 'X'])).toBe(1)
  })
  it('판정이 전부 동일(변별 0) → null (완전일치를 1.0으로 안 침)', () => {
    expect(cohensKappa(['O', 'O', 'O'], ['O', 'O', 'O'])).toBeNull()
  })
  it('길이 불일치·빈 배열 → null', () => {
    expect(cohensKappa(['O'], ['O', 'X'])).toBeNull()
    expect(cohensKappa([], [])).toBeNull()
  })
  it('부분 일치는 0~1 사이', () => {
    const k = cohensKappa(['O', 'O', 'X', 'X', 'O'], ['O', 'X', 'X', 'X', 'O'])
    expect(k).not.toBeNull()
    expect(k! > 0 && k! < 1).toBe(true)
  })
})

describe('examSheetToRows (O/X 시트 → kappa 자동)', () => {
  const H = '의도 id,의도(그대로),번호,시험 질문,검수자A 판정(O/X),검수자B 판정(O/X)'
  // 4개 문항: (O,O)(O,O)(X,X)(O,X) — 둘 다 O 2개, 갈림 1개, 둘다X 1개
  const sheet = [
    H,
    'play_expand,놀이 더 키우기,1,블록 더 재밌게,O,O',
    'obs_record_moment,순간 관찰,1,이거 기록해줘,O,O',
    'doc_proofread,맞춤법 교정,1,맞춤법 봐줘,X,X',
    'op_workspace_search,자료 검색,1,자료 어디 있지,O,X',
    'refl_activity_review,활동 돌아보기,1,,,', // 질문 빈칸 → 무시
  ].join('\n')

  it('둘 다 O인 문항만 채택하고, 검수자 이름·자동 kappa를 부착한다', () => {
    const r = examSheetToRows(sheet, '김유아', '이교사')
    expect(r.questionsFilled).toBe(4)
    expect(r.bothAgree).toBe(2)
    expect(r.disagreements).toBe(1)
    expect(r.bothReject).toBe(1)
    expect(r.accepted).toHaveLength(2)
    expect(r.accepted[0].reviewers).toEqual(['김유아', '이교사'])
    // kappa는 판정 4건(OO/OO/XX/OX)으로 계산 — 변별 있으니 null 아님, 모든 채택행에 같은 값
    expect(r.kappa).not.toBeNull()
    expect(r.accepted.every((e) => e.agreement_kappa === r.kappa)).toBe(true)
    expect(r.accepted[0].intent).toBe('play_expand')
    // 관측 일치율 = (둘 다 O 2 + 둘 다 X 1) / judged 4 = 0.75, 채택행에도 부착
    expect(r.agreementRate).toBe(0.75)
    expect(r.accepted.every((e) => e.agreement_rate === 0.75)).toBe(true)
  })

  it('판정이 O로 쏠리면 kappa는 퇴화해도 일치율은 실제 일치를 반영한다 (§3-3 v1.6)', () => {
    // 10문항 중 9개 (O,O), 1개 (O,X) — 관측 일치 90%인데 쏠림이라 kappa는 낮거나 음수
    const lines = [H]
    for (let i = 0; i < 9; i++) lines.push(`play_expand,놀이,${i + 1},질문${i + 1},O,O`)
    lines.push('obs_record_moment,관찰,10,질문10,O,X')
    const r = examSheetToRows(lines.join('\n'), '김유아', '이교사')
    expect(r.judged).toBe(10)
    expect(r.agreementRate).toBeCloseTo(0.9, 5) // (9 + 0) / 10
    // kappa는 base-rate 역설로 실제 일치(90%)보다 훨씬 낮다 — 일치율이 진짜 신호다
    expect(r.kappa === null || r.kappa! < r.agreementRate!).toBe(true)
  })

  it('한쪽만 판정한 문항은 kappa 표본·채택에서 빠지고 needJudgment로 센다', () => {
    const s = [H, 'play_expand,놀이,1,질문1,O,', 'obs_record_moment,관찰,1,질문2,O,O',
      'doc_proofread,교정,1,질문3,X,X'].join('\n')
    const r = examSheetToRows(s, 'A', 'B')
    expect(r.needJudgment).toBe(1)     // 질문1: B 미판정
    expect(r.judged).toBe(2)           // 질문2·3만 kappa 표본
    expect(r.bothAgree).toBe(1)
  })

  it('판정 O/X 열이 없으면 친절한 오류(쉬운 양식 안내)', () => {
    expect(() => examSheetToRows('의도 id,시험 질문\nplay_expand,질문', 'A', 'B')).toThrow(/검수자 판정/)
  })
})
