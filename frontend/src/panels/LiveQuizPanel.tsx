/**
 * 즉석 문답(Live Quiz) 오버레이 — 자유 발화 타이핑 → 뇌의 라이브 추측(3~4 후보) → 사람 판정.
 *
 * 판정 경로 (§6-7 [4]~[6]):
 * - 후보에서 선택: 뇌 추측과 일치=확인, 다르면=교정 → 훈련 evidence + pending 링
 * - 목록에 없음: 전체 의도 검색(라벨 자동완성)에서 정답 기록 → 교정(가장 강한 인간 신호)
 * - 진짜 새 의도: atlas 확장 큐 제안 — 노드 자동 생성 없음(규칙 4)
 * - 출제용 토글: 훈련에 쓰지 않고 2차 검수 대기열로만 (§8-2 학습/시험 분리 — 같은 발화는
 *   훈련·시험 중 한쪽에만 간다)
 *
 * 정직성: 결과 화면은 백엔드가 실제로 만든 수치(evidence/큐 크기)만 보여준다. 훈련은
 * 정확도(밝기)를 바꾸지 않는다 — pending 링 안내 문구로 그 구분을 그대로 전달한다(규칙 3).
 */
import { useMemo, useState } from 'react'

import {
  inferLive,
  LiveApiError,
  newFeedbackId,
  submitLiveFeedback,
  type LiveFeedbackReport,
  type LiveInferResult,
  type LivePurpose,
} from '../api/live'
import { useBrainStore } from '../brain3d/store'
import { INTENT_LABEL_KO, labelOf } from './intentLabels'

interface Props {
  onClose: () => void
  /** 훈련 evidence가 실제로 저장된 뒤에만 호출 — 뇌 상태 refetch(§6-7 [6]) */
  onComplete?: () => void
}

type Phase = 'input' | 'inferring' | 'review' | 'saving' | 'done'

const TRAINER_REF = 'TR_local' // NodePanel 훈련 세션과 동일한 로컬 트레이너 식별자

export function LiveQuizPanel({ onClose, onComplete }: Props) {
  const brain = useBrainStore((s) => s.brain)
  const [phase, setPhase] = useState<Phase>('input')
  const [utterance, setUtterance] = useState('')
  const [infer, setInfer] = useState<LiveInferResult | null>(null)
  const [searchOpen, setSearchOpen] = useState(false)
  const [query, setQuery] = useState('')
  const [purpose, setPurpose] = useState<LivePurpose>('training')
  const [report, setReport] = useState<LiveFeedbackReport | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  // 의도 검색 우주: 실데이터(노드 목록)가 있으면 그것을, 없으면 라벨 사전 키를 쓴다(날조 아님)
  const allIntents = useMemo(() => {
    const ids = brain?.nodes?.length
      ? brain.nodes.map((n) => n.intent_id)
      : Object.keys(INTENT_LABEL_KO)
    return [...new Set(ids)].sort()
  }, [brain])

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return allIntents.slice(0, 8)
    return allIntents
      .filter((id) => id.toLowerCase().includes(q) || labelOf(id).toLowerCase().includes(q))
      .slice(0, 8)
  }, [allIntents, query])

  const ask = async () => {
    const text = utterance.trim()
    if (!text) return
    setPhase('inferring')
    setError(null)
    try {
      setInfer(await inferLive(text, TRAINER_REF))
      setPhase('review')
    } catch {
      setError('브레인에게 물어보는 중 문제가 생겼어요. 백엔드 연결을 확인해 주세요.')
      setPhase('input')
    }
  }

  const submit = async (chosen: string | null, suggestNew = false) => {
    if (!infer) return
    setPhase('saving')
    setError(null)
    try {
      const rep = await submitLiveFeedback({
        feedback_id: newFeedbackId(),
        trainer_ref: TRAINER_REF,
        utterance: utterance.trim(),
        chosen_intent: chosen,
        brain_top_intent: infer.top_intent,
        intent_candidates: infer.candidates.map((c) => c.intent_id),
        inference_request_id: infer.request_id, // 감사 연결 — inference_logs의 스냅샷과 잇는다
        suggest_new_intent: suggestNew,
        purpose: suggestNew ? 'training' : purpose, // 새 의도 제안은 큐 등록만 — purpose 무관
      })
      setReport(rep)
      setPhase('done')
      if (rep.kind === 'confirmation' || rep.kind === 'correction') onComplete?.()
    } catch (e) {
      if (e instanceof LiveApiError && e.status === 409) {
        // 정직한 안내: 중복(이미 반영/이미 출제 대기) 또는 학습·시험 오염 차단
        setNotice(e.message)
        setPhase('review')
        return
      }
      setError('저장 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요.')
      setPhase('review')
    }
  }

  const reset = () => {
    setPhase('input')
    setUtterance('')
    setInfer(null)
    setSearchOpen(false)
    setQuery('')
    setPurpose('training')
    setReport(null)
    setNotice(null)
    setError(null)
  }

  const abstained = infer !== null && infer.candidates.length === 0

  return (
    <div className="gym-backdrop" role="dialog" aria-label="즉석 문답">
      <div className="gym-modal">
        <div className="gym-head">
          <span className="gym-mode">즉석 문답</span>
          <button type="button" className="gym-close" onClick={onClose} aria-label="닫기">✕</button>
        </div>

        {phase === 'done' && report ? (
          <div className="gym-result">
            {report.kind === 'benchmark_queued' ? (
              <>
                <div className="gym-result-num">{report.benchmark_queue_size}</div>
                <div className="gym-result-label">문항이 시험 출제 대기열에 있어요</div>
                <p className="gym-result-note">
                  이 문답은 브레인 학습에 쓰이지 않고, 두 번째 검수자가 확인하면
                  시험지(KTIB)에 들어가요. (검수 전에는 시험에 반영되지 않아요)
                </p>
              </>
            ) : report.kind === 'atlas_queued' ? (
              <p className="gym-result-note">
                새 의도 후보로 접수했어요. 검토를 거쳐 승인되면 새 노드가 생겨요 —
                자동으로 만들지는 않아요.
              </p>
            ) : (
              <>
                <div className="gym-result-num">{report.evidence_created ?? 0}</div>
                <div className="gym-result-label">
                  {report.kind === 'confirmation'
                    ? '개의 확인 근거를 쌓았어요 (브레인이 맞혔어요!)'
                    : '개의 교정 근거를 쌓았어요 (브레인이 배웠어요)'}
                </div>
                <p className="gym-result-note">
                  {report.pending_set
                    ? '노드에 검증 대기 링이 켜졌어요 — 정확도(밝기)는 Arena 시험을 통과해야 올라가요.'
                    : '학습 근거로 저장됐어요.'}
                </p>
              </>
            )}
            <div className="gym-options">
              <button type="button" className="cta-train" onClick={reset}>한 번 더</button>
              <button type="button" className="view-toggle" onClick={onClose}>완료</button>
            </div>
          </div>
        ) : phase === 'input' || phase === 'inferring' ? (
          <div className="gym-item">
            <div className="gym-prompt">선생님이 실제로 쓰는 말로 물어보세요</div>
            <textarea
              className="live-quiz-input"
              value={utterance}
              onChange={(e) => setUtterance(e.target.value)}
              placeholder="예) 아까 찍은 블록놀이 사진 애들별로 정리해줘"
              rows={3}
              disabled={phase === 'inferring'}
            />
            {error && <p className="gym-error">{error}</p>}
            <button
              type="button"
              className="cta-train"
              disabled={phase === 'inferring' || !utterance.trim()}
              onClick={ask}
            >
              {phase === 'inferring' ? '브레인이 생각 중…' : '브레인에게 물어보기'}
            </button>
          </div>
        ) : infer ? (
          <div className="gym-item">
            <div className="gym-utterance">“{utterance.trim()}”</div>
            <div className="gym-prompt">
              {abstained
                ? '브레인이 아직 이 말을 몰라요 — 정답을 알려주시면 배웁니다'
                : '브레인의 추측이에요. 맞는 의도를 골라 주세요'}
            </div>

            {!abstained && (
              <div className="gym-options">
                {infer.candidates.map((c) => (
                  <button
                    key={c.intent_id}
                    type="button"
                    className="gym-option"
                    disabled={phase === 'saving'}
                    onClick={() => submit(c.intent_id)}
                  >
                    {labelOf(c.intent_id)}
                    {c.intent_id === infer.top_intent && (
                      <span className="live-quiz-top-badge"> ★ 브레인의 답</span>
                    )}
                    <span className="live-quiz-score"> {Math.round(c.score * 100)}%</span>
                  </button>
                ))}
              </div>
            )}

            {!searchOpen ? (
              <button
                type="button"
                className="view-toggle"
                disabled={phase === 'saving'}
                onClick={() => setSearchOpen(true)}
              >
                {abstained ? '정답 의도 찾기' : '목록에 없어요 — 직접 찾기'}
              </button>
            ) : (
              <div className="live-quiz-search">
                <input
                  className="live-quiz-input"
                  value={query}
                  onChange={(e) => setQuery(e.target.value)}
                  placeholder="의도 이름 검색 (예: 알림장)"
                />
                <div className="gym-options">
                  {filtered.map((id) => (
                    <button
                      key={id}
                      type="button"
                      className="gym-option"
                      disabled={phase === 'saving'}
                      onClick={() => submit(id)}
                    >
                      {labelOf(id)} <span className="live-quiz-score">{id}</span>
                    </button>
                  ))}
                  {filtered.length === 0 && (
                    <button
                      type="button"
                      className="gym-option"
                      disabled={phase === 'saving'}
                      onClick={() => submit(null, true)}
                    >
                      딱 맞는 의도가 없어요 — 새 의도로 제안하기
                    </button>
                  )}
                </div>
              </div>
            )}

            <label className="live-quiz-purpose">
              <input
                type="checkbox"
                checked={purpose === 'benchmark'}
                disabled={phase === 'saving'}
                onChange={(e) => setPurpose(e.target.checked ? 'benchmark' : 'training')}
              />
              시험 문제로 출제 (학습에 쓰지 않고 2차 검수 후 시험지로)
            </label>

            {notice && <p className="gym-error">{notice}</p>}
            {error && <p className="gym-error">{error}</p>}
            {phase === 'saving' && <p className="gym-result-note">저장 중…</p>}
          </div>
        ) : null}
      </div>
    </div>
  )
}
