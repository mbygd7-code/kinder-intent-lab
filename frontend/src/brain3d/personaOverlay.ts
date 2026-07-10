/**
 * T5.4 Persona Overlay 시각 채널 (§7-6 "같은 뇌를 페르소나 클러스터별 활성 분포로 전환" · §4-2).
 *
 * prior(§5-5)는 LLM 밖에서 activation에 곱해지는 사전 배수다 — 측정 정확도가 아니다.
 * 중립 = 0.5(강조 없음). prior "부재"는 중립이지 낮은 prior가 아니다 — 없는 intent를
 * 어둡게 그리면 값을 지어내는 것이다(정보 정직성).
 *
 * ── 절대 규칙 3 (§7-5 원칙 8) ────────────────────────────────────────────────
 * 이 오버레이는 **부가(additive) 시각 채널**이다. Node Brightness(Arena held-out
 * 정확도, encodings.ts가 유일한 원천)를 읽지도, 쓰지도, 덮지도 않는다 — 오버레이
 * ON/OFF와 무관하게 기본 노드의 밝기 렌더링은 그대로 유지된다. 이 모듈은 §7-5 표의
 * 어떤 채널(size/density/pulse/ring)도 건드리지 않고 자기 마크만 추가한다.
 * (encodings.test의 소스 스캔이 이 파일에도 강제된다)
 * ──────────────────────────────────────────────────────────────────────────
 */

/** §5-5 — prior의 중립값. 이 값(또는 부재)이면 오버레이 마크를 그리지 않는다 */
export const NEUTRAL_PRIOR = 0.5

/** 오버레이 마크 색 — region 7색과 겹치지 않는 전용 2색 (강조/억제) */
export const BOOST_COLOR = '#ffd166' // prior > 0.5: 이 성향 클러스터가 이 intent를 밀어준다
export const DAMP_COLOR = '#7dd3fc' // prior < 0.5: 이 성향 클러스터가 이 intent를 눌러준다

/** 노드 1개의 오버레이 마크 — strength 0 = 중립(마크 없음) */
export interface PersonaMark {
  /** |prior − 0.5| / 0.5 를 [0,1] 클램프 — 시각 강조 세기 */
  strength: number
  /** true = prior > 0.5(강조), false = prior < 0.5(억제). strength 0이면 무의미 */
  boost: boolean
}

export const NEUTRAL_MARK: PersonaMark = { strength: 0, boost: false }

/**
 * intent의 prior → 오버레이 마크. 유일한 계산 지점 — 3D 레이어와 2D fallback이 공유한다.
 * prior 부재(undefined)·비수치 → 중립: "이 클러스터엔 이 intent의 사전값이 없다"일 뿐이다.
 */
export function markFromPrior(prior: number | null | undefined): PersonaMark {
  if (prior == null || !Number.isFinite(prior)) return NEUTRAL_MARK
  const delta = prior - NEUTRAL_PRIOR
  const strength = Math.min(1, Math.abs(delta) / NEUTRAL_PRIOR)
  if (strength === 0) return NEUTRAL_MARK
  return { strength, boost: delta > 0 }
}
