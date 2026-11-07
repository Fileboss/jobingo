-- Prompts and answers are kept 90 days; a purged call keeps its counts and its cost,
-- so the statistics stay whole.
ALTER TABLE llm_calls ALTER COLUMN request DROP NOT NULL;
ALTER TABLE llm_calls ADD COLUMN purged_at TIMESTAMPTZ;

-- The application log: named events with a few fields (ids, counts, categories, short
-- reasons), never a prompt, a mail or a CV. An event caused by a model call points to
-- it. `user_id` is null for an event that concerns no account, such as a purge.
CREATE TABLE app_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT REFERENCES users (id) ON DELETE CASCADE,
    level TEXT NOT NULL CHECK (level IN ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')),
    name TEXT NOT NULL,
    logger TEXT NOT NULL,
    fields JSONB NOT NULL,
    -- No foreign key: a log line must never fail, nor block deleting a call.
    llm_call_id BIGINT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX app_events_user_created ON app_events (user_id, created_at);
CREATE INDEX app_events_llm_call ON app_events (llm_call_id);
