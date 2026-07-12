/**
 * 인코딩 범례 — 화면의 모든 시각 채널이 어떤 실데이터인지.
 *
 * 2026-07-12 레이아웃 재정비: 상시 HUD 카드 → 하단 뷰 독의 팝오버 콘텐츠로.
 * 접기/펼치기 상태는 독(BrainScreen dockOpen)이 소유하므로 여기는 순수 카드다.
 * "어두운 게 정상" 상태줄은 톱바 점수 캡션(App)으로 이동 — 항상 보이는 자리가 맞다.
 */

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
  return (
    <div className="persona-card legend-card">
      <div className="persona-head">
        <span className="persona-title">그림 읽는 법</span>
      </div>
      <ul className="legend-rows">
        {ROWS.map(([key, desc]) => (
          <li key={key} className="legend-row">
            <strong className="legend-key">{key}</strong>
            <span>{desc}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}
