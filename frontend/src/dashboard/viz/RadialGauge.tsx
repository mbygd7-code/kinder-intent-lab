/**
 * 진척 게이지 — n/max 원호 채움 (게이트 진척 등). pathLength=100 트릭으로 채움 애니메이션.
 *
 * 정직성: 값·목표를 항상 숫자로 병기한다(색·호 단독 금지 — dataviz 직접 라벨 규칙).
 */
import { motionOff } from './motion'

interface Props {
  value: number
  max: number
  size?: number
  color?: string
  /** 중앙 표기 — 기본 "n/max" */
  centerText?: string
}

export function RadialGauge({ value, max, size = 72, color = 'var(--accent)', centerText }: Props) {
  const pct = max > 0 ? Math.min(100, (value / max) * 100) : 0
  const r = size / 2 - 6
  const c = size / 2
  const animate = !motionOff() && pct > 0
  return (
    <svg
      className="viz-gauge"
      width={size}
      height={size}
      role="img"
      aria-label={`진척 ${value}/${max}`}
    >
      <circle cx={c} cy={c} r={r} fill="none" stroke="rgba(148,163,184,0.18)" strokeWidth="5" />
      {pct > 0 && (
        <circle
          className={animate ? 'viz-gauge-fill' : undefined}
          cx={c} cy={c} r={r}
          fill="none"
          stroke={color}
          strokeWidth="5"
          strokeLinecap="round"
          pathLength={100}
          strokeDasharray={`${pct} ${100 - pct}`}
          strokeDashoffset="25"
          style={animate ? ({ '--gauge-pct': pct } as React.CSSProperties) : undefined}
        />
      )}
      <text x={c} y={c + 1} textAnchor="middle" dominantBaseline="middle" className="viz-gauge-text">
        {centerText ?? `${value}/${max}`}
      </text>
    </svg>
  )
}
