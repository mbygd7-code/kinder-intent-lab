/**
 * 의도 추천(검수 보조) — 발화 ↔ 정적 예문 사전의 글자 유사도 랭킹.
 *
 * blind 원칙 유지가 핵심이다: 이 추천은 **뇌의 추론·집계 제안·다른 검수자의 표가 아니라**,
 * 공개 예문 사전(ontology_examples_draft.csv — 의도별 사람 저작 예시 문장)과의
 * 문자 2-gram 겹침만으로 만든다. 결정론적이고 정답을 아는 주체가 없다 — "검색어를
 * 대신 쳐 주는 것" 이상도 이하도 아니다. 랭킹은 전체 의도를 포함하므로(더보기 페이징)
 * 추천이 틀려도 모든 의도에 도달할 수 있다.
 */
import { INTENT_LABEL_KO, labelOf } from './intentLabels'

/** 의도별 매칭 코퍼스: label + 설명 + 예시 문장들을 이어 붙인 텍스트 */
export type IntentCorpus = Map<string, string>

/** 공백·문장부호를 걷어낸 문자 2-gram 집합 (한국어 어미 변화에 견디는 최소 단위) */
export function bigrams(text: string): Set<string> {
  const s = text.replace(/[\s"'’‘“”.,!?~()\-—·]/g, '')
  const out = new Set<string>()
  for (let i = 0; i < s.length - 1; i += 1) out.add(s.slice(i, i + 2))
  return out
}

/** CSV(의도 id, 의도, 뜻, 구분, 예시 문장, …) → 의도별 코퍼스. parseCsv 산출 행을 받는다. */
export function buildCorpus(rows: string[][]): IntentCorpus {
  const corpus: IntentCorpus = new Map()
  for (const row of rows.slice(1)) {
    const id = (row[0] ?? '').replace(/^﻿/, '').trim()
    if (!id || !(id in INTENT_LABEL_KO)) continue
    const parts = [row[1] ?? '', row[2] ?? '', row[4] ?? ''].join(' ')
    corpus.set(id, `${corpus.get(id) ?? labelOf(id)} ${parts}`)
  }
  return corpus
}

/**
 * 발화와의 2-gram 겹침 순으로 **전체 의도**를 랭킹한다(코퍼스에 없는 의도는 라벨만으로
 * 점수 후 후미 배치). 동점은 intent_id 사전순 — 결정론(두 검수자가 같은 순서를 본다는
 * 사실 자체는 검색과 동일 조건이며, 순서에 정답 신호가 없다는 것이 불변식이다).
 */
export function rankIntents(utterance: string, corpus: IntentCorpus): string[] {
  const u = bigrams(utterance)
  const score = (id: string): number => {
    const text = corpus.get(id) ?? labelOf(id)
    let hit = 0
    for (const g of bigrams(text)) if (u.has(g)) hit += 1
    return hit
  }
  return Object.keys(INTENT_LABEL_KO)
    .map((id) => [id, score(id)] as const)
    .sort((a, b) => b[1] - a[1] || (a[0] < b[0] ? -1 : 1))
    .map(([id]) => id)
}

/** public/ontology_examples_draft.csv 로드 — 실패하면 null(추천 없이 검색만, 기능 저하 없음) */
export async function loadIntentCorpus(
  parse: (text: string) => string[][],
  signal?: AbortSignal,
): Promise<IntentCorpus | null> {
  try {
    const res = await fetch('/ontology_examples_draft.csv', { signal })
    if (!res.ok) return null
    return buildCorpus(parse(await res.text()))
  } catch {
    return null
  }
}
