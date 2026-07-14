/**
 * run 타임라인 차트 — 채점 run별 정확도 스텝 라인 + 80% 목표선 (단일 시리즈·단일 축).
 *
 * dataviz 규칙: 목표선은 중립 점선, 하락 세그먼트는 status 색(serious) + 화면의 델타 배지가
 * 텍스트로 병기(색 단독 금지). 측정 없는 run(accuracy null)은 점을 그리지 않는다 — 지어내지 않음.
 */
import type { RunPoint } from '../../api/dashboard'
import { motionOff } from './motion'

interface Props {
  runs: RunPoint[]
  target: number // config.first_intent_accuracy_target — payload 원천 (하드코딩 금지)
  width?: number
  height?: number
}

const DOWN = '#fb7185' // status(serious) — 하락 세그먼트 전용, 시리즈 색으로 재사용 금지

export function RunChart({ runs, target, width = 560, height = 150 }: Props) {
  const pad = { l: 44, r: 16, t: 14, b: 22 }
  const measured = runs.filter((r) => r.accuracy != null)
  const n = Math.max(runs.length, 2)
  const x = (i: number) => pad.l + (i * (width - pad.l - pad.r)) / (n - 1)
  // y 스케일은 0~1 고정 + 목표선 — run 간 비교가 과장되지 않게(제로 베이스라인)
  const y = (v: number) => pad.t + (1 - v) * (height - pad.t - pad.b)
  const animate = !motionOff()

  const pts = runs
    .map((r, i) => (r.accuracy == null ? null : `${x(i)},${y(r.accuracy)}`))
    .filter((p): p is string => p != null)

  return (
    <svg className="viz-runchart" width={width} height={height} role="img"
         aria-label={`채점 run ${measured.length}개 정확도 추이 (목표 ${(target * 100).toFixed(0)}%)`}>
      {/* 눈금 — 0/50/100% (recessive) */}
      {[0, 0.5, 1].map((v) => (
        <g key={v}>
          <line x1={pad.l} y1={y(v)} x2={width - pad.r} y2={y(v)}
                stroke="rgba(148,163,184,0.12)" strokeWidth="1" />
          <text x={pad.l - 8} y={y(v) + 3} textAnchor="end" className="viz-axis-text">
            {(v * 100).toFixed(0)}%
          </text>
        </g>
      ))}
      {/* 목표선 — 중립 점선 + 라벨 */}
      <line x1={pad.l} y1={y(target)} x2={width - pad.r} y2={y(target)}
            stroke="rgba(232,241,255,0.45)" strokeWidth="1.5" strokeDasharray="5 5" />
      <text x={width - pad.r} y={y(target) - 5} textAnchor="end" className="viz-target-text">
        목표 {(target * 100).toFixed(0)}%
      </text>

      {/* 라인 — 하락 세그먼트는 status 색으로 분절 */}
      {runs.map((r, i) => {
        if (i === 0 || r.accuracy == null) return null
        const prev = runs[i - 1]
        if (prev.accuracy == null) return null
        const down = r.accuracy < prev.accuracy
        return (
          <line
            key={r.run_id}
            className={animate ? 'viz-seg' : undefined}
            style={animate ? { animationDelay: `${i * 140}ms` } : undefined}
            x1={x(i - 1)} y1={y(prev.accuracy)} x2={x(i)} y2={y(r.accuracy)}
            stroke={down ? DOWN : 'var(--accent)'} strokeWidth="2" strokeLinecap="round"
          />
        )
      })}

      {/* run 점 + 선택적 직접 라벨(첫·마지막만 — 전부 라벨 금지) */}
      {runs.map((r, i) =>
        r.accuracy == null ? null : (
          <g key={r.run_id}
             className={animate ? 'viz-pt' : undefined}
             style={animate ? { animationDelay: `${i * 140}ms` } : undefined}>
            <circle cx={x(i)} cy={y(r.accuracy)} r="4" fill="var(--bg)"
                    stroke="var(--accent)" strokeWidth="2">
              <title>{`${r.run_id} · ${(r.accuracy * 100).toFixed(1)}% · 문항 ${r.item_count ?? '—'}`}</title>
            </circle>
            {(i === 0 || i === runs.length - 1) && (
              <text x={x(i)} y={y(r.accuracy) - 9} textAnchor="middle" className="viz-pt-label">
                {(r.accuracy * 100).toFixed(1)}%
              </text>
            )}
          </g>
        ),
      )}
      {pts.length === 0 && (
        <text x={width / 2} y={height / 2} textAnchor="middle" className="viz-axis-text">
          측정된 run 없음
        </text>
      )}
    </svg>
  )
}
