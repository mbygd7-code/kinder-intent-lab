/**
 * 모션 게이트 — prefers-reduced-motion 존중 + 비브라우저(jsdom) 환경 결정론.
 *
 * matchMedia가 없으면(jsdom) 모션 끔으로 간주한다 — 테스트가 최종값을 즉시 단언할 수 있고,
 * 접근성 기본값도 보수적이 된다. 모션은 장식이지 정보가 아니다(정직성: 값은 모션 없이도 동일).
 */
export function motionOff(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') return true
  return window.matchMedia('(prefers-reduced-motion: reduce)').matches
}
