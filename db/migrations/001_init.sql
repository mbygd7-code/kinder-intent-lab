-- Kinder Intent Lab — 초기 스키마 (문서 §9)
-- 핵심: episodes의 무결성 CHECK는 절대 규칙 2의 물리적 구현이다. 우회 금지.

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE sources (
  source_id        TEXT PRIMARY KEY,
  source_class     TEXT NOT NULL CHECK (source_class IN ('AUTHORITY','PRACTICE','TEACHER_LANGUAGE')),
  title            TEXT NOT NULL,
  access           TEXT,
  format           TEXT,
  est_volume       TEXT,
  discovery_reason TEXT NOT NULL,
  governance_status TEXT NOT NULL DEFAULT 'PENDING'
    CHECK (governance_status IN ('PENDING','ALLOW','TRANSFORM_ONLY','DENY')),
  governance_meta  JSONB DEFAULT '{}'::jsonb,
  created_at       TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE situation_frames (
  frame_id       TEXT PRIMARY KEY,
  domain         TEXT NOT NULL CHECK (domain IN ('PLAY','OBSERVATION','DOCUMENT','VISUAL','COMMUNICATION','OPERATION','REFLECTION')),
  summary        TEXT NOT NULL,
  participants   JSONB,
  materials      JSONB,
  teacher_concern TEXT,
  source_refs    JSONB,
  extraction_confidence REAL,
  created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE atlas_entries (
  atlas_id        TEXT PRIMARY KEY,
  surface_form    TEXT NOT NULL,
  pattern_cluster TEXT NOT NULL,
  ambiguity_types JSONB NOT NULL,
  possible_intents JSONB NOT NULL,
  resolution_signals JSONB NOT NULL,
  register        JSONB,
  observed_count  INT DEFAULT 0,
  source_class_mix JSONB,
  created_at      TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE canonical_scenarios (
  scenario_id    TEXT PRIMARY KEY,
  frame_id       TEXT REFERENCES situation_frames(frame_id),
  workspace_state JSONB NOT NULL,          -- visual_semantics 포함 (vs-1.0 통제 어휘)
  variation_of   TEXT,
  variation_axis TEXT,
  created_at     TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE episodes (
  episode_id       TEXT PRIMARY KEY,
  ontology_version TEXT NOT NULL,
  lang             TEXT NOT NULL DEFAULT 'ko',
  dataset_split    TEXT NOT NULL CHECK (dataset_split IN ('TRAIN','VALIDATION','TEST','BENCHMARK_HOLDOUT')),
  reliability_tier TEXT NOT NULL DEFAULT 'UNVERIFIED'
    CHECK (reliability_tier IN ('UNVERIFIED','BRONZE','SILVER','GOLD')),
  label_state      TEXT NOT NULL DEFAULT 'UNLABELED'
    CHECK (label_state IN ('UNLABELED','EVIDENCE_ACCUMULATING','AGGREGATION_READY','LABEL_CANDIDATE','REVIEW_REQUIRED','LABELED','REJECTED')),
  origin_channel   TEXT NOT NULL
    CHECK (origin_channel IN ('FOUNDRY_SYNTHETIC','FOUNDRY_AUGMENTED','GYM_HUMAN','EXPERT_AUTHORED','PRODUCTION_SHADOW','OFFICIAL_CORPUS','COMMUNITY_DERIVED')),
  episode_creator_type TEXT NOT NULL
    CHECK (episode_creator_type IN ('FOUNDRY_PIPELINE','GYM_SESSION','SHADOW_CONVERTER','HUMAN_ANNOTATOR')),
  primary_subject_type TEXT NOT NULL CHECK (primary_subject_type IN ('TEACHER','SIMULATED_TEACHER')),
  scenario_id      TEXT REFERENCES canonical_scenarios(scenario_id),
  teacher_prompt   TEXT NOT NULL,
  persona_lens_used TEXT,
  label_distribution JSONB NOT NULL,
  consensus        REAL,
  disagreement_pairs JSONB,
  human_review     JSONB,
  dedup_hash       TEXT,
  prompt_embedding vector(1536),
  created_at       TIMESTAMPTZ DEFAULT now(),
  -- 절대 규칙 2: 벤치마크에 합성 데이터·미검증 라벨 진입 금지
  CONSTRAINT benchmark_integrity CHECK (
    dataset_split <> 'BENCHMARK_HOLDOUT'
    OR (reliability_tier = 'GOLD'
        AND label_state = 'LABELED'
        AND origin_channel NOT IN ('FOUNDRY_SYNTHETIC','FOUNDRY_AUGMENTED'))
  )
);

CREATE TABLE evidence (
  evidence_id   TEXT PRIMARY KEY,
  episode_id    TEXT NOT NULL REFERENCES episodes(episode_id),
  intent_id     TEXT NOT NULL,
  polarity      TEXT NOT NULL CHECK (polarity IN ('supports','refutes')),
  strength      REAL NOT NULL CHECK (strength BETWEEN 0 AND 1),
  evidence_type TEXT NOT NULL
    CHECK (evidence_type IN ('SYNTHETIC_CONSENSUS','WEAK_BEHAVIORAL','DOMAIN_RULE','HUMAN_CORRECTION','HUMAN_CONFIRMATION','EXPERT_REVIEW')),
  actor_type    TEXT NOT NULL
    CHECK (actor_type IN ('LLM_ANALYST','DOMAIN_EXPERT','TEACHER_TRAINER','STAFF_TRAINER','BEHAVIOR_SIGNAL','RULE_ENGINE')),
  trainer_ref   TEXT,
  reliability   REAL,
  adversarial   BOOLEAN NOT NULL DEFAULT FALSE,   -- 절대 규칙 6: 집계 시 분리
  context       JSONB DEFAULT '{}'::jsonb,
  created_at    TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE brain_nodes (
  node_id       TEXT PRIMARY KEY,
  intent_id     TEXT NOT NULL UNIQUE,
  region        TEXT NOT NULL CHECK (region IN ('PLAY','OBSERVATION','DOCUMENT','VISUAL','COMMUNICATION','OPERATION','REFLECTION')),
  definition_ref TEXT NOT NULL,
  exemplar_stats JSONB DEFAULT '{}'::jsonb,
  evidence_stats JSONB DEFAULT '{}'::jsonb,
  heldout_accuracy REAL,             -- 절대 규칙 3: Arena 러너만 UPDATE
  calibration_ece  REAL,
  last_arena_run   TEXT,
  coverage      JSONB DEFAULT '{}'::jsonb,
  pending_evaluation BOOLEAN NOT NULL DEFAULT FALSE,
  created_by_event TEXT NOT NULL     -- 절대 규칙 4: governance_events.event_id 필수
);

CREATE TABLE confusion_edges (
  edge_id       TEXT PRIMARY KEY,
  from_true     TEXT NOT NULL,
  to_predicted  TEXT NOT NULL,
  confusion_rate REAL,
  state         TEXT NOT NULL DEFAULT 'hypothesized' CHECK (state IN ('hypothesized','observed','confirmed')),
  origin        TEXT CHECK (origin IN ('SKEPTIC','CONSENSUS_DISAGREEMENT','GYM_CORRECTION','ARENA_MATRIX')),
  evidence_runs JSONB,
  contrast_exemplars JSONB,
  last_updated  TIMESTAMPTZ DEFAULT now(),
  UNIQUE (from_true, to_predicted)   -- 방향성: (A,B) != (B,A)
);

CREATE TABLE persona_clusters (
  cluster_id   TEXT PRIMARY KEY,
  method       TEXT,
  axes         JSONB,
  member_count INT,
  version      TEXT NOT NULL,
  created_at   TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE population_priors (
  cluster_id  TEXT REFERENCES persona_clusters(cluster_id),
  intent_id   TEXT NOT NULL,
  prior       REAL NOT NULL,
  state_version TEXT NOT NULL,        -- persona_state_version (replay)
  PRIMARY KEY (cluster_id, intent_id, state_version)
);

CREATE TABLE teacher_priors (
  trainer_ref TEXT NOT NULL,
  intent_id   TEXT NOT NULL,
  prior       REAL NOT NULL,
  state_version TEXT NOT NULL,
  updated_at  TIMESTAMPTZ DEFAULT now(),
  PRIMARY KEY (trainer_ref, intent_id, state_version)
);

CREATE TABLE challenge_packs (
  pack_id     TEXT PRIMARY KEY,
  origin      JSONB NOT NULL,
  strategy    JSONB NOT NULL,
  target_edges JSONB,
  items       INT NOT NULL,
  difficulty_curve TEXT,
  persona_mix JSONB,
  delivery_modes JSONB,
  expected_yield JSONB,
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE gym_sessions (
  session_id  TEXT PRIMARY KEY,
  pack_id     TEXT REFERENCES challenge_packs(pack_id),
  trainer_ref TEXT NOT NULL,
  mode        TEXT NOT NULL,
  results     JSONB NOT NULL DEFAULT '[]'::jsonb,
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE brain_versions (
  version     TEXT PRIMARY KEY,
  base        TEXT,
  trigger     TEXT,
  delta       JSONB,
  arena_result JSONB,
  decision    TEXT CHECK (decision IN ('candidate','promote','reject')),
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE arena_runs (
  run_id      TEXT PRIMARY KEY,
  model_version TEXT NOT NULL,
  ontology_version TEXT NOT NULL,
  persona_state_version TEXT NOT NULL,   -- replay 무결성 4종
  extractor_versions JSONB NOT NULL,
  ktib_version TEXT NOT NULL,            -- extractor 재추출 = 새 KTIB 버전
  metrics     JSONB NOT NULL,
  confusion_matrix JSONB,
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE ontology_versions (
  version     TEXT PRIMARY KEY,
  change_type TEXT CHECK (change_type IN ('minor','major')),
  migration_map JSONB,
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE TABLE governance_events (
  event_id    TEXT PRIMARY KEY,
  event_type  TEXT NOT NULL,             -- NODE_CREATE / ONTOLOGY_CHANGE / SOURCE_DECISION / CONFIG_CHANGE ...
  payload     JSONB NOT NULL,
  approved_by TEXT NOT NULL,
  created_at  TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_episodes_split ON episodes(dataset_split);
CREATE INDEX idx_episodes_state ON episodes(label_state);
CREATE INDEX idx_evidence_episode ON evidence(episode_id);
CREATE INDEX idx_evidence_intent ON evidence(intent_id);
