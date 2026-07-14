/**
 * 유입 흐름 라인 — 스트림 카드 상단의 "데이터가 흐르는" 표현.
 *
 * 정직성: 최근 창에 유입이 실제로 있을 때만 점이 흐른다 — 유입 0인 스트림은 정지 상태의
 * 어두운 라인(살아있는 척 금지). reduced-motion이면 항상 정지.
 */
import { motionOff } from './motion'

interface Props {
  active: boolean
  color?: string
}

export function FlowDots({ active, color = 'var(--accent)' }: Props) {
  const flowing = active && !motionOff()
  return (
    <div className={`viz-flow${flowing ? ' viz-flow-on' : ''}`} aria-hidden>
      <span className="viz-flow-line" />
      {flowing &&
        [0, 1, 2].map((k) => (
          <span
            key={k}
            className="viz-flow-dot"
            style={{ animationDelay: `${k * 0.6}s`, background: color }}
          />
        ))}
    </div>
  )
}
