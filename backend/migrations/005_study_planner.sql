-- Marklyf Study Planner MVP.
-- Additive and safe to re-run.

CREATE TABLE IF NOT EXISTS study_goals (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  title TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  goal_type TEXT NOT NULL DEFAULT 'exam',
  subject TEXT NOT NULL DEFAULT '',
  exam_date DATE,
  desired_outcome TEXT,
  priority INTEGER NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
  status TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active','completed','archived')),
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_study_goals_user_status
  ON study_goals(user_id, status, exam_date);

CREATE TABLE IF NOT EXISTS study_topics (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  goal_id TEXT REFERENCES study_goals(id) ON DELETE SET NULL,
  parent_id TEXT REFERENCES study_topics(id) ON DELETE SET NULL,
  subject TEXT NOT NULL DEFAULT '',
  title TEXT NOT NULL,
  description TEXT,
  estimated_minutes INTEGER NOT NULL DEFAULT 45 CHECK (estimated_minutes > 0),
  difficulty INTEGER NOT NULL DEFAULT 3 CHECK (difficulty BETWEEN 1 AND 5),
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','in_progress','completed')),
  sort_order INTEGER NOT NULL DEFAULT 0,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_study_topics_user_goal
  ON study_topics(user_id, goal_id, sort_order, title);
CREATE INDEX IF NOT EXISTS idx_study_topics_user_parent
  ON study_topics(user_id, parent_id, sort_order, title);

CREATE TABLE IF NOT EXISTS study_plan_blocks (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  goal_id TEXT REFERENCES study_goals(id) ON DELETE SET NULL,
  topic_id TEXT REFERENCES study_topics(id) ON DELETE SET NULL,
  title TEXT NOT NULL,
  planned_date DATE NOT NULL,
  start_time TIME,
  duration_minutes INTEGER NOT NULL CHECK (duration_minutes > 0),
  status TEXT NOT NULL DEFAULT 'planned' CHECK (status IN ('planned','completed','skipped')),
  priority INTEGER NOT NULL DEFAULT 3 CHECK (priority BETWEEN 1 AND 5),
  generated_by TEXT NOT NULL DEFAULT 'manual' CHECK (generated_by IN ('manual','generated','replanned')),
  locked BOOLEAN NOT NULL DEFAULT FALSE,
  notebook_id TEXT REFERENCES apollo_notebooks(id) ON DELETE SET NULL,
  source_id TEXT REFERENCES apollo_sources(id) ON DELETE SET NULL,
  session_id TEXT REFERENCES apollo_chat_sessions(id) ON DELETE SET NULL,
  actual_minutes INTEGER,
  completed_at TIMESTAMPTZ,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_study_plan_blocks_user_date
  ON study_plan_blocks(user_id, planned_date, start_time);
CREATE INDEX IF NOT EXISTS idx_study_plan_blocks_user_status
  ON study_plan_blocks(user_id, status, generated_by, locked);

CREATE TABLE IF NOT EXISTS study_availability (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL,
  weekday INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
  start_time TIME NOT NULL,
  end_time TIME NOT NULL,
  enabled BOOLEAN NOT NULL DEFAULT TRUE,
  CHECK (start_time < end_time)
);

CREATE INDEX IF NOT EXISTS idx_study_availability_user_weekday
  ON study_availability(user_id, weekday, start_time);
