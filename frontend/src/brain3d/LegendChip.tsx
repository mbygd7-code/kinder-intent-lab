/**
 * 인코딩 범례 — 화면의 모든 시각 채널이 어떤 실데이터인지 (접이식 HUD 카드).
 *
 * 상태줄: live인데 KTIB가 null이면(Arena 미실행) "어두운 게 정상"을 명시 —
 * 미측정 뇌를 고장으로 오독하지 않게 한다(§7-6 Dormant는 실패가 아니다).
 */
import { useState } from 'react'

import { useBrainStore } from './store'

const ROWS: ReadonlyArray<readonly [string, string]> = [
  ['크기', '훈련량 (evidence 총량)'],
  ['밝기', '정확도 — Arena 측정만'],
  ['고리', '평가 대기 (훈련 후 미측정)'],
  ['필드 채도', '영역 훈련량 — 학습될수록 선명·풍성'],
  ['금색 입자', 'GOLD·전문가 근거'],
  ['점선', '혼동 가설 · 실선 깜빡임 = 측정된 혼동'],
  ['바닥 링', '성장 단계 · 외곽 호 = KTIB'],
]

export function LegendChip() {
  const [open, setOpen] = useState(false)
  const ktibGlobal = useBrainStore((s) => s.ktibGlobal)
  const dataSource = useBrainStore((s) => s.dataSource)

  return (
    <div className="persona-card legend-card">
      <div className="persona-head">
        <span className="persona-title">인코딩 범례</span>
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
          훈련 축적 중 · Arena 측정 전 — 뇌가 어두운 것이 정상이에요
        </p>
      )}
    </div>
  )
}
