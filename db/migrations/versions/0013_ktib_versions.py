"""ktib_versions / ktib_items + arena_runs.run_type — KTIB 격리 벤치마크 (T5.1, §8-2).

- `ktib_versions`: 벤치마크 스냅샷 1개 = 에피소드 집합 + **동결된 extractor 버전**.
  `content_hash`(에피소드 집합 ⊕ extractor 지문)가 UNIQUE라 같은 내용은 재빌드해도 같은 버전이고,
  extractor가 바뀌면 해시가 바뀌어 **새 ktib_version이 강제된다**(§8-2 KTIB extractor 고정 규칙).
- `ktib_items`: 채택 시점의 발화·gold intent·workspace(visual_semantics 포함) 스냅샷.
  에피소드 원본이 나중에 바뀌어도 벤치마크는 흔들리지 않는다(replay 무결성).
- `arena_runs.run_type`: 'brain'(밝기의 원천) vs 'zero_shot_baseline'(§8-2 베이스라인).
  베이스라인 run이 3D 뇌의 밝기·ktib_global로 새지 않도록 물리적으로 분리한다.

Revision ID: 0013
Revises: 0012
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

_UPGRADE = """
CREATE TABLE ktib_versions (
  ktib_version       TEXT PRIMARY KEY,
  seq                INTEGER NOT NULL UNIQUE,
  extractor_versions JSONB NOT NULL,      -- 동결 — replay 무결성 4종의 4번째 축
  episode_count      INTEGER NOT NULL CHECK (episode_count > 0),
  content_hash       TEXT NOT NULL,       -- 에피소드 집합 ⊕ extractor 지문 (재빌드 멱등)
  notes              TEXT,
  created_at         TIMESTAMPTZ DEFAULT now()
);
CREATE UNIQUE INDEX idx_ktib_versions_content ON ktib_versions(content_hash);

CREATE TABLE ktib_items (
  ktib_version       TEXT NOT NULL REFERENCES ktib_versions(ktib_version) ON DELETE CASCADE,
  episode_id         TEXT NOT NULL REFERENCES episodes(episode_id),
  gold_intent        TEXT NOT NULL,
  teacher_prompt     TEXT NOT NULL,       -- 채택 시점 동결
  lang               TEXT NOT NULL,
  workspace_snapshot JSONB,               -- visual_semantics 포함 (없으면 NULL — 지어내지 않음)
  PRIMARY KEY (ktib_version, episode_id)
);
CREATE INDEX idx_ktib_items_version ON ktib_items(ktib_version);

ALTER TABLE arena_runs
  ADD COLUMN run_type TEXT NOT NULL DEFAULT 'brain'
    CHECK (run_type IN ('brain','zero_shot_baseline'));
ALTER TABLE arena_runs
  ADD CONSTRAINT arena_runs_ktib_fk
  FOREIGN KEY (ktib_version) REFERENCES ktib_versions(ktib_version);
CREATE INDEX idx_arena_runs_type_created ON arena_runs(run_type, created_at DESC);
"""

_DOWNGRADE = """
DROP INDEX IF EXISTS idx_arena_runs_type_created;
ALTER TABLE arena_runs DROP CONSTRAINT IF EXISTS arena_runs_ktib_fk;
ALTER TABLE arena_runs DROP COLUMN IF EXISTS run_type;
DROP TABLE IF EXISTS ktib_items CASCADE;
DROP TABLE IF EXISTS ktib_versions CASCADE;
"""


def upgrade() -> None:
    op.get_bind().exec_driver_sql(_UPGRADE)


def downgrade() -> None:
    op.get_bind().exec_driver_sql(_DOWNGRADE)
