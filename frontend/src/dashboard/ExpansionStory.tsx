/**
 * D. 확장 스토리 — "지금 수가 끝이 아니다"를 실데이터로만 증명 (신뢰 요구의 직접 응답).
 *
 * 원천: 온톨로지(의도·예시 수), UNKNOWN pool, atlas 확장 큐(PENDING), 온톨로지 버전 이력.
 * 과거 수치를 날조하지 않는다 — 버전 행 + 현재 값만. 헤더 수치는 API가 준 intent_count
 * (onto-2.0에서 63→70처럼 자라므로 하드코딩 금지).
 */
import type { Dashboard } from '../api/dashboard'
import { useBrainStore } from '../brain3d/store'
import { CountUp } from './viz/CountUp'

export function ExpansionStory({ data }: { data: Dashboard }) {
  const openIntentCatalog = useBrainStore((s) => s.openIntentCatalog)
  const openSituationSeed = useBrainStore((s) => s.openSituationSeed)
  const e = data.expansion
  const growing = e.unknown_pool + e.atlas_queue_pending

  return (
    <section className="dash-card" aria-label="확장 스토리">
      <h2 className="dash-section-title dash-section-title-inset">
        EXPANSION <span>확장 — {e.intent_count}개가 끝이 아니에요</span>
      </h2>
      <div className="dash-expansion-row">
        <div className="dash-stat">
          <div className="dash-stream-value">
            <CountUp
              value={e.intent_count}
              suffix="개"
              tip={`지금 뇌가 배우는 의도(과목) 수예요 — 사전(${e.ontology_version}) 기준. 아래 후보가 승격되면 늘어나요.`}
            />
          </div>
          <span className="dash-card-sub">현재 배우는 의도</span>
        </div>
        <span className="dash-expansion-plus" aria-hidden>
          +
        </span>
        <div className="dash-stat">
          <div className="dash-stream-value">
            <CountUp
              value={growing}
              suffix="건"
              tip="새 의도(과목)가 될 후보예요 — 뇌가 못 알아들은 발화(미분류)와 즉석 문답의 '새 의도 제안'의 합. 사람 검토·승인을 거쳐야만 과목이 돼요."
            />
          </div>
          <span className="dash-card-sub">
            자라는 중 — 미분류 발화 {e.unknown_pool} · 새 의도 후보 {e.atlas_queue_pending}
          </span>
        </div>
        <div className="dash-stat">
          <div className="dash-stream-value">
            <CountUp
              value={e.positive_examples_total}
              suffix="문장"
              tip="의도마다 '이런 말 = 이 의도'를 보여주는 기준 예문의 총합이에요 — 강화하기 문제의 재료라서, 늘리면 훈련 문제도 늘어나요."
            />
          </div>
          <span className="dash-card-sub">의도별 기준 예문(사전)</span>
        </div>
      </div>

      <div className="dash-version-track">
        {e.ontology_versions.map((v, i) => (
          <span key={v.version} className="dash-version-node">
            <span className={`dash-chip${v.version === e.ontology_version ? '' : ' dash-chip-dim'}`}>
              {v.version}
              {v.change_type ? ` · ${v.change_type}` : ''}
            </span>
            {i < e.ontology_versions.length - 1 && <span className="dash-version-arrow">→</span>}
          </span>
        ))}
        {e.ontology_versions.length === 0 && (
          <span className="dash-card-sub dash-dim">버전 이력 없음</span>
        )}
      </div>
      <p className="dash-card-sub">
        교사들이 못 알아듣는 말을 하면 그 발화가 <strong>미분류 pool</strong>에 쌓이고, 즉석
        문답의 "새 의도 제안"이 <strong>확장 후보 큐</strong>로 갑니다 — 검토를 거쳐 새 의도로
        승격되면 뇌가 배우는 과목이 늘어나요(자동 등록은 없음 · 사람 승인 필수).
      </p>
      <div className="dash-actions">
        <button type="button" className="dash-btn" onClick={openIntentCatalog}>
          🗂 의도 목록 · 수정 제안
        </button>
        <button type="button" className="dash-btn" onClick={openSituationSeed}>
          🖥 화면 씨드 스튜디오
        </button>
      </div>
    </section>
  )
}
