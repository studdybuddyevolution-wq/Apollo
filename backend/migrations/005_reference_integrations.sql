-- Apollo reference-derived security, planning and billing primitives.
-- Additive and safe to re-run.

CREATE TABLE IF NOT EXISTS apollo_users (
  id TEXT PRIMARY KEY,
  email TEXT NOT NULL UNIQUE,
  password_hash TEXT NOT NULL,
  is_active BOOLEAN NOT NULL DEFAULT TRUE,
  is_superuser BOOLEAN NOT NULL DEFAULT FALSE,
  stripe_customer_id TEXT UNIQUE,
  subscription_status TEXT,
  subscription_updated_at BIGINT,
  created TEXT NOT NULL,
  updated TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_apollo_users_email ON apollo_users(email);

CREATE TABLE IF NOT EXISTS apollo_auth_attempts (
  id BIGSERIAL PRIMARY KEY,
  ip TEXT NOT NULL,
  email TEXT,
  kind TEXT NOT NULL,
  ok BOOLEAN NOT NULL DEFAULT FALSE,
  at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_apollo_auth_attempts_scope
  ON apollo_auth_attempts(ip, kind, at DESC);

CREATE TABLE IF NOT EXISTS apollo_rate_limit_events (
  id BIGSERIAL PRIMARY KEY,
  rate_key TEXT NOT NULL,
  bucket TEXT NOT NULL,
  at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_apollo_rate_limit_events_scope
  ON apollo_rate_limit_events(rate_key, bucket, at DESC);

CREATE TABLE IF NOT EXISTS apollo_stripe_webhook_events (
  event_id TEXT PRIMARY KEY,
  event_type TEXT NOT NULL,
  stripe_created BIGINT,
  status TEXT NOT NULL DEFAULT 'received',
  error_message TEXT,
  received_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  processed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS idx_apollo_stripe_events_status
  ON apollo_stripe_webhook_events(status, received_at DESC);

CREATE TABLE IF NOT EXISTS apollo_study_preferences (
  user_id TEXT PRIMARY KEY,
  daily_hours DOUBLE PRECISION NOT NULL DEFAULT 2.0,
  updated TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS apollo_courses (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  code TEXT NOT NULL,
  title TEXT NOT NULL,
  deadline_at TEXT,
  priority INTEGER NOT NULL DEFAULT 3,
  created TEXT NOT NULL,
  updated TEXT NOT NULL,
  UNIQUE(user_id, code)
);

CREATE INDEX IF NOT EXISTS idx_apollo_courses_user
  ON apollo_courses(user_id, priority, deadline_at);

CREATE TABLE IF NOT EXISTS apollo_study_topics (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  course_id TEXT NOT NULL REFERENCES apollo_courses(id) ON DELETE CASCADE,
  title TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'not_started',
  estimated_hours DOUBLE PRECISION NOT NULL DEFAULT 1.0,
  lecture_at TEXT,
  completed_at TEXT,
  created TEXT NOT NULL,
  updated TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_apollo_study_topics_course
  ON apollo_study_topics(user_id, course_id, status, lecture_at);
