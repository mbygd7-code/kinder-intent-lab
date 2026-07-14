/**
 * A. 스코어보드 — 골든 시그널 4카드 (실력 / 시험지 / 공부 데이터 / 사람 가르침).
 *
 * 실력 카드의 원천은 store(/brain 응답)다 — 대시보드 API는 실력을 중복 제공하지 않는다.
 * 기준선(게이트 하한·80% 목표)은 전부 payload.config 값 — 하드코딩 금지(절대 규칙 1).
 */
import type { Dashboard } from '../api/dashboard'
import { useBrainStore } from '../brain3d/store'
import { stageWithNumber } from '../panels/terms'
import { CountUp } from './viz/CountUp'
import { RadialGauge } from './viz/RadialGauge'

const CHANNEL_KO: Record<string, string> = {
  FOUNDRY_SYNTHETIC: '컴퓨터 생성',
  FOUNDRY_AUGMENTED: '컴퓨터 변형',
  GYM_HUMAN: '선생님 답',
  EXPERT_AUTHORED: '전문가',
  PRODUCTION_SHADOW: '실서비스',
  OFFICIAL_CORPUS: '공식 자료',
  COMMUNITY_DERIVED: '커뮤니티',
}

export function Scoreboard({ data }: { data: Dashboard }) {
  const ktib = useBrainStore((s) => s.ktibGlobal)
  const brainStage = useBrainStore((s) => s.brainStage)
  const brainStageName = useBrainStore((s) => s.brainStageName)
  const dataSource = useBrainStore((s) => s.dataSource)
  const { scoreboard: sb, config: cfg } = data
  const stageLabel = stageWithNumber(brainStage, brainStageName)
  const humanTotal = Object.values(sb.human_evidence).reduce((a, b) => a + b, 0)

  return (
    <section className="dash-grid dash-grid-4" aria-label="핵심 지표">
      {/* 실력 — /brain(store) 원천. 미측정 '—'는 0이 아니다 */}
      <article className="dash-card dash-hero-card">
        <header className="dash-card-label">ACCURACY · 실력</header>
        <div className="dash-hero-value">
          {ktib == null ? (
            <span className="viz-num dash-dim">—%</span>
          ) : (
            <CountUp value={ktib * 100} decimals={1} suffix="%" />
          )}
        </div>
        <p className="dash-card-sub">
          목표 {(cfg.first_intent_accuracy_target * 100).toFixed(0)}% ·{' '}
          {ktib == null
            ? dataSource === 'live'
              ? '아직 시험 전'
              : '뇌 상태 미연결'
            : '공식 시험(KTIB) 기준'}
        </p>
        {stageLabel != null && (
          <span className="dash-chip" title="성장 단계 — 시험(채점) 결과로만 바뀌어요">
            {stageLabel}
          </span>
        )}
      </article>

      {/* 시험지 — 등록 문항 + CRITICAL 게이트 진척 */}
      <article className="dash-card">
        <header className="dash-card-label">EXAM · 시험지</header>
        <div className="dash-card-row">
          <div>
            <div className="dash-hero-value">
              <CountUp value={sb.ktib_registered_total} suffix="문항" />
            </div>
            <p className="dash-card-sub">
              검수 중 {sb.ktib_pending_total} ·{' '}
              {sb.current_ktib
                ? `동결 ${sb.current_ktib.version} (${sb.current_ktib.episode_count}문항)`
                : '동결된 시험지 없음'}
            </p>
          </div>
          <div
            className="dash-gauge-wrap"
            title={
              '되돌릴 수 없는 행동(학부모 전송·출결·삭제 등) 의도 ' +
              `${sb.critical_total}개 중 시험 ${cfg.critical_surface_min_items}문항을 채운 수예요. ` +
              '전부 채워야 안전 게이트가 판정을 시작해요.'
            }
          >
            <RadialGauge value={sb.critical_met} max={sb.critical_total} />
            <span className="dash-gauge-caption">
              위험 의도 게이트
              <br />
              의도당 {cfg.critical_surface_min_items}문항
            </span>
          </div>
        </div>
      </article>

      {/* 공부 데이터 */}
      <article className="dash-card">
        <header className="dash-card-label">TRAINING · 공부 데이터</header>
        <div className="dash-hero-value">
          <CountUp value={sb.train_total} suffix="건" />
        </div>
        <p className="dash-card-sub">
          GOLD(2인 검증) {sb.gold_total} · 목표 의도당 {cfg.gold_low_threshold}
        </p>
        <div className="dash-chip-row">
          {Object.entries(sb.channels).map(([ch, n]) => (
            <span key={ch} className="dash-chip dash-chip-dim">
              {CHANNEL_KO[ch] ?? ch} {n.toLocaleString('ko-KR')}
            </span>
          ))}
        </div>
      </article>

      {/* 사람 가르침 */}
      <article className="dash-card">
        <header className="dash-card-label">HUMAN · 사람 가르침</header>
        <div className="dash-hero-value">
          <CountUp value={humanTotal} suffix="건" />
        </div>
        <p className="dash-card-sub">
          사람 확인 {sb.human_evidence.human_confirmed ?? 0} · GOLD{' '}
          {sb.human_evidence.gold ?? 0} · 전문가 {sb.human_evidence.expert ?? 0}
        </p>
        <p className="dash-card-sub">
          검수 대기 배치 <strong>{sb.review_awaiting_batches}</strong>건
        </p>
      </article>
    </section>
  )
}
