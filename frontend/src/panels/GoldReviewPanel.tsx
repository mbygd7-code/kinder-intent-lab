/**
 * 공부 검수(2인 → GOLD) 웹 플로우 — YAML 검수(run_human_review)의 화면 판 (투트랙 세트 ④).
 *
 * blind 원칙: 발화만 보여준다 — 다른 검수자의 표·집계 제안을 절대 싣지 않는다(앵커링 방지).
 * 흐름: 이름 입력 → 발화별로 의도 검색·선택(또는 폐기·건너뛰기) → 표 저장 →
 *       두 사람 표가 모이면 [일치분 GOLD 확정] → 서버 유일문이 kappa·만장일치 판정 →
 *       확정 시 대표 예문 자동 생성(backfill 체인) 결과 표시.
 * 정직성: 결과 수치·거부 사유는 백엔드 응답 그대로. 프론트는 승격 규칙을 판정하지 않는다.
 */
import { useEffect, useMemo, useRef, useState } from 'react'

import {
  applyReview,
  fetchReviewQueue,
  fetchReviewStatus,
  postReviewVote,
  type ReviewQueue,
  type ReviewStatus,
} from '../api/review'
import { parseCsv } from './csv'
import { INTENT_LABEL_KO, labelOf } from './intentLabels'
import { loadIntentCorpus, rankIntents, type IntentCorpus } from './intentRecommend'

const PAGE = 6 // 추천 한 페이지 크기 — [더 보기]가 이만큼씩 늘린다

interface Props {
  onClose: () => void
  onApplied: () => void // GOLD 확정 성공 시 — 대시보드 수치 재조회(bumpReload)
}

export function GoldReviewPanel({ onClose, onApplied }: Props) {
  const [reviewer, setReviewer] = useState('')
  const [queue, setQueue] = useState<ReviewQueue | null>(null)
  const [idx, setIdx] = useState(0)
  const [query, setQuery] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [status, setStatus] = useState<ReviewStatus | null>(null)
  const [approver, setApprover] = useState('')
  const [applied, setApplied] = useState<string | null>(null)
  // 추천 코퍼스(정적 예문 사전) — blind 유지: 뇌·집계·타인 표가 아니라 글자 유사도만.
  const [corpus, setCorpus] = useState<IntentCorpus | null>(null)
  const [shown, setShown] = useState(PAGE)
  const listRef = useRef<HTMLDivElement>(null) // 추천 스크롤 컨테이너 — 발화 넘어가면 맨 위로

  useEffect(() => {
    // scrollTo는 jsdom에 없다 — scrollTop 할당이 브라우저·테스트 양쪽에서 안전
    if (listRef.current) listRef.current.scrollTop = 0
  }, [idx])

  useEffect(() => {
    const ctrl = new AbortController()
    void loadIntentCorpus(parseCsv, ctrl.signal).then(setCorpus)
    return () => ctrl.abort()
  }, [])

  const loadStatus = () =>
    fetchReviewStatus()
      .then(setStatus)
      .catch(() => {
        /* 상태는 부가 정보 — 실패해도 검수는 계속 */
      })
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => void loadStatus(), [])

  const start = async () => {
    if (!reviewer.trim()) {
      setError('검수자 이름을 입력해주세요.')
      return
    }
    setBusy(true)
    setError(null)
    try {
      setQueue(await fetchReviewQueue(reviewer.trim()))
      setIdx(0)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const current = queue && idx < queue.items.length ? queue.items[idx] : null

  // 발화별 추천 랭킹(전체 70개 — 더보기로 끝까지 도달 가능). 코퍼스 미로드면 null.
  const ranked = useMemo(
    () => (current && corpus ? rankIntents(current.teacher_prompt, corpus) : null),
    [current, corpus],
  )

  const searching = query.trim().length > 0
  const options = useMemo(() => {
    const q = query.trim().toLowerCase()
    const ids = Object.keys(INTENT_LABEL_KO)
    if (q) {
      // 검색은 전체 일치를 다 준다 — 목록이 길어도 스크롤로 계속 볼 수 있다(최대 70)
      return ids.filter((id) => id.toLowerCase().includes(q) || labelOf(id).toLowerCase().includes(q))
    }
    if (ranked) return ranked.slice(0, shown) // 검색 없이 바로 고르는 추천 모드
    return ids.slice(0, 8)
  }, [query, ranked, shown])

  const vote = async (intent: string | null) => {
    if (!queue || !current) return
    setBusy(true)
    setError(null)
    try {
      await postReviewVote({
        reviewer: queue.reviewer,
        episode_id: current.episode_id,
        chosen_intent: intent,
      })
      setQuery('')
      setShown(PAGE) // 다음 발화는 추천 첫 페이지부터
      setIdx((i) => i + 1)
      void loadStatus()
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  const apply = async () => {
    if (!approver.trim()) {
      setError('승인자(검수 총괄) 이름을 입력해주세요.')
      return
    }
    setBusy(true)
    setError(null)
    setApplied(null)
    try {
      const r = await applyReview(approver.trim())
      setApplied(`✓ ${r.message}${r.kappa != null ? ` · 일치도 kappa ${r.kappa.toFixed(2)}` : ''}`)
      onApplied()
      void loadStatus()
      // 확정된 것들이 큐에서 빠졌다 — 목록 갱신
      if (queue) setQueue(await fetchReviewQueue(queue.reviewer))
      setIdx(0)
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="gym-backdrop" role="dialog" aria-label="공부 검수">
      <div className="gym-modal">
        <div className="gym-head">
          <strong className="gym-title">🔍 공부 검수 — 두 사람이 맞으면 정답(GOLD)</strong>
          <button type="button" className="gym-close" aria-label="닫기" onClick={onClose}>
            ✕
          </button>
        </div>

        {status && (
          <p className="help-note">
            검수 대기 <strong>{status.reviewable_total}</strong>건 · 두 사람 표가 모인 것{' '}
            <strong>{status.ready_total}</strong>건
            {status.reviewers.length > 0 &&
              ' · ' + status.reviewers.map((r) => `${r.name} ${r.votes}표`).join(' · ')}
          </p>
        )}

        {queue == null ? (
          <div className="gold-review-start">
            <p className="help-note">
              발화를 보고 <strong>맞는 의도를 골라주세요</strong>. 다른 검수자의 답은 보이지
              않아요(각자 독립 판단) — <strong>두 사람이 일치한 것만</strong> 정답(GOLD)이 되어
              뇌의 대표 예문이 됩니다.
            </p>
            <label className="help-field">
              검수자 이름
              <input
                className="help-input"
                value={reviewer}
                placeholder="예: 명배영"
                onChange={(e) => setReviewer(e.target.value)}
              />
            </label>
            <button type="button" className="dash-btn dash-btn-primary" disabled={busy} onClick={start}>
              검수 시작
            </button>
          </div>
        ) : current ? (
          <div className="gold-review-item">
            <p className="dash-card-sub">
              {queue.reviewer} · {idx + 1} / {queue.items.length}
              {queue.my_done > 0 && ` (이전에 ${queue.my_done}건 완료)`}
            </p>
            <p className="live-quiz-utterance">"{current.teacher_prompt}"</p>
            {ranked && !searching && (
              <p className="dash-card-sub help-dim">
                🔎 비슷한 예문 순 추천이에요 — 뇌의 판단이 아니라 글자 유사도예요. 없으면
                [더 보기]나 검색으로 찾으세요.
              </p>
            )}
            <div className="live-quiz-search">
              <input
                className="live-quiz-input"
                value={query}
                onChange={(e) => setQuery(e.target.value)}
                placeholder="의도 검색 (추천에 없을 때 — 예: 알림장, 출결)"
              />
              <div
                ref={listRef}
                className="gym-options gold-options-scroll"
                onScroll={(e) => {
                  // 무한 스크롤: 바닥 근처에 닿으면 다음 페이지 자동 로드(추천 모드에서만)
                  if (searching || !ranked || shown >= ranked.length) return
                  const el = e.currentTarget
                  if (el.scrollTop + el.clientHeight >= el.scrollHeight - 48) {
                    setShown((n) => Math.min(n + PAGE, ranked.length))
                  }
                }}
              >
                {options.map((id) => (
                  <button
                    key={id}
                    type="button"
                    className="gym-option"
                    disabled={busy}
                    onClick={() => vote(id)}
                  >
                    {labelOf(id)} <span className="live-quiz-score">{id}</span>
                  </button>
                ))}
                {ranked && !searching && shown < ranked.length && (
                  <button
                    type="button"
                    className="gym-option gym-option-more"
                    disabled={busy}
                    onClick={() => setShown((n) => n + PAGE)}
                  >
                    ⌄ 더 보기 — 스크롤해도 자동으로 이어져요 (남은 {ranked.length - shown}개)
                  </button>
                )}
              </div>
            </div>
            <div className="dash-actions">
              <button type="button" className="dash-btn" disabled={busy} onClick={() => vote(null)}>
                🗑 못 쓰는 발화 (폐기 표)
              </button>
              <button
                type="button"
                className="dash-btn"
                disabled={busy}
                onClick={() => {
                  setQuery('')
                  setShown(PAGE)
                  setIdx((i) => i + 1)
                }}
              >
                건너뛰기
              </button>
            </div>
          </div>
        ) : (
          <div className="gold-review-done">
            <p className="help-note">
              ✅ 내 몫의 검수가 끝났어요. <strong>다른 검수자 한 분</strong>도 끝나면 아래에서
              확정할 수 있어요 — 일치분만 GOLD가 되고, 일치도(kappa)가 낮으면 전체가 반려돼요.
            </p>
            <label className="help-field">
              승인자(검수 총괄) 이름
              <input
                className="help-input"
                value={approver}
                placeholder="예: 원장님"
                onChange={(e) => setApprover(e.target.value)}
              />
            </label>
            <button type="button" className="dash-btn dash-btn-primary" disabled={busy} onClick={apply}>
              ✓ 일치분 GOLD 확정 (대표 예문 자동 생성)
            </button>
          </div>
        )}

        {busy && <p className="help-note">처리 중…</p>}
        {error && <p className="help-upload-err">⚠ {error}</p>}
        {applied && <p className="help-note help-upload-ok">{applied}</p>}
      </div>
    </div>
  )
}
