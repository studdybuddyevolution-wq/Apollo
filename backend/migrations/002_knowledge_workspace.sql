-- Apollo Phase 1 knowledge workspace.
-- Additive and safe to re-run.

CREATE TABLE IF NOT EXISTS apollo_chat_sessions (
  id TEXT PRIMARY KEY,
  notebook_id TEXT NOT NULL REFERENCES apollo_notebooks(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL,
  title TEXT NOT NULL,
  created TEXT NOT NULL,
  updated TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_apollo_chat_sessions_scope
  ON apollo_chat_sessions(user_id, notebook_id, updated DESC);

CREATE TABLE IF NOT EXISTS apollo_chat_messages (
  id TEXT PRIMARY KEY,
  session_id TEXT NOT NULL REFERENCES apollo_chat_sessions(id) ON DELETE CASCADE,
  role TEXT NOT NULL,
  content TEXT NOT NULL,
  model TEXT,
  sources_json TEXT,
  created TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_apollo_chat_messages_session
  ON apollo_chat_messages(session_id, created);

CREATE TABLE IF NOT EXISTS apollo_notes (
  id TEXT PRIMARY KEY,
  notebook_id TEXT NOT NULL REFERENCES apollo_notebooks(id) ON DELETE CASCADE,
  user_id TEXT NOT NULL,
  title TEXT NOT NULL,
  content TEXT NOT NULL,
  source_type TEXT NOT NULL DEFAULT 'manual',
  source_ref TEXT,
  created TEXT NOT NULL,
  updated TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_apollo_notes_scope
  ON apollo_notes(user_id, notebook_id, updated DESC);
