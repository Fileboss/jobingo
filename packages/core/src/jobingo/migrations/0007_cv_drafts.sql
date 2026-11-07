-- A CV adapted to one offer. `proposal` is the model's answer as code checked it, kept
-- unchanged as the trail; `choices` is what the user made of it. The offer is pasted
-- text until offers have their own table.
CREATE TABLE cv_drafts (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    lang TEXT NOT NULL CHECK (lang IN ('fr', 'en')),
    offer_title TEXT NOT NULL,
    offer_company TEXT NOT NULL,
    offer_description TEXT NOT NULL,
    llm_call_id BIGINT REFERENCES llm_calls (id) ON DELETE SET NULL,
    proposal JSONB NOT NULL,
    choices JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX cv_drafts_user_created ON cv_drafts (user_id, created_at);
