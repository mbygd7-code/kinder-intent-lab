/**
 * 의도 카탈로그 동기화 — 서버(/v1/ontology/intents)가 의도 id 목록·한글 이름의 원천.
 *
 * 왜: 의도 목록에서 고친 이름(intent_display 오버레이)과 운영 경로로 늘어난 의도가
 * **어느 화면을 먼저 열든** 검수·즉석 문답·훈련에 똑같이 보여야 한다(2026-07-18 연결
 * 점검). 정적 INTENT_LABEL_KO는 서버 미연결 시의 폴백일 뿐 — 씨드 어휘(검수 상황
 * 라벨)와 같은 패턴. 실패 시 마지막 성공 상태(오버레이)를 지우지 않는다.
 */
import { useEffect, useState } from 'react'

import { fetchIntentCatalog } from '../api/ontologyAdmin'
import { INTENT_LABEL_KO, setIntentLabelOverrides } from './intentLabels'

/** 서버 카탈로그 → 전역 라벨 오버레이 반영 + 의도 id 목록 반환. 실패는 null(폴백 유지). */
export async function syncIntentCatalog(signal?: AbortSignal): Promise<string[] | null> {
  try {
    const catalog = await fetchIntentCatalog(signal)
    const overrides: Record<string, string> = {}
    for (const item of catalog.items) if (item.name_ko) overrides[item.intent_id] = item.name_ko
    setIntentLabelOverrides(overrides)
    return catalog.items.map((i) => i.intent_id)
  } catch {
    return null
  }
}

/** 마운트 시 동기화 — 서버 의도 id 목록(도착 전·실패 시 정적 사전 키). 도착 리렌더가 라벨도 갱신 */
export function useIntentCatalog(): string[] {
  const [ids, setIds] = useState<string[]>(() => Object.keys(INTENT_LABEL_KO))
  useEffect(() => {
    const ctrl = new AbortController()
    void syncIntentCatalog(ctrl.signal).then((got) => {
      if (got && got.length) setIds(got)
    })
    return () => ctrl.abort()
  }, [])
  return ids
}
