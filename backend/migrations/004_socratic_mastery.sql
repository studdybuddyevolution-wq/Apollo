-- Apollo Socratic Study mastery profile.
-- Additive and safe to re-run.

CREATE TABLE IF NOT EXISTS apollo_socratic_mastery (
  user_id TEXT NOT NULL,
  topic_key TEXT NOT NULL,
  display_name TEXT NOT NULL,
  score DOUBLE PRECISION NOT NULL DEFAULT 30.0,
  attempts INTEGER NOT NULL DEFAULT 0,
  correct INTEGER NOT NULL DEFAULT 0,
  updated TEXT NOT NULL,
  PRIMARY KEY (user_id, topic_key)
);

CREATE INDEX IF NOT EXISTS idx_apollo_socratic_mastery_user
  ON apollo_socratic_mastery(user_id, updated DESC);
