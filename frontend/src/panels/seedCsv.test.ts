/**
 * 화면 씨드 CSV AC — 다운로드 폼 왕복·한글 라벨 인식·행 단위 오류 안내·다중 서술 보존.
 */
import { describe, expect, it } from 'vitest'

import type { SeedCatalog } from '../api/situationSeeds'
import { buildSeedCsv, parseSeedRows } from './seedCsv'

const CATALOG: SeedCatalog = {
  version: 'ss-1.0',
  domains: ['PLAY', 'OBSERVATION', 'DOCUMENT', 'VISUAL', 'COMMUNICATION', 'OPERATION', 'REFLECTION', 'STUDIO'],
  scenario_variants: 4,
  vocabulary: {
    surface_types: { play_board: '놀이 보드 화면', photo_album: '사진첩 화면' },
    object_kinds: { photo: '사진', text: '글' },
    actions: { move_object: '카드를 옮김(드래그)', zoom_in: '화면을 확대함', select_photo: '사진을 고름' },
  },
  vs_vocabulary: {
    scene_type: ['INDOOR_CLASSROOM', 'OUTDOOR_YARD'],
    activity_types: ['FREE_PLAY', 'NATURE_SORTING'],
    materials: ['LEAF', 'BLOCK'],
    observed_actions: ['OBSERVE', 'SORT'],
    interaction_pattern: ['PEER_COLLABORATIVE', 'SOLO'],
    group_size_band: ['SMALL_GROUP', 'INDIVIDUAL'],
    spatial_pattern: ['SCATTERED'],
  },
  seeds: [
    {
      seed_id: 'play_board_block', domains: ['PLAY'],
      workspace_state: {
        surface_type: 'play_board', objects_summary: { photo: 4, text: 2 },
        selection: { type: 'photo', count: 2 }, recent_actions: ['move_object', 'zoom_in'],
        visual_semantics: [{
          object_ref: 'photo_1', schema_version: 'vs-1.0', extractor_version: 'SYNTH_BUILDER_v1',
          scene_type: ['INDOOR_CLASSROOM'], activity_types: ['FREE_PLAY'],
          observed_actions: ['OBSERVE'], interaction_pattern: ['PEER_COLLABORATIVE'],
          group_size_band: 'SMALL_GROUP', identity_removed: true,
        }],
      },
      ready: true, unmet: [],
    },
    {
      // 사진 서술 2개 — CSV 열이 그대로면 업로드가 전체를 보존해야 한다
      seed_id: 'album_two_vs', domains: ['VISUAL'],
      workspace_state: {
        surface_type: 'photo_album', objects_summary: { photo: 8 },
        selection: {}, recent_actions: ['select_photo'],
        visual_semantics: [
          {
            object_ref: 'photo_1', schema_version: 'vs-1.0', extractor_version: 'SYNTH_BUILDER_v1',
            scene_type: ['OUTDOOR_YARD'], activity_types: ['NATURE_SORTING'], materials: ['LEAF'],
            observed_actions: ['SORT'], interaction_pattern: ['PEER_COLLABORATIVE'],
            group_size_band: 'SMALL_GROUP', identity_removed: true,
          },
          {
            object_ref: 'photo_2', schema_version: 'vs-1.0', extractor_version: 'SYNTH_BUILDER_v1',
            scene_type: ['INDOOR_CLASSROOM'], activity_types: ['FREE_PLAY'],
            observed_actions: ['OBSERVE'], interaction_pattern: ['SOLO'],
            group_size_band: 'INDIVIDUAL', identity_removed: true,
          },
        ],
      },
      ready: true, unmet: [],
    },
  ],
}

describe('seedCsv', () => {
  it('왕복: 다운로드한 폼을 그대로 올리면 씨드가 정확히 복원된다(2개 서술 포함, 오류 0)', () => {
    const csv = buildSeedCsv(CATALOG)
    expect(csv).toContain('놀이 보드 화면')
    expect(csv).toContain('카드를 옮김(드래그) > 화면을 확대함')
    expect(csv).toContain('사진 서술 2개')

    const { drafts, errors } = parseSeedRows(csv, CATALOG)
    expect(errors).toEqual([])
    expect(drafts.map((d) => d.seed_id)).toEqual(['play_board_block', 'album_two_vs'])
    expect(drafts[0].workspace_state).toEqual(CATALOG.seeds[0].workspace_state)
    // 서술 열이 다운로드 원형 그대로 → 2개 서술 전체 보존(조용한 유실 방지)
    expect(drafts[1].workspace_state.visual_semantics).toHaveLength(2)
    expect(drafts[1].workspace_state).toEqual(CATALOG.seeds[1].workspace_state)
  })

  it('새 행: 한글 라벨(+영역 구분·행동 순서)로 쓴 행이 씨드로 조립된다', () => {
    const csv = buildSeedCsv(CATALOG) + '\n' + [
      '"my_new_seed"', '"PLAY+VISUAL"', '"사진첩 화면"', '"3"', '"0"', '"사진"', '"1"',
      '"사진을 고름 > 화면을 확대함"',
      '"바깥 마당"', '"자연물 분류"', '""', '"분류하기"', '"또래 협력"', '"소그룹"', '""',
    ].join(',')
    const { drafts, errors } = parseSeedRows(csv, CATALOG)
    expect(errors).toEqual([])
    const mine = drafts.find((d) => d.seed_id === 'my_new_seed')!
    expect(mine.domains).toEqual(['PLAY', 'VISUAL'])
    expect(mine.workspace_state.surface_type).toBe('photo_album')
    expect(mine.workspace_state.objects_summary).toEqual({ photo: 3 })
    expect(mine.workspace_state.selection).toEqual({ type: 'photo', count: 1 })
    expect(mine.workspace_state.recent_actions).toEqual(['select_photo', 'zoom_in'])
    const vs = mine.workspace_state.visual_semantics[0]
    expect(vs.scene_type).toEqual(['OUTDOOR_YARD'])
    expect(vs.materials).toBeUndefined() // 재료 빈칸 = 생략
    expect(vs.identity_removed).toBe(true)
  })

  it('오류 안내: 모르는 화면·행동은 행 번호·씨드id·가능한 값 목록과 함께 거부된다', () => {
    const csv = buildSeedCsv(CATALOG) + '\n' +
      '"bad_row","PLAY","화이트보드","1","0","","","순간이동","","","","","",""'
    const { drafts, errors } = parseSeedRows(csv, CATALOG)
    expect(drafts.find((d) => d.seed_id === 'bad_row')).toBeUndefined()
    expect(errors.length).toBe(2)
    expect(errors[0]).toMatch(/4행\(bad_row\).*화이트보드.*놀이 보드 화면/)
    expect(errors[1]).toMatch(/순간이동.*카드를 옮김/)
  })
})
