/**
 * Region 라벨 콜아웃 — 3중 인코딩의 ② (§7-5: 색 + 라벨 + 위치).
 *
 * 레퍼런스 이미지처럼 [이름 | 스테이지 | 점수] 칩을 리더라인으로 로브에 연결한다.
 * 점수 = region reliability(§7-2, Arena heldout이 원천) — Arena 미실행이면 null → "—"
 * (값을 지어내지 않는다, 원칙 8).
 * 스테이지 = §7-6 성장 스테이지(stage_name, 전부 Arena 산출) — 미측정 region은
 * "Dormant"(잠자는 뇌)로 읽힌다: 실패가 아니라 아직 깨어나기 전 상태다.
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
  const brain = useBrainStore((s) => s.brain)
  const selectRegion = useBrainStore((s) => s.selectRegion)
  const selectedRegionId = useBrainStore((s) => s.selectedRegionId)
  return (
    <>
      {REGIONS.map((r) => {
        const pos = labelPos(r.center)
        const score = scores[r.id as RegionId]
        // §7-6 stage_name — API 도착 전엔 표기하지 않는다(지어내지 않음)
        const stageName = brain?.regions.find((x) => x.region === r.id)?.stage_name ?? null
        const active = selectedRegionId === r.id
        return (
          <group key={r.id}>
            <Line
              points={[r.center as unknown as [number, number, number], pos]}
              color={r.color}
              lineWidth={active ? 2 : 1}
              transparent
              opacity={active ? 0.9 : 0.55}
              raycast={() => null}
            />
            {/* distanceFactor 미사용 — 라벨은 깊이와 무관한 고정 크기 UI 콜아웃(레퍼런스 스타일) */}
            <Html position={pos} center wrapperClass="region-label-wrap" zIndexRange={[2, 0]}>
              <button
                type="button"
                className={`region-label${active ? ' region-label-active' : ''}`}
                style={active ? { borderColor: r.color } : undefined}
                onClick={() => selectRegion(active ? null : r.id)}
              >
                <span className="region-dot" style={{ backgroundColor: r.color }} />
                <span className="region-name">{r.label}</span>
                {stageName != null && <span className="region-stage">{stageName}</span>}
                <span className="region-score" style={{ color: r.color }}>
                  {score == null ? '—' : Math.round(score * 100)}
                </span>
              </button>
            </Html>
          </group>
        )
      })}
    </>
  )
}
