/**
 * @vitest-environment jsdom
 *
 * T3.6 AC: §7-2·§7-3 목업과 필드 1:1 + 정보 정직성(Arena 미실행 → "—", mock은 명시 라벨).
 */
import { cleanup, fireEvent, render, screen, within } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

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

beforeEach(() => {
  useBrainStore.setState({ brain: BRAIN, ktibGlobal: null, selectedRegionId: null, selectedNodeId: null })
})
afterEach(cleanup)

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

  it('선택 노드: 실 KEY METRICS + mock 혼동/WHY-WEAK(라벨 필수) + Gold Data는 실데이터', () => {
    useBrainStore.setState({ selectedNodeId: 'N_play_a' })
    const { container } = render(<NodePanel />)
    expect(screen.getByText('play_a')).toBeTruthy()
    // §7-3 방향성 혼동: 후보(play_b, vis_a)가 있으니 실제로 행이 렌더된다(빈 목록 vacuous 방지)
    expect(container.querySelectorAll('.confusion-row').length).toBeGreaterThanOrEqual(1)
    expect(container.querySelectorAll('.confusion-row').length).toBeLessThanOrEqual(3)
    expect(screen.queryByText('혼동 관계 데이터 없음 (측정 전)')).toBeNull()
    // 실 지표 4종 (KEY METRICS 전부 실데이터)
    expect(screen.getByText('Evidence Total').previousSibling?.textContent).toBe('30')
    expect(screen.getByText('Gold').previousSibling?.textContent).toBe('12')
    expect(screen.getByText('Diversity').previousSibling?.textContent).toBe('0%')
    expect(screen.getByText('Exemplars').previousSibling?.textContent).toBe('0')
    // §7-3 4축 라벨 존재
    for (const ax of ['Ambiguous Language', 'Screen Context Coverage', 'Persona Diversity', 'Gold Data']) {
      expect(screen.getByText(ax)).toBeTruthy()
    }
    // mock 섹션은 반드시 "mock" 라벨을 단다 (실측 오인 방지)
    expect(screen.getAllByText(/mock/i).length).toBeGreaterThanOrEqual(2)
    // Gold Data는 실 gold_count(12)→HIGH (mock 아님)
    const goldAxis = screen.getByText('Gold Data').closest('.axis-row') as HTMLElement
    expect(within(goldAxis).getByText('HIGH')).toBeTruthy()
  })

  it('강화하기 클릭 → §7-4 브리핑 미리보기(라벨) 노출', () => {
    useBrainStore.setState({ selectedNodeId: 'N_play_a' })
    render(<NodePanel />)
    fireEvent.click(screen.getByText('🚀 강화하기'))
    expect(screen.getByText('Target Confusion')).toBeTruthy()
    expect(screen.getByText(/T3.7 Gym/)).toBeTruthy()
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
