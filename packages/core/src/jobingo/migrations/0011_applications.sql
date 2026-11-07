-- Applications and their timeline. `status` is derived from the events and stored only
-- to sort and filter; the events are the truth. Deleting hides an application: its
-- events stay, for the record.
CREATE TABLE applications (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    offer_id BIGINT REFERENCES offers (id) ON DELETE SET NULL,
    title TEXT NOT NULL,
    company_name TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'a_postuler'
        CHECK (status IN ('a_postuler', 'postule', 'en_echange', 'entretien', 'offre', 'cloture')),
    -- Someone at the company: third-party data, never put in a prompt on its own.
    contact_name TEXT NOT NULL DEFAULT '',
    contact_email TEXT NOT NULL DEFAULT '',
    contact_phone TEXT NOT NULL DEFAULT '',
    deleted_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- One live application per offer.
CREATE UNIQUE INDEX applications_one_per_offer
    ON applications (user_id, offer_id) WHERE deleted_at IS NULL AND offer_id IS NOT NULL;

CREATE TABLE application_events (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    application_id BIGINT NOT NULL REFERENCES applications (id) ON DELETE CASCADE,
    type TEXT NOT NULL CHECK (type IN ('applied', 'message_received', 'message_sent',
        'interview_scheduled', 'interview_done', 'offer_received', 'rejected', 'withdrawn',
        'note')),
    occurred_at DATE NOT NULL,
    note TEXT NOT NULL DEFAULT '',
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX application_events_app ON application_events (user_id, application_id, occurred_at);
