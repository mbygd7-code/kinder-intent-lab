/**
 * WebGL 가용성 — 마운트 전 1회 동기 판정.
 *
 * store 초기값(webglOk)과 App/BrainScreen의 뷰 분기(effectiveMode)가 공유한다.
 * 미지원 기기는 3D 대신 대시보드가 상시 화면이 된다(2D 지도 폴백은 2026-07-14 대시보드로 대체).
 */
export function webglAvailable(): boolean {
  try {
    const canvas = document.createElement('canvas')
    return Boolean(canvas.getContext('webgl2') ?? canvas.getContext('webgl'))
  } catch {
    return false
  }
}
