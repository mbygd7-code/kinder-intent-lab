/**
 * @vitest-environment jsdom
 *
 * T3.6 AC: §7-2·§7-3 목업과 필드 1:1 + 정보 정직성(Arena 미실행 → "—", mock은 명시 라벨).
 */
import { cleanup, fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type { ObservatoryBrain, ObservatoryNode } from '../api/observatory'
import { REGIONS } from '../brain3d/regions'
import { useBrainStore } from '../brain3d/store'
import { NodePanel } from './NodePanel'
import { RegionsPanel } from './RegionsPanel'

function node(over: Partial<ObservatoryNode>): ObservatoryNode {
  return {
    node_id: 'N_x', intent_id: 'x', region: 'PLAY', evidence_total: 0, evidence_diversity: 0,
    gold_count: 0, exemplar_count: 0, heldout_accuracy: null, pending_evaluation: false, ...over,
  }
}

const BRAIN: ObservatoryBrain = {
  brain_version: 'seed-v0',
  ontology_version: 'onto-1.0',
  ktib_global: null,
  regions: REGIONS.map((r) => ({
    region: r.id, reliability: null, node_count: 2,
    gold_evidence: r.id === 'PLAY' ? 231 : 0, synthetic_evidence: r.id === 'PLAY' ? 8402 : 0,
  })),
  nodes: [
    node({ node_id: 'N_play_a', intent_id: 'play_a', region: 'PLAY', evidence_total: 30, gold_count: 12 }),
    node({ node_id: 'N_play_b', intent_id: 'play_b', region: 'PLAY', evidence_total: 5, gold_count: 1 }),
    node({ node_id: 'N_vis_a', intent_id: 'vis_a', region: 'VISUAL', evidence_total: 9, gold_count: 0 }),
  ],
}

// 노드 4축 진단(§7-3) 응답 스텁 — 기본은 데이터 없음(모두 null). 개별 테스트가 덮어쓸 수 있다.
function stubDiagnosis(diag?: Partial<Record<string, { value: number | null; level: string | null }>>) {
  const nul = { value: null, level: null }
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true,
    json: async () => ({
      intent_id: 'play_a',
      ambiguous_language: diag?.ambiguous_language ?? nul,
      screen_context_coverage: diag?.screen_context_coverage ?? nul,
      persona_diversity: diag?.persona_diversity ?? nul,
      gold_data: diag?.gold_data ?? nul,
    }),
  }) as Response))
}

beforeEach(() => {
  useBrainStore.setState({ brain: BRAIN, ktibGlobal: null, selectedRegionId: null, selectedNodeId: null })
  stubDiagnosis() // NodePanel의 진단 fetch가 기본적으로 안전하게 해석되게
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('RegionsPanel (§7-2)', () => {
  it('KTIB 미실행이면 "—", 7개 region 리스트를 렌더한다', () => {
    render(<RegionsPanel />)
    expect(screen.getByText('OVERALL BRAIN SCORE')).toBeTruthy()
    for (const r of REGIONS) expect(screen.getByText(r.label)).toBeTruthy()
    // 모든 region reliability null → 점수 자리 "—" (지어내지 않음)
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(7)
  })

  it('region 선택 시 §7-2 상세: Gold/Synthetic 실데이터 분리 표기, Reliability/Coverage "—"', () => {
    render(<RegionsPanel />)
    fireEvent.click(screen.getByText('Play'))
    const detail = screen.getByText('PLAY REGION').closest('.region-detail') as HTMLElement
    const d = within(detail)
    expect(d.getByText('Gold Episodes').nextSibling?.textContent).toBe('231')
    expect(d.getByText('Synthetic Episodes').nextSibling?.textContent).toBe('8,402')
    expect(d.getByText('Region Reliability').nextSibling?.textContent).toBe('—') // Arena 전
    expect(d.getByText('Coverage').nextSibling?.textContent).toBe('—')
    // Top Weak Nodes: 훈련량 낮은 순 → play_b(5) 먼저, 점수는 "—"
    const weakRows = detail.querySelectorAll('.weak-row')
    expect(weakRows[0].querySelector('.weak-name')?.textContent).toBe('play_b')
    // 정직성: heldout 없으므로 각 weak 노드 점수는 "—"(지어낸 % 아님)
    for (const row of weakRows) {
      expect(row.querySelector('.weak-score')?.textContent).toBe('—')
    }
  })
})

describe('NodePanel (§7-3)', () => {
  it('노드 미선택이면 아무것도 안 그린다', () => {
    const { container } = render(<NodePanel />)
    expect(container.querySelector('.side-panel-right')).toBeNull()
  })

  it('선택 노드: 실 KEY METRICS + 혼동(mock 라벨) + 실계산 4축(데이터 없으면 "—")', () => {
    useBrainStore.setState({ selectedNodeId: 'N_play_a' }) // stubDiagnosis 기본=모두 null
    const { container } = render(<NodePanel />)
    expect(screen.getByText('play_a')).toBeTruthy()
    // 방향성 혼동은 mock(§5-6 미적재) — 라벨 필수, 후보가 있으면 행 렌더(vacuous 방지)
    expect(container.querySelectorAll('.confusion-row').length).toBeGreaterThanOrEqual(1)
    expect(screen.getByText('미리보기 · mock')).toBeTruthy()
    // 실 지표 4종 (KEY METRICS 전부 실데이터)
    expect(screen.getByText('Evidence Total').previousSibling?.textContent).toBe('30')
    expect(screen.getByText('Gold').previousSibling?.textContent).toBe('12')
    expect(screen.getByText('Diversity').previousSibling?.textContent).toBe('0%')
    expect(screen.getByText('Exemplars').previousSibling?.textContent).toBe('0')
    // WHY-WEAK는 §7-3 실계산 배지 (mock 아님)
    expect(screen.getByText('§7-3 실계산')).toBeTruthy()
    // 진단 데이터 없음 → 4축 모두 "—"(지어내지 않음)
    for (const ax of ['Ambiguous Language', 'Screen Context Coverage', 'Persona Diversity', 'Gold Data']) {
      const row = screen.getByText(ax).closest('.axis-row') as HTMLElement
      expect(within(row).getByText('—')).toBeTruthy()
    }
  })

  it('노드 전환 시 재fetch — 이전 노드의 레벨이 잔류하지 않는다 (정직성 게이트)', async () => {
    // URL의 intent에 따라 다른 레벨 반환: play_a→HIGH, 그 외→LOW
    vi.stubGlobal('fetch', vi.fn(async (url: string) => {
      const isA = url.includes('play_a')
      const lvl = isA ? { value: 20, level: 'HIGH' } : { value: 0, level: 'LOW' }
      return { ok: true, json: async () => ({
        intent_id: isA ? 'play_a' : 'play_b',
        ambiguous_language: { value: null, level: null },
        screen_context_coverage: { value: null, level: null },
        persona_diversity: { value: null, level: null },
        gold_data: lvl,
      }) } as Response
    }))
    useBrainStore.setState({ selectedNodeId: 'N_play_a' })
    render(<NodePanel />)
    await waitFor(() => {
      const g = screen.getByText('Gold Data').closest('.axis-row') as HTMLElement
      expect(within(g).getByText('HIGH')).toBeTruthy()
    })
    // play_b로 전환 → 잔류 HIGH가 아니라 LOW로 바뀐다
    useBrainStore.setState({ selectedNodeId: 'N_play_b' })
    await waitFor(() => {
      const g = screen.getByText('Gold Data').closest('.axis-row') as HTMLElement
      expect(within(g).getByText('LOW')).toBeTruthy()
      expect(within(g).queryByText('HIGH')).toBeNull()
    })
  })

  it('실계산 4축이 응답 레벨을 그대로 표시한다 (Gold Data=HIGH 등)', async () => {
    stubDiagnosis({
      ambiguous_language: { value: 3.2, level: 'HIGH' },
      screen_context_coverage: { value: 0.2, level: 'LOW' },
      persona_diversity: { value: 0.1, level: 'LOW' },
      gold_data: { value: 20, level: 'HIGH' },
    })
    useBrainStore.setState({ selectedNodeId: 'N_play_a' })
    render(<NodePanel />)
    await waitFor(() => {
      const gold = screen.getByText('Gold Data').closest('.axis-row') as HTMLElement
      expect(within(gold).getByText('HIGH')).toBeTruthy()
    })
    const cov = screen.getByText('Screen Context Coverage').closest('.axis-row') as HTMLElement
    expect(within(cov).getByText('LOW')).toBeTruthy()
  })

  it('강화하기 클릭 → 헷갈리는 짝 + §8-1 Gym 3모드(한글) 버튼 노출', () => {
    useBrainStore.setState({ selectedNodeId: 'N_play_a' })
    render(<NodePanel />)
    fireEvent.click(screen.getByText('🚀 강화하기'))
    expect(screen.getByText('헷갈리는 짝')).toBeTruthy()
    expect(screen.getByText('훈련 방식을 골라 주세요')).toBeTruthy()
    for (const label of ['의도 알아맞히기', '알맞은 의미 고르기', '바로잡기 연습']) {
      expect(screen.getByRole('button', { name: label })).toBeTruthy()
    }
  })

  it('모드 클릭 → openGymSession이 intent_id(node_id 아님)로 origin 전송 + 오버레이 마운트', async () => {
    // Phase 3 게이트 시임: node→패널→강화하기→openGymSession 배선 고정 (리뷰 MINOR)
    // 마운트 시 진단 GET(body 없음)도 함께 나가므로 gym POST만 골라 검증한다
    const sent: Array<{ url: string; body: Record<string, unknown> | null }> = []
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      sent.push({ url, body: init?.body ? JSON.parse(init.body as string) : null })
      return { ok: true, json: async () => ({
        session_id: 'GS_x', pack_id: 'CP_x', mode: 'guess_my_intent',
        items: [{ item_id: 'GI_0', utterance: '발화', candidate_intents: ['play_a'], brain_guess: null }],
        // 진단 GET 응답으로도 무해(axis 없으면 "—")
      }) } as Response
    }))
    useBrainStore.setState({ selectedNodeId: 'N_play_a' })
    render(<NodePanel />)
    fireEvent.click(screen.getByText('🚀 강화하기'))
    fireEvent.click(screen.getByRole('button', { name: '의도 알아맞히기' }))
    await waitFor(() => expect(screen.getByRole('dialog', { name: '훈련 세션' })).toBeTruthy())
    const gym = sent.find((s) => s.url === '/v1/gym/session')
    expect(gym).toBeTruthy()
    expect((gym!.body!.origin as { node: string }).node).toBe('play_a') // node_id였다면 백엔드 422
  })

  it('mock 진단은 결정론 — 같은 노드 재렌더에 혼동 목록이 동일', () => {
    useBrainStore.setState({ selectedNodeId: 'N_play_a' })
    const first = render(<NodePanel />)
    const a = [...first.container.querySelectorAll('.confusion-name')].map((e) => e.textContent)
    cleanup()
    render(<NodePanel />)
    const b = [...document.querySelectorAll('.confusion-name')].map((e) => e.textContent)
    expect(a).toEqual(b)
  })
})
