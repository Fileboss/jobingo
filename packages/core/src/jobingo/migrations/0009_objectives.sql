-- What the user is looking for: one row per account. Filters and weights are applied by
-- code; the preferences are read by the model when it rates an offer.
CREATE TABLE objectives (
    user_id BIGINT PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    hard_filters JSONB NOT NULL,
    weights JSONB NOT NULL,
    preferences TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
