/**
 * C. 성능 & 귀속 — run 타임라인: run별 점수와 "그 사이 들어온 데이터"를 나란히.
 *
 * 정직성: run<2면 귀속을 지어내지 않고 "측정 전" 카드(다음 행동 안내 — empty state 원칙).
 * delta_pp null = 비교 대상 없음('—'), 0.0과 다르다. 유입 증분은 created_at 귀속의 근사임을 표기.
 */
import type { Dashboard, RunPoint } from '../api/dashboard'
import { useBrainStore } from '../brain3d/store'
import { RunChart } from './viz/RunChart'

function DeltaBadge({ delta }: { delta: number | null }) {
  if (delta == null) return <span className="dash-delta dash-dim">— 기준 없음</span>
  if (delta > 0) return <span className="dash-delta dash-delta-up">▲ +{delta.toFixed(1)}pp</span>
  if (delta < 0) return <span className="dash-delta dash-delta-down">▼ {delta.toFixed(1)}pp</span>
  return <span className="dash-delta">± 0.0pp</span>
}

function RunRow({ run }: { run: RunPoint }) {
  const inflow = run.inflow_since_prev
  return (
    <li className="dash-run-row">
      <div className="dash-run-head">
        <span className="dash-run-id">{run.run_id}</span>
        <span className="dash-run-acc">
          {run.accuracy == null ? '—' : `${(run.accuracy * 100).toFixed(1)}%`}
        </span>
        <DeltaBadge delta={run.delta_pp} />
      </div>
      <div className="dash-run-detail">
        {inflow ? (
          <span className="dash-card-sub">
            직전 run 이후 유입: 공부 +{inflow.train_episodes} · GOLD +{inflow.gold} · 시험문항 +
            {inflow.benchmark_episodes}
          </span>
        ) : (
          <span className="dash-card-sub dash-dim">첫 run — 비교 대상 없음</span>
        )}
        {run.region_regressions.length > 0 && (
          <span className="dash-chip dash-chip-warn">
            영역 하락: {run.region_regressions.join(', ')}
          </span>
        )}
        {run.critical_worse.length > 0 && (
          <span className="dash-chip dash-chip-danger">
            위험 의도 악화: {run.critical_worse.length}건
          </span>
        )}
      </div>
    </li>
  )
}

export function RunTimeline({ data }: { data: Dashboard }) {
  const openReview = useBrainStore((s) => s.openReview)
  const { performance: perf, scoreboard: sb, config: cfg } = data

  return (
    <section aria-label="성능과 귀속">
      <h2 className="dash-section-title">
        PERFORMANCE <span>성능 & 귀속 — 무엇이 들어와 무엇이 변했나</span>
      </h2>

      {perf.runs.length === 0 ? (
        <div className="dash-card dash-empty">
          <p className="dash-empty-title">아직 채점 전이에요</p>
          <p className="dash-card-sub">
            시험지 {sb.ktib_registered_total}문항이 준비되어 있어요. 운영자가 채점(Arena)을
            실행하면 여기에 첫 점수가 그려지고, 두 번째 채점부터는 "그 사이 들어온 데이터가
            점수를 어떻게 바꿨는지"가 나란히 표시됩니다.
          </p>
          <div className="dash-actions">
            <button type="button" className="dash-btn dash-btn-primary" onClick={openReview}>
              📄 시험 문항 더 만들기
            </button>
          </div>
        </div>
      ) : (
        <div className="dash-card">
          <div className="dash-card-sub dash-axis-note">
            같은 시험지({perf.axis?.ktib_version}) · 같은 뇌({perf.axis?.model_version}) 축의
            run만 비교합니다 — 유입 증분은 도착 시각 기준 근사예요.
          </div>
          <RunChart runs={perf.runs} target={cfg.first_intent_accuracy_target} />
          {!perf.attribution_ready && (
            <p className="dash-empty-note">
              귀속 측정 전 — 같은 시험지로 <strong>두 번 이상</strong> 채점해야 상승·하락의
              원인을 붙일 수 있어요.
            </p>
          )}
          <ul className="dash-run-list">
            {[...perf.runs].reverse().map((r) => (
              <RunRow key={r.run_id} run={r} />
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
