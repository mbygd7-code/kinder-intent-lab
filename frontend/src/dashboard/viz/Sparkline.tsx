/**
 * 7일 유입 스파크라인 — 단일 시리즈 미니 라인 (dataviz: 단일 시리즈는 범례 불필요, 제목이 명명).
 *
 * 모션: pathLength=1 트릭으로 stroke draw-in(1s) + 마지막 점 펄스.
 * 정직성: 전부 0(유입 없음)이면 평평한 점선 + 모션 없음 — 없는 유입을 살아있게 위장하지 않는다.
 */
import { motionOff } from './motion'

interface Props {
  data: number[]
  label: string
  color?: string
  width?: number
  height?: number
}

export function Sparkline({ data, label, color = 'var(--accent)', width = 132, height = 36 }: Props) {
  const pad = 4
  const n = Math.max(data.length, 2)
  const max = Math.max(...data, 1)
  const x = (i: number) => pad + (i * (width - pad * 2)) / (n - 1)
  const y = (v: number) => height - pad - (v / max) * (height - pad * 2)
  const empty = data.every((v) => v === 0)
  const animate = !empty && !motionOff()

  if (empty) {
    return (
      <svg className="viz-spark" width={width} height={height} role="img" aria-label={`${label} — 최근 유입 없음`}>
        <line
          x1={pad} y1={height / 2} x2={width - pad} y2={height / 2}
          stroke="var(--muted)" strokeWidth="1.5" strokeDasharray="2 4" opacity="0.55"
        />
      </svg>
    )
  }

  const points = data.map((v, i) => `${x(i)},${y(v)}`).join(' ')
  const last = data.length - 1
  return (
    <svg className="viz-spark" width={width} height={height} role="img" aria-label={`${label} — 최근 ${data.length}일 유입`}>
      <title>{`${label}: ${data.join(', ')}`}</title>
      <polyline
        className={animate ? 'viz-draw' : undefined}
        points={points}
        pathLength={1}
        fill="none"
        stroke={color}
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <circle
        className={animate ? 'viz-dot-pulse' : undefined}
        cx={x(last)} cy={y(data[last])} r="3" fill={color}
      />
    </svg>
  )
}
