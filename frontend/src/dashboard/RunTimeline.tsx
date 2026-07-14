/**
 * C. 성능 & 귀속 — run 타임라인: run별 점수와 "그 사이 들어온 데이터"를 나란히.
 *
 * 정직성: run<2면 귀속을 지어내지 않고 "측정 전" 카드(다음 행동 안내 — empty state 원칙).
 * delta_pp null = 비교 대상 없음('—'), 0.0과 다르다. 유입 증분은 created_at 귀속의 근사임을 표기.
 */
import type { Dashboard, RunPoint } from '../api/dashboard'
import { useBrainStore } from '../brain3d/store'
import { ArenaRunButton } from './ArenaRunButton'
import { RunChart } from './viz/RunChart'

function DeltaBadge({ delta }: { delta: number | null }) {
  if (delta == null)
    return (
      <span
        className="dash-delta dash-dim"
        title="비교할 이전 점수가 없어요 — 0이 아니라 '처음'이라는 뜻이에요."
      >
        첫 채점
      </span>
    )
  const title = '바로 전 채점과 비교해 점수가 얼마나 변했는지예요.'
  if (delta > 0)
    return <span className="dash-delta dash-delta-up" title={title}>▲ +{delta.toFixed(1)}%p 올랐어요</span>
  if (delta < 0)
    return <span className="dash-delta dash-delta-down" title={title}>▼ {delta.toFixed(1)}%p 내렸어요</span>
  return <span className="dash-delta" title={title}>변화 없음</span>
}

/** "7월 14일 19:20" — 코드형 run id 대신 사람이 읽는 시각 라벨 */
function runTime(iso: string): string {
  const d = new Date(iso)
  if (Number.isNaN(d.getTime())) return ''
  return `${d.getMonth() + 1}월 ${d.getDate()}일 ${String(d.getHours()).padStart(2, '0')}:${String(d.getMinutes()).padStart(2, '0')}`
}

function RunRow({ run, seq }: { run: RunPoint; seq: number }) {
  const inflow = run.inflow_since_prev
  return (
    <li className="dash-run-row">
      <div className="dash-run-head">
        {/* run id는 코드 냄새라 감춘다 — 추적이 필요한 운영자는 툴팁으로 */}
        <span className="dash-run-id" title={`기록 번호: ${run.run_id}`}>
          {seq}번째 채점 · {runTime(run.created_at)}
        </span>
        <span
          className="dash-run-acc"
          title={
            run.accuracy == null
              ? '이 채점은 점수가 기록되지 않았어요 — 0이 아니라 미측정이에요.'
              : `${run.item_count ?? '—'}문항 중 뇌가 첫 시도에 맞힌 비율이에요.`
          }
        >
          {run.accuracy == null ? '—' : `${(run.accuracy * 100).toFixed(1)}%`}
        </span>
        <DeltaBadge delta={run.delta_pp} />
      </div>
      <div className="dash-run-detail">
        {inflow ? (
          <span className="dash-card-sub">
            이 채점 전에 새로 들어온 것: 공부 {inflow.train_episodes}건 · 사람검증(GOLD){' '}
            {inflow.gold}건 · 시험문항 {inflow.benchmark_episodes}건
          </span>
        ) : (
          <span className="dash-card-sub dash-dim">첫 채점이에요 — 비교할 이전 점수가 없어요</span>
        )}
        {run.region_regressions.length > 0 && (
          <span
            className="dash-chip dash-chip-warn"
            title="바로 전 채점보다 평균 점수가 내려간 뇌 영역이에요 — 그 영역을 보강하라는 신호예요."
          >
            내려간 영역: {run.region_regressions.join(', ')}
          </span>
        )}
        {run.critical_worse.length > 0 && (
          <span
            className="dash-chip dash-chip-danger"
            title="바로 전 채점보다 점수가 떨어진 위험 의도(학부모 전송·출결·삭제처럼 되돌릴 수 없는 것) 수예요 — 가장 급한 신호예요."
          >
            위험 의도 나빠짐: {run.critical_worse.length}건
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
      <div className="dash-section-head">
        <h2 className="dash-section-title">
          PERFORMANCE <span>시험 점수 변화 — 무엇을 배워서 얼마나 올랐나</span>
        </h2>
        {perf.runs.length > 0 && <ArenaRunButton />}
      </div>

      {perf.runs.length === 0 ? (
        <div className="dash-card dash-empty dash-has-pop">
          <p className="dash-empty-title">아직 채점 전이에요</p>
          <p className="dash-card-sub">
            시험지 {sb.ktib_registered_total}문항이 준비되어 있어요. 채점을 실행하면 여기에
            첫 점수가 그려지고, 두 번째 채점부터는 "그 사이 배운 것이 점수를 얼마나
            올렸는지"가 나란히 표시돼요.
          </p>
          <div className="dash-actions">
            <button type="button" className="dash-btn dash-btn-primary" onClick={openReview}>
              📄 시험 문항 더 만들기
            </button>
            <ArenaRunButton />
          </div>
        </div>
      ) : (
        <div className="dash-card">
          <div
            className="dash-card-sub dash-axis-note"
            title="공정한 비교를 위해 매번 같은 시험지로 시험을 봐요. 시험지가 바뀌면 새 기준으로 다시 시작돼요."
          >
            채점할 때마다 점수가 점 하나로 찍혀요 — 왼쪽이 처음, 오른쪽이 최근.
            점선({(cfg.first_intent_accuracy_target * 100).toFixed(0)}%)을 넘는 게 목표예요.
          </div>
          <RunChart runs={perf.runs} target={cfg.first_intent_accuracy_target} />
          {!perf.attribution_ready && (
            <p className="dash-empty-note">
              같은 시험지로 <strong>두 번 이상</strong> 채점해야 "무엇 때문에 오르내렸는지"를
              붙일 수 있어요.
            </p>
          )}
          <ul className="dash-run-list">
            {[...perf.runs].reverse().map((r, i) => (
              <RunRow key={r.run_id} run={r} seq={perf.runs.length - i} />
            ))}
          </ul>
        </div>
      )}
    </section>
  )
}
