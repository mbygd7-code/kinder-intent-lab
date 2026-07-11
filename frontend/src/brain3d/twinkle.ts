/**
 * 파티클 비정형 반짝임 — 순수 장식 셰이더 (데이터 인코딩 아님).
 *
 * 전용 ShaderMaterial: 입자마다 위치 해시로 위상·속도가 달라 비정형하게 깜박인다.
 * 별빛 기법 — 소수(≈35%)만 깊게, 나머지는 은은하게: 전체가 일렁이지 않고 "반짝"인다.
 * **감광 방향만**: 배수 ∈ [1-AMP, 1.0] — 절대 기본 광량보다 밝아지지 않으므로
 * 블룸 규율(빛남 = Arena 정확도 전용)의 luma 상한이 그대로 유지된다
 * (twinkle.test.ts가 dip-only 형태를 잠근다).
 *
 * CPU 비용 ≈ 0: 전 재질이 공유 uniform(uTime·uScale) 2개를 참조 — 드라이버 1개가 갱신.
 */
import * as THREE from 'three'

/** 깊게 깜박이는 소수 입자의 감광 폭 (최저 20% 광량 — 확실히 보이는 별빛) */
export const TWINKLE_DEEP_AMP = 0.8
/** 나머지 입자의 은은한 감광 폭 */
export const TWINKLE_BASE_AMP = 0.25
/** 깊은 깜박임 입자 비율 (위치 해시 < 이 값) */
export const TWINKLE_DEEP_RATIO = 0.4

/** 전 트윙클 재질이 공유하는 시간 uniform — BrainFieldLayer 드라이버가 갱신 */
export const sharedTwinkleTime = { value: 0 }
/** 포인트 크기 감쇠 스케일(= 렌더버퍼 높이/2, PointsMaterial과 동일 규칙) — 드라이버가 갱신 */
export const sharedPointScale = { value: 400 }

export const TWINKLE_VERTEX = /* glsl */ `
uniform float uTime;
uniform float uScale;
uniform float uSize;
varying vec3 vColor;
varying float vTw;
void main() {
  vColor = color;
  // 위치 해시 → 입자별 고유 위상·속도 (결정론 — 같은 지오메트리 = 같은 패턴)
  float h = fract(sin(dot(position, vec3(12.9898, 78.233, 37.719))) * 43758.5453);
  float sp = mix(1.6, 5.2, fract(h * 13.73));
  float amp = mix(${TWINKLE_BASE_AMP.toFixed(2)}, ${TWINKLE_DEEP_AMP.toFixed(2)}, step(h, ${TWINKLE_DEEP_RATIO.toFixed(2)}));
  // 감광 딥만: 1.0 - amp·(0..1) — 기본 광량을 절대 넘지 않는다
  vTw = 1.0 - amp * (0.5 + 0.5 * sin(uTime * sp + h * 6.28318));
  vec4 mv = modelViewMatrix * vec4(position, 1.0);
  // 크기도 함께 딥 — 어두워질 때 살짝 작아져 반짝임이 확실히 지각된다 (감소 방향만)
  gl_PointSize = uSize * (uScale / -mv.z) * (0.7 + 0.3 * vTw);
  gl_Position = projectionMatrix * mv;
}
`

export const TWINKLE_FRAGMENT = /* glsl */ `
uniform vec3 uTint;
uniform float uOpacity;
varying vec3 vColor;
varying float vTw;
void main() {
  gl_FragColor = vec4(vColor * uTint * vTw, uOpacity);
  #include <colorspace_fragment>
}
`

/** 트윙클 포인트 재질 — vertexColors × uTint × 감광 딥. 호출부가 dispose 책임. */
export function makeTwinkleMaterial(): THREE.ShaderMaterial {
  return new THREE.ShaderMaterial({
    vertexShader: TWINKLE_VERTEX,
    fragmentShader: TWINKLE_FRAGMENT,
    uniforms: {
      uTime: sharedTwinkleTime,
      uScale: sharedPointScale,
      uSize: { value: 0.01 },
      uTint: { value: new THREE.Color(1, 1, 1) },
      uOpacity: { value: 1 },
    },
    vertexColors: true,
    transparent: true,
    depthWrite: false,
    blending: THREE.AdditiveBlending,
  })
}
