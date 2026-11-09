-- What the model said of a message, and what the user and the code did with it. The
-- category is the model's verdict alone: a message hidden by a rule has none.
ALTER TABLE messages
    ADD COLUMN category TEXT
        CHECK (category IN ('offer', 'rejection', 'interview', 'recruiter_other', 'other')),
    ADD COLUMN company_hint TEXT NOT NULL DEFAULT '',
    ADD COLUMN summary TEXT NOT NULL DEFAULT '',
    ADD COLUMN llm_call_id BIGINT REFERENCES llm_calls (id) ON DELETE SET NULL,
    -- Why it is out of the list: a newsletter or a blocked sender (rules, no model),
    -- filed as `other` by the model, or hidden by the user. NULL: shown.
    ADD COLUMN hidden_reason TEXT
        CHECK (hidden_reason IN ('newsletter', 'blocked_sender', 'other', 'user')),
    ADD COLUMN application_id BIGINT REFERENCES applications (id) ON DELETE SET NULL,
    -- `match`: tied by code at sync time; `user`: by hand.
    ADD COLUMN linked_by TEXT CHECK (linked_by IN ('match', 'user')),
    -- A status change the message suggests. It becomes an event only on a click.
    ADD COLUMN suggestion_type TEXT CHECK (suggestion_type IN ('rejected', 'interview_scheduled')),
    ADD COLUMN suggestion_date DATE,
    ADD COLUMN suggestion_status TEXT
        CHECK (suggestion_status IN ('pending', 'accepted', 'dismissed'));

CREATE INDEX messages_thread ON messages (user_id, thread_id);

-- The message an event came from: it moves with the message to another application.
ALTER TABLE application_events
    ADD COLUMN message_id BIGINT REFERENCES messages (id) ON DELETE SET NULL;

-- Senders whose messages are hidden without reaching the model.
CREATE TABLE blocked_senders (
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    address TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, address)
);
