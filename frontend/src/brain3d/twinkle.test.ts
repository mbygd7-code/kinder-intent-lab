/**
 * 트윙클 재질 — 감광 딥만(dip-only) 불변식.
 *
 * 배수 vTw ∈ [1-AMP, 1.0]이어야 파티클이 기본 광량을 절대 넘지 않는다 —
 * 블룸 규율(빛남 = Arena 정확도 전용)의 luma 상한이 트윙클로도 깨지지 않는 근거.
 */
import * as THREE from 'three'
import { describe, expect, it } from 'vitest'

import {
  makeTwinkleMaterial,
  sharedPointScale,
  sharedTwinkleTime,
  TWINKLE_BASE_AMP,
  TWINKLE_DEEP_AMP,
  TWINKLE_VERTEX,
} from './twinkle'

describe('twinkle 재질', () => {
  it('공유 uniform(uTime·uScale)을 참조한다 — 드라이버 1개가 전 재질을 구동', () => {
    const m = makeTwinkleMaterial()
    expect(m.uniforms.uTime).toBe(sharedTwinkleTime)
    expect(m.uniforms.uScale).toBe(sharedPointScale)
    m.dispose()
  })

  it('감광 딥만: vTw = 1.0 - amp·(0..1) — 기본 광량 초과 불가 (amp < 1)', () => {
    // 배수식: sin ∈ [-1,1] → (0.5+0.5·sin) ∈ [0,1] → vTw ∈ [1-amp, 1]
    expect(TWINKLE_VERTEX).toContain('vTw = 1.0 - amp * (0.5 + 0.5 * sin(')
    expect(TWINKLE_DEEP_AMP).toBeGreaterThan(0)
    expect(TWINKLE_DEEP_AMP).toBeLessThan(1)
    expect(TWINKLE_BASE_AMP).toBeGreaterThan(0)
    expect(TWINKLE_BASE_AMP).toBeLessThan(TWINKLE_DEEP_AMP)
    // 프래그먼트 곱 적용 + 별빛 기법(소수만 깊게)
    expect(makeTwinkleMaterial().fragmentShader).toContain('* vTw')
    expect(TWINKLE_VERTEX).toContain('step(h,')
  })

  it('위상은 위치 해시 — 파티클별 비정형(결정론) 깜박임', () => {
    expect(TWINKLE_VERTEX).toContain('dot(position, vec3(12.9898, 78.233, 37.719))')
  })

  it('재질 상태: additive·투명·vertexColors — 기존 포인트 룩과 동일 규약', () => {
    const m = makeTwinkleMaterial()
    expect(m.blending).toBe(THREE.AdditiveBlending)
    expect(m.transparent).toBe(true)
    expect(m.depthWrite).toBe(false)
    expect(m.vertexColors).toBe(true)
    m.dispose()
  })
})
