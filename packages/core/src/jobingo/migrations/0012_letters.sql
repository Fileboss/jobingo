-- What the user knows about the company, written by them: a source the letter's facts
-- may come from.
ALTER TABLE applications ADD COLUMN company_notes TEXT NOT NULL DEFAULT '';

-- Cover letters. `proposal` is the model's answer as code checked it, kept unchanged as
-- the trail; `texts` is what the user made of it.
CREATE TABLE letters (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    application_id BIGINT NOT NULL REFERENCES applications (id) ON DELETE CASCADE,
    template TEXT NOT NULL,
    recipient TEXT NOT NULL,
    proposal JSONB NOT NULL,
    texts JSONB NOT NULL,
    llm_call_id BIGINT REFERENCES llm_calls (id) ON DELETE SET NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX letters_application ON letters (user_id, application_id, created_at);
