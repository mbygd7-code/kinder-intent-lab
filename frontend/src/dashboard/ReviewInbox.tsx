/**
 * E. 검수함 — 시험지 후보 배치의 상태를 보여주고, 수정은 기존 검수 모달로 연결한다.
 *
 * REGISTERED(등록·동결)에는 어떤 수정 affordance도 없다 — KTIB 동결(§8-2). 고지 문구로 명시.
 */
import type { Dashboard } from '../api/dashboard'
import { useBrainStore } from '../brain3d/store'

const STATUS_KO: Record<string, string> = {
  AWAITING_SECOND: '2차 검수 대기',
  SECOND_DONE: '검수 완료 · 등록 가능',
  REGISTERED: '등록됨 · 동결',
}

export function ReviewInbox({ data }: { data: Dashboard }) {
  const openReview = useBrainStore((s) => s.openReview)
  const batches = data.review_inbox

  return (
    <section className="dash-card" aria-label="검수함">
      <h2 className="dash-section-title dash-section-title-inset">
        REVIEW <span>검수함 — 시험지 후보</span>
      </h2>
      {batches.length === 0 ? (
        <div className="dash-empty">
          <p className="dash-card-sub">
            검수 대기 중인 배치가 없어요 — 웹에서 문항을 작성하면 여기 쌓입니다.
          </p>
        </div>
      ) : (
        <table className="help-table dash-table">
          <thead>
            <tr>
              <th>작성자</th>
              <th>문항</th>
              <th>일치도</th>
              <th>상태</th>
            </tr>
          </thead>
          <tbody>
            {batches.map((b) => (
              <tr
                key={b.batch_id}
                className={b.status === 'REGISTERED' ? 'dash-row-frozen' : 'dash-row-click'}
                onClick={b.status === 'REGISTERED' ? undefined : openReview}
              >
                <td>{b.created_by}</td>
                <td>{b.item_count}</td>
                <td>{b.agreement_kappa == null ? '—' : b.agreement_kappa.toFixed(2)}</td>
                <td>{STATUS_KO[b.status] ?? b.status}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      <div className="dash-actions">
        <button type="button" className="dash-btn dash-btn-primary" onClick={openReview}>
          📄 검수하러 가기
        </button>
      </div>
      <p className="dash-empty-note">
        🔒 등록된 시험지는 <strong>동결</strong>되어 수정할 수 없어요 — 보완은 새 문항 배치로만
        (검수 전 단계에서만 수정 가능).
      </p>
    </section>
  )
}
