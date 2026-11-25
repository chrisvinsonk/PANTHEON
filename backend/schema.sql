-- Logical schema reference. SQLAlchemy creates the running MVP schema.
CREATE TABLE companies (
  id BIGSERIAL PRIMARY KEY, name VARCHAR(160) NOT NULL,
  mission TEXT NOT NULL DEFAULT '', strategic_context TEXT NOT NULL DEFAULT '',
  created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE executives (
  id BIGSERIAL PRIMARY KEY, role VARCHAR(32) NOT NULL UNIQUE,
  title VARCHAR(120) NOT NULL, mandate TEXT NOT NULL, system_instruction TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL
);
CREATE TABLE board_meetings (
  id BIGSERIAL PRIMARY KEY, title VARCHAR(240) NOT NULL, agenda TEXT NOT NULL,
  founder_context TEXT NOT NULL DEFAULT '', status VARCHAR(16) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL, completed_at TIMESTAMPTZ
);
CREATE TABLE agent_contributions (
  id BIGSERIAL PRIMARY KEY, meeting_id BIGINT NOT NULL REFERENCES board_meetings(id) ON DELETE CASCADE,
  role VARCHAR(32) NOT NULL, phase VARCHAR(32) NOT NULL,
  assessment TEXT NOT NULL DEFAULT '', critique TEXT NOT NULL DEFAULT '',
  model_provider VARCHAR(32) NOT NULL, model_name VARCHAR(120) NOT NULL,
  created_at TIMESTAMPTZ NOT NULL, UNIQUE(meeting_id, role, phase)
);
CREATE TABLE board_resolutions (
  id BIGSERIAL PRIMARY KEY, meeting_id BIGINT NOT NULL UNIQUE REFERENCES board_meetings(id) ON DELETE CASCADE,
  recommendation TEXT NOT NULL, rationale TEXT NOT NULL DEFAULT '',
  dissent_and_open_questions TEXT NOT NULL DEFAULT '', decision_status VARCHAR(32) NOT NULL,
  founder_notes TEXT NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL, decided_at TIMESTAMPTZ
);
CREATE TABLE approval_events (
  id BIGSERIAL PRIMARY KEY, meeting_id BIGINT NOT NULL REFERENCES board_meetings(id) ON DELETE CASCADE,
  action VARCHAR(40) NOT NULL, actor VARCHAR(120) NOT NULL,
  comments TEXT NOT NULL DEFAULT '', created_at TIMESTAMPTZ NOT NULL
);
