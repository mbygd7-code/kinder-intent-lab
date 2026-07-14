/**
 * 대시보드 테스트 픽스처 — 정직한 "빈 운영실" 기본값 + 섹션별 오버라이드.
 * (테스트 전용 — 앱 코드에서 import 금지. 값은 실제 API 기본 형태와 동일 구조.)
 */
import type { Dashboard, Stream } from '../api/dashboard'

export function emptyStream(days = 7): Stream {
  const today = new Date()
  return {
    total: 0,
    last_days: Array.from({ length: days }, (_, k) => {
      const d = new Date(today)
      d.setDate(d.getDate() - (days - 1 - k))
      return { day: d.toISOString().slice(0, 10), count: 0 }
    }),
  }
}

export function makeDashboard(overrides: Partial<Dashboard> = {}): Dashboard {
  return {
    config: {
      critical_surface_min_items: 30,
      gold_low_threshold: 100,
      first_intent_accuracy_target: 0.8,
      min_agreement_kappa: 0.65,
    },
    scoreboard: {
      ktib_registered_total: 0,
      ktib_pending_total: 0,
      critical_met: 0,
      critical_total: 7,
      current_ktib: null,
      train_total: 0,
      gold_total: 0,
      channels: {},
      human_evidence: { human_confirmed: 0, gold: 0, expert: 0 },
      review_awaiting_batches: 0,
    },
    inflow: {
      foundry: emptyStream(),
      human_teaching: emptyStream(),
      exam: emptyStream(),
      shadow: emptyStream(),
    },
    performance: { axis: null, runs: [], attribution_ready: false },
    expansion: {
      intent_count: 63,
      positive_examples_total: 378,
      ontology_version: 'onto-1.1',
      unknown_pool: 0,
      ambiguous: 0,
      atlas_queue_pending: 0,
      ontology_versions: [
        { version: 'onto-1.1', change_type: 'minor', created_at: '2026-07-13T00:00:00Z' },
      ],
    },
    review_inbox: [],
    intents: [
      {
        intent_id: 'op_attendance_record', region: 'OPERATION', is_critical: true,
        exam_registered: 0, exam_pending: 0, gap_to_floor: 30,
        train: 0, gold: 0, positive_examples: 6, heldout_accuracy: null, evidence_total: 0,
      },
      {
        intent_id: 'play_expand', region: 'PLAY', is_critical: false,
        exam_registered: 0, exam_pending: 0, gap_to_floor: null,
        train: 0, gold: 0, positive_examples: 6, heldout_accuracy: null, evidence_total: 0,
      },
    ],
    ...overrides,
  }
}
