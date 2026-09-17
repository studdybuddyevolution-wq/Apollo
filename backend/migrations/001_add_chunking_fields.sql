-- Apollo Phase 7 notebook/retrieval upgrade.
-- The runner executes statements independently so pgvector failures do not
-- prevent the non-vector schema from being applied.

CREATE EXTENSION IF NOT EXISTS vector;

ALTER TABLE apollo_chunks
  ADD COLUMN IF NOT EXISTS chunk_index INTEGER NOT NULL DEFAULT 0;

ALTER TABLE apollo_chunks
  ADD COLUMN IF NOT EXISTS content_type TEXT NOT NULL DEFAULT 'plain';

ALTER TABLE apollo_chunks
  ADD COLUMN IF NOT EXISTS embedding vector(768);

CREATE INDEX IF NOT EXISTS idx_apollo_chunks_embedding
  ON apollo_chunks USING ivfflat (embedding vector_cosine_ops)
  WITH (lists = 100);

CREATE TABLE IF NOT EXISTS apollo_sources (
  id TEXT PRIMARY KEY,
  notebook_id TEXT NOT NULL REFERENCES apollo_notebooks(id) ON DELETE CASCADE,
  name TEXT NOT NULL,
  kind TEXT NOT NULL DEFAULT 'file',
  processing_status TEXT NOT NULL DEFAULT 'pending',
  error_message TEXT,
  created TEXT NOT NULL,
  updated TEXT NOT NULL,
  UNIQUE(notebook_id, name)
);

CREATE TABLE IF NOT EXISTS apollo_source_insights (
  id TEXT PRIMARY KEY,
  notebook_id TEXT NOT NULL REFERENCES apollo_notebooks(id) ON DELETE CASCADE,
  source_name TEXT NOT NULL,
  insight_type TEXT NOT NULL,
  content TEXT NOT NULL,
  model_used TEXT,
  status TEXT NOT NULL DEFAULT 'completed',
  error TEXT,
  created TEXT NOT NULL,
  updated TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS apollo_jobs (
  id TEXT PRIMARY KEY,
  type TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'queued',
  progress INTEGER NOT NULL DEFAULT 0,
  notebook_id TEXT,
  user_id TEXT,
  created_at TEXT NOT NULL,
  started_at TEXT,
  completed_at TEXT,
  error TEXT,
  result_ref TEXT
);

CREATE INDEX IF NOT EXISTS idx_apollo_jobs_notebook ON apollo_jobs(notebook_id);
CREATE INDEX IF NOT EXISTS idx_apollo_sources_notebook ON apollo_sources(notebook_id);
CREATE INDEX IF NOT EXISTS idx_apollo_insights_source ON apollo_source_insights(notebook_id, source_name);
