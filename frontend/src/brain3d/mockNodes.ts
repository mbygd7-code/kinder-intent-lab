/**
 * 임시 노드 데이터 — Observatory API(후속 티켓)가 붙기 전까지의 스켈레톤 전용.
 *
 * v1 의미 노드 수 = intent 수(~100, §5). AC "노드 100 기준 프레임 유지" 검증을 위해
 * 7 region × 15 = 105개를 만든다. 실 데이터로 교체되면 이 파일은 제거된다.
 * 주의: brightness·정확도 등 훈련 상태 값은 절대 만들지 않는다 — 그 원천은 Arena뿐(원칙 8).
 */
import type { NodeSeed } from './layout'
import { REGIONS } from './regions'

export function makeMockNodes(perRegion = 15): NodeSeed[] {
  return REGIONS.flatMap((region) =>
    Array.from({ length: perRegion }, (_, i) => {
      const intentId = `${region.id.toLowerCase()}_intent_${String(i + 1).padStart(2, '0')}`
      return { nodeId: `BN_${intentId}`, intentId, region: region.id }
    }),
  )
}
