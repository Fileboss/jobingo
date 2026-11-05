-- Accounts. No personal data here: the candidate's identity is stored apart,
-- so that a query on this table can never carry it towards the model.
CREATE TABLE users (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    username TEXT NOT NULL UNIQUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
