import { describe, expect, it } from 'vitest'

import { ktibRowsFromCsv, parseCsv } from './csv'

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
