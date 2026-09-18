-- Apollo Phase 7 source lifecycle and workspace hardening.
-- Additive and safe to re-run.

ALTER TABLE apollo_sources
  ADD COLUMN IF NOT EXISTS source_url TEXT;

CREATE INDEX IF NOT EXISTS idx_apollo_sources_url
  ON apollo_sources(notebook_id, source_url);

CREATE TABLE IF NOT EXISTS apollo_source_payloads (
  notebook_id TEXT NOT NULL REFERENCES apollo_notebooks(id) ON DELETE CASCADE,
  source_name TEXT NOT NULL,
  payload BYTEA NOT NULL,
  updated TEXT NOT NULL,
  PRIMARY KEY (notebook_id, source_name)
);

CREATE INDEX IF NOT EXISTS idx_apollo_source_payloads_notebook
  ON apollo_source_payloads(notebook_id);
