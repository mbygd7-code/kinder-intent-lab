/**
 * 인코딩 범례 — 화면의 모든 시각 채널이 어떤 실데이터인지 (접이식 HUD 카드).
 *
 * 상태줄: live인데 KTIB가 null이면(Arena 미실행) "어두운 게 정상"을 명시 —
 * 미측정 뇌를 고장으로 오독하지 않게 한다(§7-6 Dormant는 실패가 아니다).
 */
import { useState } from 'react'

import { useBrainStore } from './store'

const ROWS: ReadonlyArray<readonly [string, string]> = [
  ['점 크기', '공부한 양 — 많이 배울수록 커져요'],
  ['점 밝기', '시험 정답률 — 시험을 봐야만 밝아져요'],
  ['하얀 고리', '공부는 끝, 시험 대기 중'],
  ['영역 색감', '그 영역의 공부량 — 배울수록 선명해져요'],
  ['금색 반짝임', '사람이 직접 확인해 준 근거'],
  ['점선', '헷갈릴 수 있다는 추측 · 깜빡이는 실선 = 시험에서 확인된 헷갈림'],
  ['바닥 원', '뇌의 성장 단계'],
]

export function LegendChip() {
  const [open, setOpen] = useState(false)
  const ktibGlobal = useBrainStore((s) => s.ktibGlobal)
  const dataSource = useBrainStore((s) => s.dataSource)

  return (
    <div className="persona-card legend-card">
      <div className="persona-head">
        <span className="persona-title">그림 읽는 법</span>
        <button
          type="button"
          className="view-toggle persona-toggle"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
        >
          {open ? '접기' : '펼치기'}
        </button>
      </div>
      {open && (
        <ul className="legend-rows">
          {ROWS.map(([key, desc]) => (
            <li key={key} className="legend-row">
              <strong className="legend-key">{key}</strong>
              <span>{desc}</span>
            </li>
          ))}
        </ul>
      )}
      {dataSource === 'live' && ktibGlobal === null && (
        <p className="persona-empty legend-state">
          공부 쌓는 중 · 아직 시험 전 — 뇌가 어두운 게 정상이에요
        </p>
      )}
    </div>
  )
}
