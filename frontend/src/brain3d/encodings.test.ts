/**
 * T3.5 AC — §7-5 바인딩 + 원칙 8(절대 규칙 3).
 *
 * 핵심: brightness의 유일한 입력은 heldout_accuracy다. 훈련 이벤트가 바꾸는 값들
 * (evidence_total·diversity·pending)을 아무리 흔들어도 brightness는 변하지 않는다.
 */
import { describe, expect, it } from 'vitest'

import { DORMANT_BRIGHTNESS, visualFromNode } from './encodings'

const BASE = {
  evidence_total: 10,
  evidence_diversity: 0.4,
  heldout_accuracy: null,
  pending_evaluation: false,
}

describe('visualFromNode — §7-5 바인딩', () => {
  it('heldout null → Dormant 어둡게 (§7-6 Stage 0)', () => {
    expect(visualFromNode(BASE).brightness).toBe(DORMANT_BRIGHTNESS)
  })

  it('AC(원칙 8): 훈련 이벤트 필드는 brightness를 절대 못 바꾼다', () => {
    const before = visualFromNode(BASE).brightness
    // 훈련 20문제 → evidence 폭증 + 다양성 변화 + pending 점등 (모킹)
    const afterTraining = visualFromNode({
      evidence_total: 10_000,
      evidence_diversity: 1.0,
      heldout_accuracy: null, // Arena는 아직 안 돌았다
      pending_evaluation: true,
    })
    expect(afterTraining.brightness).toBe(before) // 여전히 Dormant
    expect(afterTraining.size).toBeGreaterThan(visualFromNode(BASE).size) // size는 변한다
    expect(afterTraining.pendingRing).toBe(true) // ring은 점등된다
  })

  it('brightness는 heldout에 단조 증가, heldout에만 반응', () => {
    const low = visualFromNode({ ...BASE, heldout_accuracy: 0.2 })
    const high = visualFromNode({ ...BASE, heldout_accuracy: 0.9 })
    expect(high.brightness).toBeGreaterThan(low.brightness)
    expect(low.brightness).toBeGreaterThan(DORMANT_BRIGHTNESS)
    // 같은 heldout + 다른 훈련량 → 같은 brightness
    const sameHeldoutMoreTraining = visualFromNode({
      ...BASE, heldout_accuracy: 0.9, evidence_total: 99_999, evidence_diversity: 1,
    })
    expect(sameHeldoutMoreTraining.brightness).toBe(high.brightness)
  })

  it('size는 evidence_total에 단조 증가(포화), density는 diversity 클램프', () => {
    const s0 = visualFromNode({ ...BASE, evidence_total: 0 })
    const s1 = visualFromNode({ ...BASE, evidence_total: 50 })
    const s2 = visualFromNode({ ...BASE, evidence_total: 500 })
    expect(s0.size).toBeLessThan(s1.size)
    expect(s1.size).toBeLessThan(s2.size)
    expect(visualFromNode({ ...BASE, evidence_diversity: 1.7 }).density).toBe(1)
    expect(visualFromNode({ ...BASE, evidence_diversity: -0.2 }).density).toBe(0)
  })
})

// brain3d 소스 원문 (vite raw glob — 서브디렉터리 포함, 테스트 파일 제외).
// 코드만 스캔하려고 주석은 벗긴다.
const SOURCES = import.meta.glob(['./**/*.ts', './**/*.tsx', '!./**/*.test.*'], {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>

function stripComments(src: string): string {
  return src.replace(/\/\*[\s\S]*?\*\//g, '').replace(/\/\/[^\n]*/g, '')
}

// brightness 쓰기(값 생성·변조) 패턴: `brightness =`, `+=` 등 복합 대입, `++/--`,
// `["brightness"] =`, 객체 리터럴 키 `brightness:` — 읽기 `.brightness`는 허용
const BRIGHTNESS_WRITE = new RegExp(
  [
    String.raw`brightness\s*[+\-*/|&^%]?=(?!=)`,
    String.raw`brightness\s*(\+\+|--)`,
    String.raw`\[\s*["']brightness["']\s*\]\s*[+\-*/|&^%]?=(?!=)`,
    String.raw`brightness\s*:`,
  ].join('|'),
)

describe('코드 리뷰 체크리스트 강제 — brightness 원천 스캔 (§7-5·원칙 8)', () => {
  it('brightness 계산·heldout 코드 참조는 encodings.ts 밖에 없다 (주석 제외)', () => {
    const offenders: string[] = []
    for (const [path, raw] of Object.entries(SOURCES)) {
      if (path.endsWith('/encodings.ts') || path === './encodings.ts') continue
      const code = stripComments(raw)
      // 정의·변조 금지: 다른 파일이 brightness 값을 만들면 원천이 둘이 된다
      if (BRIGHTNESS_WRITE.test(code)) offenders.push(`${path}: brightness 쓰기`)
      if (/heldout/i.test(code)) offenders.push(`${path}: heldout 코드 참조`)
    }
    expect(offenders).toEqual([])
    expect(Object.keys(SOURCES).length).toBeGreaterThan(5) // 스캔이 실제로 파일을 읽었는지
  })

  it('스캔 자가 검증: 위반 패턴 샘플을 실제로 잡아낸다 (가드가 살아있음)', () => {
    for (const bad of [
      'v.brightness = 1',
      'v.brightness *= flicker',
      'x["brightness"] = 0.5',
      'const v = { brightness: 1 }',
      'v.brightness++',
    ]) {
      expect(BRIGHTNESS_WRITE.test(bad), bad).toBe(true)
    }
    expect(BRIGHTNESS_WRITE.test('const b = v.brightness')).toBe(false) // 읽기는 허용
  })
})
