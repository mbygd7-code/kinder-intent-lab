/**
 * INSIGHT · 애매 발화 — "의도 분류 자체가 현장 인사이트" (직원 의견서 목표②, 투트랙 B′).
 *
 * 원천: GET /v1/observatory/ambiguity-report (읽기 전용 집계 — 어디에도 쓰지 않음).
 * 출처 분리: gym=오픈 전(실험실·직원), live/shadow=오픈 후(실사용 교사) — 11월 이후
 * 같은 카드가 실교사 데이터로 그대로 이어진다. 정직성: 없으면 없다고 말한다.
 * CSV 내려받기는 직원 공유용(전체 원자료 — 분포·교정·분류불능 3섹션).
 */
import { useEffect, useState } from 'react'

import { fetchAmbiguityReport, type AmbiguityReport } from '../api/observatory'
import { useBrainStore } from '../brain3d/store'
import { labelOf } from '../panels/intentLabels'

const SOURCE_KO: Record<string, string> = {
  gym: '오픈 전 · 실험실(직원·전문가)',
  arena: '오픈 전 · 시험 채점 중 추론',
  live: '오픈 후 · 실사용(교사)',
  shadow: '오픈 후 · 섀도(관찰만)',
}

function toCsv(r: AmbiguityReport): string {
  const esc = (v: unknown) => `"${String(v ?? '').replaceAll('"', '""')}"`
  const lines: string[] = []
  lines.push('[애매 의도 분포]', '출처,의도 id,의도(한글),건수')
  for (const s of r.sources)
    for (const t of s.top_ambiguous_intents)
      lines.push([esc(s.source), esc(t.intent_id), esc(labelOf(t.intent_id)), t.count].join(','))
  lines.push('', '[사람 교정 사례]', '발화,사람 정답,뇌 추측,출처 채널,시각')
  for (const c of r.corrections)
    lines.push(
      [esc(c.utterance), esc(c.chosen), esc(c.guessed), esc(c.origin_channel), esc(c.created_at)].join(','),
    )
  lines.push('', '[분류 불능(아틀라스 대기)]', '발화,상태,시각')
  for (const u of r.unclassified)
    lines.push([esc(u.utterance), esc(u.status), esc(u.created_at)].join(','))
  return '﻿' + lines.join('\n') // BOM — 엑셀에서 한글 안 깨지게
}

export function AmbiguityCard() {
  const reloadNonce = useBrainStore((s) => s.reloadNonce) // 즉석 문답 제출 후 갱신
  const [report, setReport] = useState<AmbiguityReport | null>(null)

  useEffect(() => {
    const ctrl = new AbortController()
    fetchAmbiguityReport(ctrl.signal)
      .then(setReport)
      .catch(() => {
        /* 부가 카드 — 실패해도 대시보드는 그대로(형식 방어 포함) */
      })
    return () => ctrl.abort()
  }, [reloadNonce])

  if (report == null) return null
  const empty =
    report.sources.length === 0 &&
    report.corrections.length === 0 &&
    report.unclassified.length === 0

  const download = () => {
    const blob = new Blob([toCsv(report)], { type: 'text/csv;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = 'ambiguity_report.csv'
    a.click()
    URL.revokeObjectURL(url)
  }

  return (
    <section aria-label="애매 발화 인사이트">
      <div className="dash-section-head">
        <h2 className="dash-section-title">
          INSIGHT <span>애매 발화 — 뇌가 헷갈린 말이 곧 현장 인사이트</span>
        </h2>
        {!empty && (
          <button type="button" className="dash-btn" onClick={download}>
            ⬇ CSV 내려받기
          </button>
        )}
      </div>

      {empty ? (
        <div className="dash-card dash-empty">
          <p className="dash-empty-title">아직 애매 발화 데이터가 없어요</p>
          <p className="dash-card-sub">
            즉석 문답으로 발화를 넣어보면, 뇌가 확신 못 한 말·사람이 고쳐준 말·분류가 안 된
            말이 여기에 모여요 — 어떤 의도의 경계가 흐린지 한눈에 보입니다.
          </p>
        </div>
      ) : (
        <div className="dash-card">
          {report.sources.map((s) => (
            <div key={s.source} className="ambig-source">
              <p className="dash-card-sub">
                <strong>{SOURCE_KO[s.source] ?? s.source}</strong> — 추론 {s.total}건 중{' '}
                <strong>{s.ambiguous}건</strong>이 확신 부족(되묻기권)이었어요.
              </p>
              {s.top_ambiguous_intents.length > 0 && (
                <div className="dash-chip-row">
                  {s.top_ambiguous_intents.slice(0, 5).map((t) => (
                    <span
                      key={t.intent_id}
                      className="dash-chip dash-chip-dim"
                      title={`이 의도로 추측했지만 확신이 낮았던 발화 수 (${t.intent_id})`}
                    >
                      {labelOf(t.intent_id)} {t.count}건
                    </span>
                  ))}
                </div>
              )}
            </div>
          ))}

          {report.corrections.length > 0 && (
            <>
              <p className="dash-card-sub ambig-block-title">
                ✏️ 사람이 고쳐준 말 (최근 {Math.min(report.corrections.length, 3)}건 표시 · 총{' '}
                {report.corrections.length}건)
              </p>
              <ul className="ambig-list">
                {report.corrections.slice(0, 3).map((c, i) => (
                  <li key={i} className="dash-card-sub">
                    "{c.utterance}" — 뇌 추측{' '}
                    <strong>{c.guessed ? labelOf(c.guessed) : '—'}</strong> → 사람 정답{' '}
                    <strong>{labelOf(c.chosen)}</strong>
                  </li>
                ))}
              </ul>
            </>
          )}

          {report.unclassified.length > 0 && (
            <p className="dash-card-sub ambig-block-title">
              🗂 어떤 의도에도 못 넣은 말: <strong>{report.unclassified.length}건</strong> (아틀라스
              확장 대기)
            </p>
          )}
        </div>
      )}
    </section>
  )
}
