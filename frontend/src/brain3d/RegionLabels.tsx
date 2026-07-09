/**
 * Region 라벨 콜아웃 — 3중 인코딩의 ② (§7-5: 색 + 라벨 + 위치).
 *
 * 레퍼런스 이미지처럼 [이름 | 점수] 칩을 리더라인으로 로브에 연결한다.
 * 점수 = region reliability(§7-2, Arena heldout이 원천) — Arena 미실행이면 null → "—"
 * (값을 지어내지 않는다, 원칙 8).
 */
import { Html, Line } from '@react-three/drei'

import { REGIONS, type RegionId } from './regions'
import { useBrainStore } from './store'

const ORIGIN: readonly [number, number, number] = [0, -0.05, 0]
const PUSH = 0.72 // 앵커 → 바깥으로 미는 거리

function labelPos(center: readonly [number, number, number]): [number, number, number] {
  const d = [center[0] - ORIGIN[0], center[1] - ORIGIN[1], center[2] - ORIGIN[2]]
  const len = Math.hypot(d[0], d[1], d[2]) || 1
  return [
    center[0] + (d[0] / len) * PUSH,
    center[1] + (d[1] / len) * PUSH,
    center[2] + (d[2] / len) * PUSH,
  ]
}

export function RegionLabels() {
  const scores = useBrainStore((s) => s.regionScores)
  return (
    <>
      {REGIONS.map((r) => {
        const pos = labelPos(r.center)
        const score = scores[r.id as RegionId]
        return (
          <group key={r.id} raycast={() => null}>
            <Line
              points={[r.center as unknown as [number, number, number], pos]}
              color={r.color}
              lineWidth={1}
              transparent
              opacity={0.55}
            />
            {/* distanceFactor 미사용 — 라벨은 깊이와 무관한 고정 크기 UI 콜아웃(레퍼런스 스타일) */}
            <Html position={pos} center wrapperClass="region-label-wrap" zIndexRange={[2, 0]}>
              <div className="region-label">
                <span className="region-dot" style={{ backgroundColor: r.color }} />
                <span className="region-name">{r.label}</span>
                <span className="region-score" style={{ color: r.color }}>
                  {score == null ? '—' : Math.round(score * 100)}
                </span>
              </div>
            </Html>
          </group>
        )
      })}
    </>
  )
}
