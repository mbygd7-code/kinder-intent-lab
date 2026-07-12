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
  brain_stage: 0,
  brain_stage_name: 'Dormant',
  regions: REGIONS.map((r) => ({
    region: r.id, reliability: null, node_count: 2,
    gold_evidence: r.id === 'PLAY' ? 231 : 0, synthetic_evidence: r.id === 'PLAY' ? 8402 : 0,
    stage: 0, stage_name: 'Dormant', measured_count: 0,
  })),
  nodes: [
    node({ node_id: 'N_play_a', intent_id: 'play_a', region: 'PLAY', evidence_total: 30, gold_count: 12 }),
    node({ node_id: 'N_play_b', intent_id: 'play_b', region: 'PLAY', evidence_total: 5, gold_count: 1 }),
    node({ node_id: 'N_vis_a', intent_id: 'vis_a', region: 'VISUAL', evidence_total: 9, gold_count: 0 }),
  ],
}

// §5-6 혼동쌍 응답 스텁 — 기본은 가설 1건(측정 전). 개별 테스트가 confusions로 덮어쓸 수 있다.
const DEFAULT_CONFUSIONS = {
  intent_id: 'play_a',
  measured: false,
  edges: [{ to_predicted: 'play_b', confusion_rate: null, state: 'hypothesized', origin: 'SKEPTIC' }],
}

// 노드 4축 진단(§7-3) + 혼동쌍(§5-6) 응답 스텁 — URL로 분기. 기본은 데이터 없음/가설.
function stubDiagnosis(
  diag?: Partial<Record<string, { value: number | null; level: string | null }>>,
  confusions: unknown = DEFAULT_CONFUSIONS,
) {
  const nul = { value: null, level: null }
  vi.stubGlobal('fetch', vi.fn(async (url: string) => {
    if (url.includes('/confusions')) {
      return { ok: true, json: async () => confusions } as Response
    }
    return {
      ok: true,
      json: async () => ({
        intent_id: 'play_a',
        ambiguous_language: diag?.ambiguous_language ?? nul,
        screen_context_coverage: diag?.screen_context_coverage ?? nul,
        persona_diversity: diag?.persona_diversity ?? nul,
        gold_data: diag?.gold_data ?? nul,
      }),
    } as Response
  }))
}

// T4.3 §7-4 브리핑용 실 pack 응답(POST /v1/gym/pack, T4.2 계약) — persona_mix는 의도적 부재
const PACK_RESP = {
  pack: {
    pack_id: 'CP_t1',
    origin: {
      trigger: 'observatory_click', node: 'play_a', region: 'PLAY',
      diagnosis: ['CONFUSION_HIGH', 'GOLD_LOW'],
    },
    strategy: ['C_CONFUSION', 'B_HUMAN_EVIDENCE'],
    target_edges: [{ from_true: 'play_a', to_predicted: 'play_b' }],
    items: 20,
    difficulty_curve: 'medium_to_hard',
    delivery_modes: ['guess_my_intent', 'choose_right_meaning', 'correction_drill'],
  },
  diagnosis_codes: ['CONFUSION_HIGH', 'GOLD_LOW'],
  strategy: ['C_CONFUSION', 'B_HUMAN_EVIDENCE'],
  needs_human: true,
  node_priority: 3.2,
  work_orders: [{ order_id: 'WO_1', order_type: 'GENERATION', status: 'REQUESTED', requested_items: 20 }],
}

// T4.3 클릭-투-트레인 전 구간 스텁 — url/메서드로 분기(진단 GET + pack/session/submit POST)
function stubGymFlow() {
  const sent: Array<{ url: string; method: string; body: Record<string, unknown> | null }> = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    sent.push({
      url,
      method: init?.method ?? 'GET',
      body: init?.body ? (JSON.parse(init.body as string) as Record<string, unknown>) : null,
    })
    if (url === '/v1/gym/pack') return { ok: true, json: async () => PACK_RESP } as Response
    if (url === '/v1/gym/session') {
      return { ok: true, json: async () => ({
        session_id: 'GS_x', pack_id: 'CP_t1', mode: 'guess_my_intent',
        items: [{ item_id: 'GI_0', utterance: '발화', candidate_intents: ['play_a'], brain_guess: null }],
      }) } as Response
    }
    // 제출은 정확한 URL만 성공 — endsWith 매칭이면 잘못된 경로 회귀가 조용히 통과한다(리뷰)
    if (url === '/v1/gym/session/GS_x/submit') {
      return { ok: true, json: async () => ({
        session_id: 'GS_x', episodes_created: 1, evidence_created: 2, by_type: { TEACHER_LABEL: 2 },
        node_intent: 'play_a', episodes_aggregated: 1, label_states: { LABELED: 1 }, pending_set: true,
      }) } as Response
    }
    // 미지의 POST는 시끄럽게 실패 — 엔드포인트 회귀가 ok:true 캐치올 뒤로 숨지 못하게
    if ((init?.method ?? 'GET') !== 'GET') {
      return { ok: false, status: 404, json: async () => ({}) } as Response
    }
    // §5-6 혼동쌍 GET — 가설 1건(측정 전)
    if (url.includes('/confusions')) {
      return { ok: true, json: async () => DEFAULT_CONFUSIONS } as Response
    }
    // 그 외 GET = 노드 4축 진단(§7-3) — 데이터 없음(모두 null)
    const nul = { value: null, level: null }
    return { ok: true, json: async () => ({
      intent_id: 'play_a', ambiguous_language: nul, screen_context_coverage: nul,
      persona_diversity: nul, gold_data: nul,
    }) } as Response
  }))
  return sent
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
    expect(screen.getByText('브레인 종합 점수')).toBeTruthy()
    for (const r of REGIONS) expect(screen.getByText(r.label)).toBeTruthy()
    // 모든 region reliability null → 점수 자리 "—" (지어내지 않음)
    expect(screen.getAllByText('—').length).toBeGreaterThanOrEqual(7)
    // T5.4(§7-6): 미측정 뇌는 실패가 아니라 Dormant — 전체 배지 1 + region row 7
    expect(screen.getAllByText('잠자는 중').length).toBeGreaterThanOrEqual(8)
  })

  it('region 선택 시 §7-2 상세: Gold/Synthetic 실데이터 분리 표기, Reliability/Coverage "—"', () => {
    render(<RegionsPanel />)
    // 영역 제목은 영문(2026-07-12 재정비) — 행 클릭도, 상세 카드 표제도 EN + 한글 병기
    fireEvent.click(screen.getByText('PLAY'))
    const detail = screen.getByText('PLAY · 놀이 영역').closest('.region-detail') as HTMLElement
    const d = within(detail)
    expect(d.getByText('사람이 확인한 데이터').nextSibling?.textContent).toBe('231')
    expect(d.getByText('AI가 만든 연습 데이터').nextSibling?.textContent).toBe('8,402')
    expect(d.getByText('영역 정답률').nextSibling?.textContent).toBe('—') // Arena 전
    expect(d.getByText('상황 경험 폭').nextSibling?.textContent).toBe('—')
    // T5.4(§7-6): 성장 스테이지 + 측정 노드 수 — Arena 산출값 그대로
    expect(d.getByText('성장 단계').nextSibling?.textContent).toBe('0단계 · 잠자는 중')
    expect(d.getByText('시험 본 의도').nextSibling?.textContent).toBe('0 / 2개')
    // Top Weak Nodes: 훈련량 낮은 순 → play_b(5) 먼저, 점수는 "—"
    const weakRows = detail.querySelectorAll('.weak-row')
    expect(weakRows[0].querySelector('.weak-name')?.textContent).toBe('play b')
    // 정직성: heldout 없으므로 각 weak 노드 점수는 "—"(지어낸 % 아님)
    for (const row of weakRows) {
      expect(row.querySelector('.weak-score')?.textContent).toBe('—')
    }
  })

  it('T5.4(§7-6): 측정된 region은 stage_name이 API 값 그대로 흐른다 (Spark 등)', () => {
    useBrainStore.setState({
      brain: {
        ...BRAIN,
        regions: BRAIN.regions.map((r) =>
          r.region === 'PLAY'
            ? { ...r, reliability: 0.42, stage: 1 as const, stage_name: 'Spark', measured_count: 1 }
            : r,
        ),
      },
    })
    render(<RegionsPanel />)
    expect(screen.getByText('첫 불꽃')).toBeTruthy() // PLAY row — 나머지는 여전히 Dormant
    fireEvent.click(screen.getByText('PLAY'))
    const detail = screen.getByText('PLAY · 놀이 영역').closest('.region-detail') as HTMLElement
    const d = within(detail)
    expect(d.getByText('성장 단계').nextSibling?.textContent).toBe('1단계 · 첫 불꽃')
    expect(d.getByText('시험 본 의도').nextSibling?.textContent).toBe('1 / 2개')
    expect(d.getByText('영역 정답률').nextSibling?.textContent).toBe('42%')
  })
})

describe('NodePanel (§7-3)', () => {
  it('노드 미선택이면 아무것도 안 그린다', () => {
    const { container } = render(<NodePanel />)
    expect(container.querySelector('.side-panel-right')).toBeNull()
  })

  it('선택 노드: 실 KEY METRICS + 실 혼동쌍(§5-6, 측정 전) + 실계산 4축(데이터 없으면 "—")', async () => {
    useBrainStore.setState({ selectedNodeId: 'N_play_a' }) // stubDiagnosis 기본=진단 null·혼동 가설1
    const { container } = render(<NodePanel />)
    expect(screen.getByText('play a')).toBeTruthy()
    // 방향성 혼동은 실 confusion_edges(§5-6) — mock 배지 사라지고 §5-6 실데이터 배지
    expect(screen.getByText('헷갈리기 쉬운 의도')).toBeTruthy()
    expect(screen.queryByText('미리보기 · mock')).toBeNull()
    await waitFor(() =>
      expect(container.querySelectorAll('.confusion-row').length).toBeGreaterThanOrEqual(1),
    )
    expect(screen.getByText('play b')).toBeTruthy() // labelOf(play_b) — 실 edge 대상
    expect(screen.getByText('추측')).toBeTruthy() // 상태칩 (hypothesized)
    expect(screen.getByText('시험 전')).toBeTruthy() // 미측정 rate — 지어낸 % 아님
    // 실 지표 4종 (KEY METRICS 전부 실데이터)
    expect(screen.getByText('공부한 양').previousSibling?.textContent).toBe('30')
    expect(screen.getByText('사람이 확인').previousSibling?.textContent).toBe('12')
    expect(screen.getByText('경험 다양성').previousSibling?.textContent).toBe('0%')
    expect(screen.getByText('대표 예문').previousSibling?.textContent).toBe('0')
    // WHY-WEAK는 §7-3 실계산 배지 (mock 아님)
    expect(screen.getByText('자동 진단')).toBeTruthy()
    // 진단 데이터 없음 → 4축 모두 "—"(지어내지 않음)
    for (const ax of ['말이 여러 뜻으로 들려요', '화면 상황 경험이 적어요', '다양한 선생님을 못 만났어요', '사람이 확인한 데이터가 적어요']) {
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
      const g = screen.getByText('사람이 확인한 데이터가 적어요').closest('.axis-row') as HTMLElement
      expect(within(g).getByText('HIGH')).toBeTruthy()
    })
    // play_b로 전환 → 잔류 HIGH가 아니라 LOW로 바뀐다
    useBrainStore.setState({ selectedNodeId: 'N_play_b' })
    await waitFor(() => {
      const g = screen.getByText('사람이 확인한 데이터가 적어요').closest('.axis-row') as HTMLElement
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
      const gold = screen.getByText('사람이 확인한 데이터가 적어요').closest('.axis-row') as HTMLElement
      expect(within(gold).getByText('HIGH')).toBeTruthy()
    })
    const cov = screen.getByText('화면 상황 경험이 적어요').closest('.axis-row') as HTMLElement
    expect(within(cov).getByText('LOW')).toBeTruthy()
  })

  it('강화하기 클릭 → POST /v1/gym/pack 실 브리핑(§7-4): 문항 수·전략 칩·정직 표기 + 3모드 버튼', async () => {
    const sent = stubGymFlow()
    useBrainStore.setState({ selectedNodeId: 'N_play_a' })
    render(<NodePanel />)
    fireEvent.click(screen.getByText('🚀 강화하기'))
    // 실 pack의 items=20 그대로 (서버 응답 도착 전엔 브리핑 없음)
    expect(await screen.findByText('20개')).toBeTruthy()
    // pack 생성이 T4.2 계약(node_intent=intent_id)으로 나갔는지
    const packCall = sent.find((s) => s.url === '/v1/gym/pack')
    expect(packCall?.method).toBe('POST')
    expect(packCall?.body?.node_intent).toBe('play_a')
    // Target Confusion: 실 target_edges의 한글 라벨 짝
    expect(screen.getByText('play a ↔ play b')).toBeTruthy()
    // Difficulty 한글 매핑
    expect(screen.getByText('보통 → 어려움')).toBeTruthy()
    // persona_mix 부재 → 개수 날조 없이 부재 문구 (정직성)
    expect(screen.getByText('성향 묶음 준비 중')).toBeTruthy()
    // 전략·진단 칩
    expect(screen.getByText('헷갈림 구분 연습')).toBeTruthy()
    expect(screen.getByText('선생님 확인 받기')).toBeTruthy()
    expect(screen.getByText('헷갈림 잦음')).toBeTruthy()
    // needs_human=true → §8-1 Gym 3모드(한글) 버튼
    expect(screen.getByText('훈련 방식을 골라 주세요')).toBeTruthy()
    for (const label of ['의도 알아맞히기', '알맞은 의미 고르기', '바로잡기 연습']) {
      expect(screen.getByRole('button', { name: label })).toBeTruthy()
    }
  })

  it('브리핑 → 모드 클릭 → openGymSession이 intent_id + 서버 진단으로 origin 전송 + 오버레이 마운트', async () => {
    // Phase 3 게이트 시임 + T4.3: 강화하기→pack 브리핑→openGymSession 배선 고정
    const sent = stubGymFlow()
    useBrainStore.setState({ selectedNodeId: 'N_play_a' })
    render(<NodePanel />)
    fireEvent.click(screen.getByText('🚀 강화하기'))
    fireEvent.click(await screen.findByRole('button', { name: '의도 알아맞히기' }))
    await waitFor(() => expect(screen.getByRole('dialog', { name: '훈련 세션' })).toBeTruthy())
    const gym = sent.find((s) => s.url === '/v1/gym/session')
    expect(gym).toBeTruthy()
    const origin = (gym!.body as {
      origin: { node: string; diagnosis: string[]; target_confusion: string | null }
    }).origin
    expect(origin.node).toBe('play_a') // node_id였다면 백엔드 422
    expect(origin.diagnosis).toEqual(['CONFUSION_HIGH', 'GOLD_LOW']) // 서버 진단 코드 그대로
    expect(origin.target_confusion).toBe('play_b') // 브리핑의 target edge와 일치(§7-4)
  })

  it('세션 제출 성공 → 정확한 submit URL로 POST + reloadNonce 증가(§6-7 [6] 갱신 트리거)', async () => {
    const sent = stubGymFlow()
    useBrainStore.setState({ selectedNodeId: 'N_play_a' })
    const before = useBrainStore.getState().reloadNonce
    render(<NodePanel />)
    fireEvent.click(screen.getByText('🚀 강화하기'))
    fireEvent.click(await screen.findByRole('button', { name: '의도 알아맞히기' }))
    const dialog = await screen.findByRole('dialog', { name: '훈련 세션' })
    // 아이템 1개 응답 → 제출 화면
    fireEvent.click(within(dialog).getByRole('button', { name: 'play a' }))
    expect(useBrainStore.getState().reloadNonce).toBe(before) // 제출 전엔 오르지 않는다
    fireEvent.click(within(dialog).getByRole('button', { name: '제출하기' }))
    await waitFor(() => expect(useBrainStore.getState().reloadNonce).toBe(before + 1))
    // 제출이 정확한 세션 URL·바디로 나갔는지 고정(경로 회귀 방지 — 리뷰)
    const submit = sent.find((s) => s.url === '/v1/gym/session/GS_x/submit')
    expect(submit?.method).toBe('POST')
    expect((submit?.body as { results: unknown[] }).results).toHaveLength(1)
  })

  it('제출 없이 ✕ 닫기 → reloadNonce 불변(취소는 refetch를 유발하지 않는다)', async () => {
    stubGymFlow()
    useBrainStore.setState({ selectedNodeId: 'N_play_a' })
    const before = useBrainStore.getState().reloadNonce
    render(<NodePanel />)
    fireEvent.click(screen.getByText('🚀 강화하기'))
    fireEvent.click(await screen.findByRole('button', { name: '의도 알아맞히기' }))
    const dialog = await screen.findByRole('dialog', { name: '훈련 세션' })
    fireEvent.click(within(dialog).getByRole('button', { name: '닫기' }))
    expect(screen.queryByRole('dialog', { name: '훈련 세션' })).toBeNull()
    expect(useBrainStore.getState().reloadNonce).toBe(before)
  })

  it('needs_human=false(A/D 전용) 브리핑 → 모드 버튼 없이 Foundry 안내만 (정직성)', async () => {
    const sent = stubGymFlow()
    // pack 응답만 A 전용으로 교체 — 사람 세션이 필요 없는 pack
    const base = vi.mocked(fetch)
    vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
      if (url === '/v1/gym/pack') {
        return { ok: true, json: async () => ({
          ...PACK_RESP,
          pack: { ...PACK_RESP.pack, strategy: ['A_DATA_COVERAGE'], delivery_modes: [] },
          strategy: ['A_DATA_COVERAGE'],
          diagnosis_codes: ['COVERAGE_LOW'],
          needs_human: false,
        }) } as Response
      }
      return base(url, init)
    }))
    useBrainStore.setState({ selectedNodeId: 'N_play_a' })
    render(<NodePanel />)
    fireEvent.click(screen.getByText('🚀 강화하기'))
    expect(await screen.findByText(/데이터 공장\(Foundry\)에 시나리오 생성만 요청했어요/)).toBeTruthy()
    expect(screen.queryByText('훈련 방식을 골라 주세요')).toBeNull()
    expect(screen.queryByRole('button', { name: '의도 알아맞히기' })).toBeNull()
    void sent
  })

  it('§5-6 실 혼동쌍: 측정된 edge는 rate %+확정 칩, 미측정은 "측정 전"+가설 칩', async () => {
    stubDiagnosis(undefined, {
      intent_id: 'play_a',
      measured: true,
      edges: [
        { to_predicted: 'vis_a', confusion_rate: 0.38, state: 'confirmed', origin: 'ARENA_MATRIX' },
        { to_predicted: 'play_b', confusion_rate: null, state: 'hypothesized', origin: 'SKEPTIC' },
      ],
    })
    useBrainStore.setState({ selectedNodeId: 'N_play_a' })
    const { container } = render(<NodePanel />)
    await waitFor(() => expect(container.querySelectorAll('.confusion-row').length).toBe(2))
    const rows = [...container.querySelectorAll('.confusion-row')] as HTMLElement[]
    // 백엔드 정렬 그대로: 측정된 confirmed(0.38)가 먼저 — rate %와 확정 칩
    expect(within(rows[0]).getByText('38%')).toBeTruthy()
    expect(within(rows[0]).getByText('확인됨')).toBeTruthy()
    // 미측정 가설은 "측정 전"(지어낸 % 아님) + 가설 칩
    expect(within(rows[1]).getByText('시험 전')).toBeTruthy()
    expect(within(rows[1]).getByText('추측')).toBeTruthy()
    // measured=true → 하단 "SKEPTIC 가설 단계" 안내문구는 뜨지 않는다
    expect(screen.queryByText(/SKEPTIC 가설 단계 혼동쌍/)).toBeNull()
  })
})
