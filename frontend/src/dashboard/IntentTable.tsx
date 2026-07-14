/**
 * F. 의도별 세부 — 63행: 시험(등록/대기)·공부·GOLD·예시·정확도를 한 줄에.
 *
 * 정직성: 정확도 null='—'(측정 전, 0 아님). 하한 갭은 CRITICAL에만 표시(비critical엔 없음).
 * 식별은 region 색 점 + 한글 라벨 병행(색 단독 금지).
 */
import { useMemo, useState } from 'react'

import type { Dashboard, IntentRow } from '../api/dashboard'
import { REGION_BY_ID, type RegionId } from '../brain3d/regions'
import { labelOf } from '../panels/intentLabels'

function sortRows(rows: IntentRow[]): IntentRow[] {
  // CRITICAL 먼저(갭 큰 순 — 다음 할 일이 위로), 나머지는 region → 의도명
  return [...rows].sort((a, b) => {
    if (a.is_critical !== b.is_critical) return a.is_critical ? -1 : 1
    if (a.is_critical && b.is_critical) return (b.gap_to_floor ?? 0) - (a.gap_to_floor ?? 0)
    return a.region === b.region
      ? a.intent_id.localeCompare(b.intent_id)
      : a.region.localeCompare(b.region)
  })
}

export function IntentTable({ data }: { data: Dashboard }) {
  const [expanded, setExpanded] = useState(false)
  const rows = useMemo(() => sortRows(data.intents), [data.intents])
  const visible = expanded ? rows : rows.slice(0, 12)

  return (
    <section className="dash-card" aria-label="의도별 세부">
      <h2 className="dash-section-title dash-section-title-inset">
        INTENTS <span>의도별 세부 — {data.intents.length}개 과목의 현재</span>
      </h2>
      <div className="dash-table-scroll">
        <table className="help-table dash-table">
          <thead>
            <tr>
              <th>의도</th>
              <th>시험 등록</th>
              <th>검수 중</th>
              <th>공부</th>
              <th>GOLD</th>
              <th>예문</th>
              <th>정확도</th>
            </tr>
          </thead>
          <tbody>
            {visible.map((r) => {
              const region = REGION_BY_ID[r.region as RegionId]
              return (
                <tr key={r.intent_id}>
                  <td>
                    <span
                      className="dash-region-dot"
                      style={{ background: region?.color ?? 'var(--muted)' }}
                      aria-hidden
                    />
                    {labelOf(r.intent_id)}
                    {r.is_critical && (
                      <span
                        className="dash-chip dash-chip-danger dash-chip-xs"
                        title={
                          '틀리면 되돌릴 수 없는 CRITICAL 의도예요 — 학부모 전송·출결 기재·' +
                          '자료 삭제처럼 실행되면 회수가 안 돼요. 그래서 안전 게이트가 이 ' +
                          `의도에만 시험 ${data.config.critical_surface_min_items}문항과 ` +
                          '오발률 기준을 요구합니다.'
                        }
                      >
                        위험
                      </span>
                    )}
                  </td>
                  <td>
                    {r.exam_registered}
                    {/* 하한 갭은 CRITICAL에만 존재 — payload config 원천 하한 대비 */}
                    {r.gap_to_floor != null && r.gap_to_floor > 0 && (
                      <span
                        className="dash-gap"
                        title={
                          `안전 게이트 하한 ${data.config.critical_surface_min_items}문항까지 ` +
                          `${r.gap_to_floor}문항 남았어요 — 채우면 이 의도의 안전 판정이 시작돼요.`
                        }
                      >
                        {' '}
                        (-{r.gap_to_floor})
                      </span>
                    )}
                  </td>
                  <td>{r.exam_pending}</td>
                  <td>{r.train}</td>
                  <td>{r.gold}</td>
                  <td>{r.positive_examples}</td>
                  <td>
                    {r.heldout_accuracy == null
                      ? '—'
                      : `${(r.heldout_accuracy * 100).toFixed(0)}%`}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
      <div className="dash-actions">
        <button type="button" className="dash-btn" onClick={() => setExpanded((v) => !v)}>
          {expanded ? '접기' : `전체 ${rows.length}개 보기`}
        </button>
        <span className="dash-card-sub">
          '—'는 아직 안 잰 것(0% 아님) · 위험 의도의 (-n)은 게이트 하한{' '}
          {data.config.critical_surface_min_items}문항까지 남은 수
        </span>
      </div>
    </section>
  )
}
