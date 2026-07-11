/**
 * Region 호버 타깃 — 각 region 구름을 감싸는 투명 스피어 7개.
 *
 * 포인터가 region 영역에 들어오면 hoveredRegionId를 올린다(라벨·글로우·패널이 반응).
 * 렌더는 완전 투명(opacity 0, colorWrite 끔) — 시각 기여 없음, 레이캐스트만 받는다.
 * 클릭: 노드(NodesMesh)가 stopPropagation하므로 여기 클릭 = "region 빈 공간" 클릭 —
 * onPointerMissed와 대칭으로 선택 해제한다(드래그 회전 릴리즈는 delta 필터로 무시).
 */
import type { ThreeEvent } from '@react-three/fiber'

import { REGIONS } from './regions'
import { useBrainStore } from './store'

export function RegionHoverTargets() {
  const setHoveredRegion = useBrainStore((s) => s.setHoveredRegion)
  const select = useBrainStore((s) => s.select)

  const onClick = (e: ThreeEvent<MouseEvent>) => {
    if (e.delta > 2) return // 드래그(회전) 릴리즈는 클릭이 아니다 — NodesMesh와 동일 가드
    select(null)
  }

  return (
    <group>
      {REGIONS.map((r) => (
        <mesh
          key={r.id}
          position={[...r.center]}
          onPointerOver={(e) => {
            e.stopPropagation()
            setHoveredRegion(r.id)
          }}
          onPointerOut={() => setHoveredRegion(null)}
          onClick={onClick}
        >
          <sphereGeometry args={[r.radius, 16, 12]} />
          {/* 완전 투명 + colorWrite 끔 — 픽셀 기여 0, 레이캐스트 전용 */}
          <meshBasicMaterial transparent opacity={0} colorWrite={false} depthWrite={false} />
        </mesh>
      ))}
    </group>
  )
}
