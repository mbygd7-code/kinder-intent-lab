/**
 * 숫자 카운트업 — 마운트/값 변경 시 rAF로 0.8s ease-out 상승, 값 "변경" 순간 accent 플래시.
 *
 * 모션 꺼짐(reduced-motion·jsdom)이면 최종값 즉시 표시 — 값 자체는 모션과 무관하게 동일하다.
 * 진행 기준은 displayRef(현재 화면값)다 — StrictMode의 effect 이중 실행에도 목표까지
 * 이어서 올라간다(prev 목표값 기준이면 두 번째 실행이 '변화 없음'으로 0에 멈춘다).
 */
import { useEffect, useRef, useState } from 'react'

import { motionOff } from './motion'

interface Props {
  value: number
  decimals?: number
  duration?: number
  /** 표기 접미(%, 개 등) — 숫자와 같은 톤으로 뒤에 붙는다 */
  suffix?: string
  /** 호버 설명(title) — "이 숫자가 뭘 세는지"를 쉬운 말로 */
  tip?: string
}

export function CountUp({ value, decimals = 0, duration = 800, suffix = '', tip }: Props) {
  const [display, setDisplay] = useState(() => (motionOff() ? value : 0))
  const [flash, setFlash] = useState(false)
  const displayRef = useRef(motionOff() ? value : 0)
  const settledOnce = useRef(false) // 첫 도달 이후의 변경에만 플래시

  useEffect(() => {
    if (motionOff()) {
      displayRef.current = value
      setDisplay(value)
      return
    }
    const from = displayRef.current
    if (from === value) {
      settledOnce.current = true
      return
    }
    let flashTimer: ReturnType<typeof setTimeout> | undefined
    if (settledOnce.current) {
      setFlash(true)
      flashTimer = setTimeout(() => setFlash(false), 900)
    }
    const t0 = performance.now()
    let raf = 0
    const tick = (now: number) => {
      const p = Math.min(1, (now - t0) / duration)
      const eased = 1 - (1 - p) ** 3
      const next = from + (value - from) * eased
      displayRef.current = next
      setDisplay(next)
      if (p < 1) {
        raf = requestAnimationFrame(tick)
      } else {
        settledOnce.current = true
      }
    }
    raf = requestAnimationFrame(tick)
    return () => {
      cancelAnimationFrame(raf)
      if (flashTimer) clearTimeout(flashTimer)
    }
  }, [value, duration])

  return (
    <span className={`viz-num${flash ? ' viz-num-flash' : ''}`} title={tip}>
      {display.toLocaleString('ko-KR', {
        minimumFractionDigits: decimals,
        maximumFractionDigits: decimals,
      })}
      {suffix}
    </span>
  )
}
