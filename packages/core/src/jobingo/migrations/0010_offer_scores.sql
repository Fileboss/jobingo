-- Scoring. `state` is automatic and recomputed at each scoring; `decision` is the
-- user's, and scoring never touches it.
ALTER TABLE offers
    ADD COLUMN state TEXT NOT NULL DEFAULT 'new' CHECK (state IN ('new', 'scored', 'filtered')),
    ADD COLUMN decision TEXT CHECK (decision IN ('shortlisted', 'dismissed'));

-- Every scoring of an offer, the latest being the current one. A score keeps what it
-- was computed from: the weights, the objectives' hash and the CV version, so a stale
-- score is known and an old one can be explained.
CREATE TABLE offer_scores (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    offer_id BIGINT NOT NULL REFERENCES offers (id) ON DELETE CASCADE,
    passed_filters BOOLEAN NOT NULL,
    eliminated_by JSONB NOT NULL,
    unknown JSONB NOT NULL,
    criteria JSONB,
    score INTEGER CHECK (score BETWEEN 0 AND 100),
    fit_score INTEGER CHECK (fit_score BETWEEN 0 AND 100),
    salary_score INTEGER CHECK (salary_score BETWEEN 0 AND 100),
    summary TEXT NOT NULL,
    strengths JSONB NOT NULL,
    gaps JSONB NOT NULL,
    weights JSONB NOT NULL,
    objectives_hash TEXT NOT NULL,
    cv_version INTEGER NOT NULL,
    llm_call_id BIGINT REFERENCES llm_calls (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX offer_scores_offer ON offer_scores (user_id, offer_id, id);
