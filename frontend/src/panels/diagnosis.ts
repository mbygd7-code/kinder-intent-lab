/**
 * §7-3 Weakness Diagnosis Engine — **MOCK 미리보기** (T3.6 티켓 AC: "이 단계는 계산값 mock").
 *
 * 실 진단 엔진은 §6-1(강화 4유형 자동 매핑) 소관이며 Atlas·S5·Evidence·Arena 데이터를 쓴다.
 * 여기서는 confusion_edges·Atlas가 아직 비어 있으므로 결정론적 mock을 만든다 — 패널이 반드시
 * "미리보기(mock)"로 표기해 실측으로 오인되지 않게 한다(정보 정직성).
 *
 * 단, **Gold Data 축만은 mock이 아니다**: 실 gold_count(GOLD evidence 절대량, §7-3 정의)에서
 * goldDataLevel()로 계산한다 — 실데이터가 있으면 실데이터를 쓴다.
 */
import { fmix32, fnv1a } from '../brain3d/hash'

export type WeakLevel = 'HIGH' | 'MED' | 'LOW'

export interface Confusion {
  intentId: string
  rate: number // 0..1 (mock)
}

export interface WhyWeak {
  ambiguousLanguage: WeakLevel // mock — Atlas 경쟁 intent 수 (§2)
  screenContextCoverage: WeakLevel // mock — workspace 조합 커버리지 (S5)
  personaDiversity: WeakLevel // mock — evidence persona 엔트로피 (§3-1)
}

export interface MockDiagnosis {
  confusions: Confusion[]
  why: WhyWeak
}

const LEVELS: WeakLevel[] = ['LOW', 'MED', 'HIGH']

function seeded(nodeId: string, salt: string): number {
  return fmix32(fnv1a(`${nodeId}#${salt}`)) / 0xffffffff
}

/**
 * 실 gold_count → Gold Data 축 (mock 아님).
 * 10/3은 HIGH/MED/LOW **UI 표시 버킷**이지 실험 임계값이 아니다(절대 규칙 1은 모델·실험
 * 파라미터 대상 — §0-3 원칙 7). 배지 렌더링용 프레젠테이션 상수이며 추론·집계에 영향 없음.
 */
export function goldDataLevel(goldCount: number): WeakLevel {
  if (goldCount >= 10) return 'HIGH'
  if (goldCount >= 3) return 'MED'
  return 'LOW'
}

export function mockDiagnosis(
  nodeId: string,
  allIntentIds: string[],
  // 자기 intent는 호출자가 넘긴다(NodePanel은 node.intent_id 보유) — node_id="N_"+intent_id
  // 스킴에 의존하지 않게. 미전달 시에만 관례로 유추(테스트 편의).
  selfIntent: string = nodeId.replace(/^N_/, ''),
): MockDiagnosis {
  const others = allIntentIds.filter((i) => i !== selfIntent)

  // 결정론 정렬 후 상위 3개를 혼동 상대로 — rate 내림차순으로 최종 정렬(단조성 보장)
  const ranked = [...others].sort(
    (a, b) => seeded(nodeId, `c_${b}`) - seeded(nodeId, `c_${a}`),
  )
  const confusions: Confusion[] = ranked
    .slice(0, 3)
    .map((intentId) => ({
      intentId,
      rate: Math.round((0.06 + 0.32 * seeded(nodeId, `r_${intentId}`)) * 100) / 100,
    }))
    .sort((a, b) => b.rate - a.rate)

  const pick = (salt: string): WeakLevel => LEVELS[Math.floor(seeded(nodeId, salt) * 3) % 3]
  return {
    confusions,
    why: {
      ambiguousLanguage: pick('amb'),
      screenContextCoverage: pick('scr'),
      personaDiversity: pick('per'),
    },
  }
}
