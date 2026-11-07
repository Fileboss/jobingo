-- Job offers, extracted from text the user pasted. `dedup_key` makes the same offer,
-- pasted twice or arriving through two channels, one row.
CREATE TABLE offers (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    title TEXT NOT NULL,
    company_name TEXT NOT NULL,
    location TEXT NOT NULL,
    contract TEXT NOT NULL
        CHECK (contract IN ('CDI', 'CDD', 'freelance', 'stage', 'alternance', 'interim', '')),
    remote TEXT NOT NULL CHECK (remote IN ('sur site', 'hybride', 'remote', '')),
    salary_min INTEGER,
    salary_max INTEGER,
    url TEXT,
    description_md TEXT NOT NULL,
    dedup_key TEXT NOT NULL,
    llm_call_id BIGINT REFERENCES llm_calls (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, dedup_key)
);

-- A CV adapted to a stored offer points to it; one adapted to pasted text does not.
ALTER TABLE cv_drafts ADD COLUMN offer_id BIGINT REFERENCES offers (id) ON DELETE SET NULL;
