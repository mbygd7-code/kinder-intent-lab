/**
 * 의도 추천(글자 유사도) AC — blind 유지: 정적 예문 사전만 쓰고, 전체 의도를 랭킹한다.
 */
import { describe, expect, it } from 'vitest'

import { INTENT_LABEL_KO } from './intentLabels'
import { bigrams, buildCorpus, rankIntents } from './intentRecommend'

const ROWS: string[][] = [
  ['의도 id', '의도', '뜻', '구분', '예시', 'X'],
  ['visual_naturalize', '사진 자연스럽게 보정', '', '기존1', '역광이라 얼굴이 어두운데 살려줘', ''],
  ['op_notice_send', '알림 보내기', '', '기존1', '알림장 지금 바로 보내줘요', ''],
  ['NOT_REAL_INTENT', '유령', '', '기존1', '이 행은 무시돼야 한다', ''],
]

describe('intentRecommend', () => {
  it('bigrams: 공백·문장부호를 걷어낸 2-gram', () => {
    expect(bigrams('사진 좀!')).toEqual(new Set(['사진', '진좀']))
  })

  it('buildCorpus: 온톨로지에 없는 의도 행은 버린다', () => {
    const corpus = buildCorpus(ROWS)
    expect(corpus.has('visual_naturalize')).toBe(true)
    expect(corpus.has('NOT_REAL_INTENT')).toBe(false)
  })

  it('buildCorpus: 서버 카탈로그 id를 주면 그 목록이 기준 — 새 의도 행도 산다', () => {
    // 운영 경로로 온톨로지에 추가된 의도(comm_new_thing)는 정적 라벨 사전에 없어도
    // 서버 id 목록이 원천이므로 예문이 버려지면 안 된다(2026-07-18 연결 점검).
    const rows = [...ROWS, ['comm_new_thing', '새 소통', '', '기존1', '새로 생긴 의도 예문', '']]
    const corpus = buildCorpus(rows, ['visual_naturalize', 'comm_new_thing'])
    expect(corpus.has('comm_new_thing')).toBe(true)
    expect(corpus.has('op_notice_send')).toBe(false) // 준 목록 밖은 버린다
  })

  it('rankIntents: 서버 id 목록을 주면 그 우주 전체를 랭킹한다(정적 사전 밖 포함)', () => {
    const ids = ['comm_new_thing', 'visual_naturalize', 'op_notice_send']
    const rows = [...ROWS, ['comm_new_thing', '새 소통', '', '기존1', '새로 생긴 의도 예문', '']]
    const ranked = rankIntents('새로 생긴 의도 예문이랑 겹치는 말', buildCorpus(rows, ids), ids)
    expect(ranked[0]).toBe('comm_new_thing')
    expect(new Set(ranked)).toEqual(new Set(ids))
  })

  it('발화와 예문이 겹치는 의도가 1순위 — 전체 의도가 랭킹에 포함(더보기로 끝까지 도달)', () => {
    const corpus = buildCorpus(ROWS)
    const ranked = rankIntents('역광이라 얼굴이 어두운데 살려줄래?', corpus)
    expect(ranked[0]).toBe('visual_naturalize')
    expect(ranked.length).toBe(Object.keys(INTENT_LABEL_KO).length)
    // 결정론 — 같은 입력이면 같은 순서 (두 검수자가 같은 조건을 본다)
    expect(rankIntents('역광이라 얼굴이 어두운데 살려줄래?', corpus)).toEqual(ranked)
  })

  it('겹침이 전혀 없어도 랭킹은 전체를 돌려준다(추천 실패 ≠ 기능 실패)', () => {
    const ranked = rankIntents('ㅁㄴㅇㄹ', buildCorpus(ROWS))
    expect(ranked.length).toBe(Object.keys(INTENT_LABEL_KO).length)
  })
})
