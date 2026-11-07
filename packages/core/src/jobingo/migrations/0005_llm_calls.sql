-- One row per model call, failed ones included, with what it really cost. Whatever the
-- app derives from a call stores its `id`, so any result can be traced back to its call.
-- `request` and `response` hold the prompts and the answer: CV and mail content.
CREATE TABLE llm_calls (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    task TEXT NOT NULL,
    prompt_version INTEGER NOT NULL CHECK (prompt_version > 0),
    model TEXT NOT NULL,
    status TEXT NOT NULL CHECK (status IN ('ok', 'failed', 'error')),
    error TEXT,
    -- SHA-256 of the task's input, to find the calls made on the same input.
    input_hash TEXT NOT NULL,
    request JSONB NOT NULL,
    response JSONB,
    -- API requests made: the client retries once on an unusable answer, and both are billed.
    attempts INTEGER NOT NULL CHECK (attempts >= 0),
    input_tokens INTEGER NOT NULL CHECK (input_tokens >= 0),
    output_tokens INTEGER NOT NULL CHECK (output_tokens >= 0),
    cache_read_tokens INTEGER NOT NULL CHECK (cache_read_tokens >= 0),
    cache_write_tokens INTEGER NOT NULL CHECK (cache_write_tokens >= 0),
    cost_usd NUMERIC(12, 6) NOT NULL CHECK (cost_usd >= 0),
    latency_ms INTEGER NOT NULL CHECK (latency_ms >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX llm_calls_user_created ON llm_calls (user_id, created_at);
CREATE INDEX llm_calls_user_task_status ON llm_calls (user_id, task, status);
