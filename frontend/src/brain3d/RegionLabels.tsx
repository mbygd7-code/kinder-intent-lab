/**
 * Region 라벨 콜아웃 — 3중 인코딩의 ② (§7-5: 색 + 라벨 + 위치).
 * 라벨은 region 중심에서 바깥으로 밀어낸 지점에 띄운다(구름 가림 방지).
 */
import { Html } from '@react-three/drei'

import { REGIONS } from './regions'

const PUSH_OUT = 1.45 // 중심 → 바깥 방향 배율

export function RegionLabels() {
  return (
    <>
      {REGIONS.map((r) => (
        <Html
          key={r.id}
          position={[r.center[0] * PUSH_OUT, r.center[1] * PUSH_OUT, r.center[2] * PUSH_OUT]}
          center
          distanceFactor={7}
          wrapperClass="region-label-wrap"
          zIndexRange={[2, 0]} // HUD(.brain-hud z-index 3) 아래에 유지 — 기본값은 HUD를 덮는다
        >
          <div className="region-label">
            <span className="region-dot" style={{ backgroundColor: r.color }} />
            {r.label}
          </div>
        </Html>
      ))}
    </>
  )
}
