/**
 * 교사 친화 용어 사전 — 백엔드 원값(영문 enum·stage_name)을 화면에서 쉬운 한글로.
 *
 * 원칙: 값 자체(API·store)는 절대 바꾸지 않는다 — 표시만 번역한다(intentLabels와 동일 규율).
 * 미등록 값은 원문 그대로 보여준다(지어내지 않음).
 */

/** §7-6 성장 스테이지 이름(백엔드 STAGE_NAMES 원문) → 교사용 한글 */
export const STAGE_LABEL_KO: Record<string, string> = {
  Dormant: '잠자는 중',
  Spark: '첫 불꽃',
  'Cluster Awake': '조금씩 깨어남',
  'Region Online': '영역이 깨어남',
  'Semantic Cross-Region Flow': '영역끼리 연결',
  'Whole Brain Resonance': '뇌 전체가 반짝임',
}

export function stageKo(name: string | null | undefined): string | null {
  if (name == null) return null
  return STAGE_LABEL_KO[name] ?? name
}

/** "N단계 · 이름" — 헤더·패널 공용 표기 */
export function stageWithNumber(stage: number | null | undefined, name: string | null | undefined): string | null {
  const label = stageKo(name)
  if (label == null) return null
  return stage != null ? `${stage}단계 · ${label}` : label
}
