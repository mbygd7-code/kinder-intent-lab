/**
 * @vitest-environment jsdom
 *
 * 화면 씨드 스튜디오 AC — 목록(최소기준 배지)·PIN 게이트(미입력 하이라이트)·작성 POST·확장 미리보기.
 */
import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SituationSeedPanel } from './SituationSeedPanel'

const CATALOG = {
  version: 'ss-1.0',
  domains: ['PLAY', 'OBSERVATION', 'DOCUMENT', 'VISUAL', 'COMMUNICATION', 'OPERATION', 'REFLECTION', 'STUDIO'],
  scenario_variants: 4,
  vocabulary: {
    surface_types: { play_board: '놀이 보드 화면', photo_album: '사진첩 화면' },
    object_kinds: { photo: '사진', text: '글' },
    actions: { move_object: '카드를 옮김(드래그)', zoom_in: '화면을 확대함' },
  },
  vs_vocabulary: {
    scene_type: ['INDOOR_CLASSROOM'], activity_types: ['FREE_PLAY'], materials: ['BLOCK'],
    observed_actions: ['OBSERVE'], interaction_pattern: ['PEER_COLLABORATIVE'],
    group_size_band: ['SMALL_GROUP'], spatial_pattern: ['SCATTERED'],
  },
  seeds: [
    {
      seed_id: 'play_board_block_arrange', domains: ['PLAY'],
      workspace_state: {
        surface_type: 'play_board', objects_summary: { photo: 4, text: 2 },
        selection: { type: 'photo', count: 2 }, recent_actions: ['move_object', 'zoom_in'],
        visual_semantics: [{
          object_ref: 'photo_1', schema_version: 'vs-1.0', extractor_version: 'SYNTH_BUILDER_v1',
          scene_type: ['INDOOR_CLASSROOM'], identity_removed: true as const,
        }],
      },
      ready: true, unmet: [],
    },
    {
      seed_id: 'draft_incomplete', domains: [],
      workspace_state: {
        surface_type: 'photo_album', objects_summary: { photo: 2 },
        selection: {}, recent_actions: [], visual_semantics: [],
      },
      ready: false, unmet: ['사진이 있는데 사진 서술(visual_semantics)이 없음 — 최소 1장 서술 필요'],
    },
  ],
}

const PREVIEW = {
  anchor_seed_id: 'play_board_block_arrange',
  domain: 'PLAY',
  variants: [
    {
      surface_type: 'play_board', objects_summary: { photo: 5, text: 1 },
      selection: {}, recent_actions: ['zoom_in'], visual_semantics: [],
    },
  ],
}

function stub() {
  const calls: Array<{ url: string; method: string; body?: unknown }> = []
  vi.stubGlobal('fetch', vi.fn(async (url: string, init?: RequestInit) => {
    const u = String(url)
    calls.push({
      url: u,
      method: init?.method ?? 'GET',
      body: init?.body ? JSON.parse(String(init.body)) : undefined,
    })
    if (u.endsWith('/v1/situation-seeds')) return { ok: true, json: async () => CATALOG } as Response
    if (u.includes('/vocabulary')) return { ok: true, json: async () => ({ ok: true, updated: false }) } as Response
    if (u.includes('/expand-preview')) return { ok: true, json: async () => PREVIEW } as Response
    if (u.includes('/seeds')) return { ok: true, json: async () => ({ ok: true, total: 3 }) } as Response
    return { ok: false, status: 404, json: async () => ({}) } as Response
  }))
  return calls
}

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

describe('SituationSeedPanel', () => {
  it('목록: 씨드 상황이 한글로 요약되고, 최소기준 배지·미달 사유가 보인다', async () => {
    stub()
    render(<SituationSeedPanel onClose={() => {}} />)
    expect(await screen.findByText('play_board_block_arrange')).toBeTruthy()
    expect(screen.getAllByText(/보고 있던 화면: 놀이 보드 화면/).length).toBeGreaterThan(0)
    expect(screen.getByText(/선택 중: 사진 2개/)).toBeTruthy()
    expect(screen.getByText('✨ 확장 가능')).toBeTruthy()
    expect(screen.getByText('⚠️ 최소기준 미달')).toBeTruthy()
    expect(screen.getByText(/사진 서술.*없음/)).toBeTruthy() // 미달 사유 체크리스트
  })

  it('PIN 게이트: 비밀번호·이름 없이 [＋ 새 씨드]를 누르면 입력창이 하이라이트된다', async () => {
    stub()
    const { container } = render(<SituationSeedPanel onClose={() => {}} />)
    await screen.findByText('play_board_block_arrange')
    fireEvent.click(screen.getByRole('button', { name: /새 씨드 만들기/ }))
    expect(container.querySelectorAll('.input-missing').length).toBe(2)
    expect(screen.getByText(/비밀번호와 작성자 이름을 입력해주세요/)).toBeTruthy()
  })

  it('CSV 게이트: 비밀번호·이름 없이 [⬇ CSV 폼 받기]/[⬆ CSV 업로드]도 막힌다(하이라이트)', async () => {
    stub()
    const { container } = render(<SituationSeedPanel onClose={() => {}} />)
    await screen.findByText('play_board_block_arrange')
    fireEvent.click(screen.getByRole('button', { name: /CSV 폼 받기/ }))
    expect(container.querySelectorAll('.input-missing').length).toBe(2)
    fireEvent.click(screen.getByRole('button', { name: /CSV 업로드/ }))
    expect(container.querySelectorAll('.input-missing').length).toBe(2)
    expect(screen.getByText(/비밀번호와 작성자 이름을 입력해주세요/)).toBeTruthy()
  })

  it('작성: 어휘 선택으로 조립한 씨드가 pin·작성자와 함께 POST된다', async () => {
    const calls = stub()
    render(<SituationSeedPanel onClose={() => {}} />)
    await screen.findByText('play_board_block_arrange')

    fireEvent.change(screen.getByPlaceholderText(/작성하려면 입력/), { target: { value: '2341' } })
    fireEvent.change(screen.getByPlaceholderText(/예: 명배영/), { target: { value: '명배영' } })
    fireEvent.click(screen.getByRole('button', { name: /새 씨드 만들기/ }))

    fireEvent.change(screen.getByPlaceholderText(/photo_album_field_trip/), {
      target: { value: 'web_new_seed' },
    })
    const textCount = screen.getByLabelText(/^글 수/)
    fireEvent.change(textCount, { target: { value: '3' } })
    fireEvent.click(screen.getByRole('button', { name: '씨드 저장' }))

    await waitFor(() => {
      const post = calls.find((c) => c.method === 'POST' && c.url.endsWith('/seeds'))
      expect(post).toBeTruthy()
      const body = post!.body as { pin: string; editor: string; seed: { seed_id: string; workspace_state: { objects_summary: Record<string, number> } } }
      expect(body.pin).toBe('2341')
      expect(body.editor).toBe('명배영')
      expect(body.seed.seed_id).toBe('web_new_seed')
      expect(body.seed.workspace_state.objects_summary.text).toBe(3)
    })
  })

  it('어휘 관리: 보고 있던 화면 목록에 새 항목이 pin·작성자와 함께 등록된다', async () => {
    const calls = stub()
    render(<SituationSeedPanel onClose={() => {}} />)
    await screen.findByText('play_board_block_arrange')
    fireEvent.change(screen.getByPlaceholderText(/작성하려면 입력/), { target: { value: '2341' } })
    fireEvent.change(screen.getByPlaceholderText(/예: 명배영/), { target: { value: '명배영' } })
    fireEvent.click(screen.getByRole('button', { name: /어휘 관리/ }))

    expect(await screen.findByText('보고 있던 화면')).toBeTruthy() // 어휘 카드 제목
    fireEvent.change(screen.getByLabelText('보고 있던 화면 새 id'), { target: { value: 'art_board' } })
    fireEvent.change(screen.getByLabelText('보고 있던 화면 새 라벨'), { target: { value: '미술 보드 화면' } })
    fireEvent.click(screen.getAllByRole('button', { name: /＋ 추가/ })[0])

    await waitFor(() => {
      const post = calls.find((c) => c.method === 'POST' && c.url.endsWith('/vocabulary'))
      expect(post).toBeTruthy()
      const body = post!.body as { pin: string; editor: string; table: string; vocab_id: string; label_ko: string }
      expect(body.table).toBe('surface_types')
      expect(body.vocab_id).toBe('art_board')
      expect(body.label_ko).toBe('미술 보드 화면')
      expect(body.pin).toBe('2341')
    })
  })

  it('확장 미리보기: 변형이 그려지고 "저장되지 않았어요" 정직 캡션이 보인다', async () => {
    stub()
    render(<SituationSeedPanel onClose={() => {}} />)
    await screen.findByText('play_board_block_arrange')
    fireEvent.change(screen.getByPlaceholderText(/작성하려면 입력/), { target: { value: '2341' } })
    fireEvent.change(screen.getByPlaceholderText(/예: 명배영/), { target: { value: '명배영' } })
    fireEvent.click(screen.getByRole('button', { name: /확장 미리보기/ }))

    expect(await screen.findByText(/변형 1/)).toBeTruthy()
    expect(screen.getByText(/저장되지 않았어요/)).toBeTruthy()
    expect(screen.getByText(/직전 행동: 화면을 확대함/)).toBeTruthy()
  })
})
