-- Apollo history and analytics indexes.
-- Safe to re-run.

CREATE INDEX IF NOT EXISTS idx_apollo_chat_sessions_user_updated_cursor
  ON apollo_chat_sessions(user_id, updated DESC, id DESC);

CREATE INDEX IF NOT EXISTS idx_apollo_chat_messages_session_created_cursor
  ON apollo_chat_messages(session_id, created DESC, id DESC);
