/**
 * TODO 엔진 — "지금 뭘 하면 목표(96%)에 가장 빨리 가는가"를 실데이터로 판정 (2026-07-17).
 *
 * 파이프라인 순서 그대로 5단계: 시험지(자) → 공부 재료 → 2인 검수(GOLD) → 채점 → 반복 상승.
 * 첫 미완료 단계가 '지금 할 일'(current)이다 — 채점 버튼의 사전판정(대표 예문 0 차단 등)과
 * 같은 신호를 쓰므로, 이 안내대로 진행하면 버튼이 순서대로 켜진다. 수치는 전부 API 실측 —
 * 지어내지 않는다(미연결이면 패널이 정직하게 미연결을 보인다).
 */

export interface TodoInputs {
  examTotal: number        // 등록된 시험 문항 수
  frozen: boolean          // 동결된 시험지(ktib) 존재
  reviewableTotal: number  // 공부 검수 대기(LABEL_CANDIDATE 등)
  readyTotal: number       // 서로 다른 2인의 표가 모인 에피소드 수
  goldTotal: number        // GOLD(2인 일치) 수
  exemplarTotal: number    // 대표 예문 수 — 0이면 채점해도 0%가 예정
  runCount: number         // 채점 실행 횟수
  score: number | null     // 현재 KTIB 점수(0~1) — 미측정 null
  target: number           // 목표(0~1) — config 원천
}

export type TodoAction = 'examWrite' | 'examUpload' | 'liveQuiz' | 'goldReview' | 'arena'
export type TodoState = 'done' | 'current' | 'locked'

export interface TodoStep {
  key: string
  title: string
  detail: string // 실측 수치 요약
  why: string    // 이걸 하면 뭐가 좋아지는가
  actions: TodoAction[]
  state: TodoState
}

const pct = (v: number) => `${(v * 100).toFixed(1)}%`

export function computeTodoSteps(i: TodoInputs): TodoStep[] {
  const defs: Array<Omit<TodoStep, 'state'> & { done: boolean }> = [
    {
      key: 'exam',
      title: '시험지 만들기 (실력을 재는 자)',
      detail: `등록 ${i.examTotal}문항 · ${i.frozen ? '동결 완료' : '아직 동결 전'}`,
      why: '시험지가 있어야 점수를 잴 수 있어요 — 자(척도)가 없으면 뇌가 늘어도 증명할 방법이 없어요.',
      actions: ['examWrite', 'examUpload'],
      done: i.frozen && i.examTotal > 0,
    },
    {
      key: 'material',
      title: '공부 재료 모으기 (검수할 발화)',
      detail: `검수 대기 ${i.reviewableTotal}건 (대량 재료는 운영자 증산으로 자동 유입돼요)`,
      why: '진짜 교사 말투 발화가 쌓여야 다음 단계(2인 검수)가 굴러가요 — 즉석 문답 한 건 한 건이 재료예요.',
      actions: ['liveQuiz'],
      done: i.reviewableTotal > 0 || i.goldTotal > 0,
    },
    {
      key: 'review',
      title: '공부 검수 — 두 사람이 정답 확정 (GOLD)',
      detail: `대기 ${i.reviewableTotal}건 · 두 사람 표 모임 ${i.readyTotal}건 · GOLD ${i.goldTotal}건`,
      why: '두 사람이 일치한 정답(GOLD)이 뇌의 대표 예문이 돼요 — 그 순간 채점 버튼이 켜져요. 지금 0%인 이유가 바로 대표 예문 0개예요.',
      actions: ['goldReview'],
      done: i.goldTotal > 0 && i.exemplarTotal > 0,
    },
    {
      key: 'arena',
      title: '채점 실행 — 첫 진짜 점수',
      detail: `채점 ${i.runCount}회 · 대표 예문 ${i.exemplarTotal}개`,
      why: '첫 실제 점수가 그려지고 3D 뇌에 불이 들어와요 — 이후 모든 개선이 이 점수로 증명돼요.',
      actions: ['arena'],
      done: i.runCount > 0 && i.score != null && i.score > 0,
    },
    {
      key: 'improve',
      title: `반복해서 올리기 — 목표 ${pct(i.target)}`,
      detail: i.score == null ? '아직 점수 없음' : `현재 ${pct(i.score)} → 목표 ${pct(i.target)}`,
      why: '공부(즉석 문답) → 검수(GOLD) → 채점의 사이클을 돌 때마다 점수가 올라요 — 이 반복이 목표 달성의 유일한 길이에요.',
      actions: ['liveQuiz', 'goldReview', 'arena'],
      done: i.score != null && i.score >= i.target,
    },
  ]

  // 첫 미완료 = current, 그 앞은 done, 그 뒤는 locked(순서를 건너뛰지 않게)
  let currentSeen = false
  return defs.map((d) => {
    let state: TodoState
    if (d.done && !currentSeen) state = 'done'
    else if (!currentSeen) {
      state = 'current'
      currentSeen = true
    } else state = 'locked'
    const { done: _done, ...rest } = d
    return { ...rest, state }
  })
}
