/**
 * Gym 오버레이 (§8-1) — 강화하기(§7-4)로 연 세션의 3모드를 플레이하고 응답을 evidence로 적재.
 * 모든 표시 문구는 한국 유아교사 톤 한글, intent는 한글 라벨(intentLabels)로 보여준다.
 *
 * 의도 알아맞히기 / 알맞은 의미 고르기: 발화를 보고 후보 중 의도를 고른다.
 * 바로잡기 연습: 헷갈리기 쉬운 예시 오답(brain_guess)이 표시됨 → 선생님이 알맞은 의도로
 *   바로잡는다. 이 오답은 실제 추론 결과가 아니라 온톨로지 혼동쌍에서 뽑은 **연습용 예시**다
 *   (실측 오인 방지 — NodePanel의 mock 표기 규율과 동일선상).
 *   예시 오답과 같은 걸 고르면 교정이 아니라 다시 시도 → recovery_turns로 기록.
 *
 * 정직성: 제출 결과는 실제 백엔드가 만든 evidence 수를 그대로 보여준다(지어내지 않음).
 */
import { useMemo, useState } from 'react'

import { submitGymSession, type GymItem, type GymResult, type GymSessionStart } from '../api/gym'
import { GYM_MODE_LABEL_KO, labelOf } from './intentLabels'

interface Props {
  session: GymSessionStart
  onClose: () => void
}

export function GymOverlay({ session, onClose }: Props) {
  const { items, mode } = session
  const [idx, setIdx] = useState(0)
  const [results, setResults] = useState<GymResult[]>([])
  const [attempts, setAttempts] = useState(0) // 현재 아이템의 다시 시도 수(바로잡기 연습)
  const [report, setReport] = useState<{ evidence_created: number } | null>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const item: GymItem | undefined = items[idx]
  const done = idx >= items.length
  const wrongGuess = mode === 'correction_drill' ? item?.brain_guess ?? null : null

  const prompt =
    mode === 'choose_right_meaning'
      ? '이 말은 어떤 뜻에 가까울까요?'
      : mode === 'guess_my_intent'
        ? '선생님이라면 이 말을 어떤 의도로 이해하실까요?'
        : '헷갈리기 쉬운 예시 오답이에요. 알맞은 의도로 바로잡아 주세요.'

  const choose = (intent: string) => {
    if (!item) return
    // 바로잡기 연습: 브레인 추측과 같은 걸 고르면 교정 아님 → 다시 시도(recovery_turns++)
    if (mode === 'correction_drill' && intent === wrongGuess) {
      setAttempts((a) => a + 1)
      return
    }
    setResults((r) => [...r, {
      item_id: item.item_id,
      chosen_intent: intent,
      brain_guess: wrongGuess,
      recovery_turns: mode === 'correction_drill' ? attempts + 1 : 0,
    }])
    setAttempts(0)
    setIdx((i) => i + 1)
  }

  const submit = async () => {
    setBusy(true)
    setError(null)
    try {
      const rep = await submitGymSession(session.session_id, results)
      setReport({ evidence_created: rep.evidence_created })
    } catch {
      setError('저장 중 문제가 생겼어요. 잠시 후 다시 시도해 주세요.')
    } finally {
      setBusy(false)
    }
  }

  const progress = useMemo(
    () => `${Math.min(idx + (done ? 0 : 1), items.length)} / ${items.length}`,
    [idx, done, items.length],
  )

  return (
    <div className="gym-backdrop" role="dialog" aria-label="훈련 세션">
      <div className="gym-modal">
        <div className="gym-head">
          <span className="gym-mode">{GYM_MODE_LABEL_KO[mode]}</span>
          {!done && <span className="gym-progress">{progress}</span>}
          <button type="button" className="gym-close" onClick={onClose} aria-label="닫기">✕</button>
        </div>

        {report ? (
          <div className="gym-result">
            <div className="gym-result-num">{report.evidence_created}</div>
            <div className="gym-result-label">개의 학습 근거를 쌓았어요</div>
            <p className="gym-result-note">
              선생님이 달아 주신 의도가 브레인 학습 근거로 저장됐어요. 고맙습니다!
            </p>
            <button type="button" className="cta-train" onClick={onClose}>완료</button>
          </div>
        ) : done ? (
          <div className="gym-submit">
            <p>{results.length}개 답변이 준비됐어요. 제출하면 브레인 학습에 쓰입니다.</p>
            {error && <p className="gym-error">{error}</p>}
            <button type="button" className="cta-train" disabled={busy} onClick={submit}>
              {busy ? '저장 중…' : '제출하기'}
            </button>
          </div>
        ) : item ? (
          <div className="gym-item">
            <div className="gym-prompt">{prompt}</div>
            <div className="gym-utterance">“{item.utterance}”</div>
            {wrongGuess && (
              <div className="gym-wrong">
                <span className="gym-wrong-tag">연습용 예시</span>
                헷갈리기 쉬운 오답: <strong>{labelOf(wrongGuess)}</strong>
                {attempts > 0 && <span className="gym-retry"> · 다시 시도 {attempts}번</span>}
              </div>
            )}
            <div className="gym-options">
              {item.candidate_intents.map((intent) => (
                <button
                  key={intent}
                  type="button"
                  className={`gym-option${intent === wrongGuess ? ' gym-option-wrong' : ''}`}
                  onClick={() => choose(intent)}
                >
                  {labelOf(intent)}
                </button>
              ))}
            </div>
          </div>
        ) : null}
      </div>
    </div>
  )
}
