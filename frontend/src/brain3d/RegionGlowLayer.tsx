/**
 * Region 은은한 광 — region reliability(Arena heldout 평균, §7-2)의 공간 표현.
 *
 * Arena 파생 광량이라 정직하다(노드 brightness와 같은 등급). 미측정(null) region은
 * 스프라이트 자체가 없다 — 무광이 곧 "측정 전". 광은 공간적으로 넓고 흐릿해
 * 점광(노드 brightness)과 혼동되지 않는다. statusEncodings.regionGlow가 유일 인코더.
 */
import { useMemo } from 'react'
import * as THREE from 'three'

import { REGIONS } from './regions'
import { regionGlow } from './statusEncodings'
import { useBrainStore } from './store'

/** 중립(백색) 방사형 텍스처 — 스프라이트 색으로 region 틴트 */
function makeNeutralGlowTexture(): THREE.Texture {
  const size = 128
  const canvas = document.createElement('canvas')
  canvas.width = size
  canvas.height = size
  const ctx = canvas.getContext('2d')!
  const g = ctx.createRadialGradient(size / 2, size / 2, 0, size / 2, size / 2, size / 2)
  g.addColorStop(0, 'rgba(255, 255, 255, 0.55)')
  g.addColorStop(0.45, 'rgba(255, 255, 255, 0.16)')
  g.addColorStop(1, 'rgba(255, 255, 255, 0)')
  ctx.fillStyle = g
  ctx.fillRect(0, 0, size, size)
  const tex = new THREE.CanvasTexture(canvas)
  tex.needsUpdate = true
  return tex
}

export function RegionGlowLayer() {
  const regionScores = useBrainStore((s) => s.regionScores)
  const tex = useMemo(makeNeutralGlowTexture, [])

  const glows = useMemo(
    () =>
      REGIONS.flatMap((r) => {
        const g = regionGlow(regionScores[r.id] ?? null)
        if (!g) return [] // 미측정 = 무광 (0이 아니라 부재)
        return [{ id: r.id, center: r.center, color: r.color, intensity: g.intensity }]
      }),
    [regionScores],
  )

  if (glows.length === 0) return null
  return (
    <group>
      {glows.map((g) => (
        <sprite key={g.id} position={[...g.center]} scale={[0.85, 0.85, 1]}>
          <spriteMaterial
            map={tex}
            color={g.color}
            transparent
            opacity={0.08 + 0.14 * g.intensity}
            depthWrite={false}
            blending={THREE.AdditiveBlending}
          />
        </sprite>
      ))}
    </group>
  )
}
