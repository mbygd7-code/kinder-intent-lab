/**
 * @vitest-environment jsdom
 *
 * BrainScreen 스모크 (F6): jsdom엔 WebGL이 없다 → §7-5 자동 2D fallback 경로가
 * 실제 렌더로 검증된다. AC2의 라벨·색 축이 "렌더된 DOM"에서 확인되는 유일한 테스트.
 */
import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it } from 'vitest'

import { BrainScreen } from './BrainScreen'
import { REGIONS } from './regions'
import { useBrainStore } from './store'

beforeEach(() => {
  useBrainStore.setState({ selectedNodeId: null, viewMode: '3d' }) // store 기본은 3d여도
})

afterEach(cleanup)

describe('BrainScreen (WebGL 없음 = jsdom)', () => {
  it('WebGL 미지원이면 store가 3d여도 2D map을 렌더하고, 3D 진입 토글을 숨긴다', () => {
    render(<BrainScreen />)
    expect(screen.getByRole('img', { name: /2d fallback/i })).toBeTruthy()
    expect(screen.queryByRole('button')).toBeNull() // 빈 3D 뷰로 들어갈 길 자체가 없다
  })

  it('AC2: 7개 region 라벨이 각자의 region 색으로 렌더된다 (색+라벨 축)', () => {
    const { container } = render(<BrainScreen />)
    const texts = [...container.querySelectorAll('svg text')]
    const rendered = new Map(texts.map((t) => [t.textContent, t.getAttribute('fill')]))
    for (const r of REGIONS) {
      expect(rendered.get(r.label)).toBe(r.color)
    }
  })

  it('노드 점 클릭 → 선택 칩에 intent + region 라벨 표시', () => {
    const { container } = render(<BrainScreen />)
    const dots = [...container.querySelectorAll('svg circle')].filter(
      (c) => Number(c.getAttribute('r')) < 0.1, // region 원(0.26) 제외
    )
    expect(dots.length).toBeGreaterThanOrEqual(100) // AC: 100+ 노드
    fireEvent.click(dots[0])
    const chip = container.querySelector('.selected-chip')
    expect(chip).toBeTruthy()
    expect(chip!.querySelector('strong')!.textContent).toMatch(/_intent_/)
  })
})
