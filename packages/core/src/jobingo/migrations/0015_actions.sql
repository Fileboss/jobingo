-- The documents attached to a message, frozen when the send is proposed: what leaves is
-- these bytes, checked against their SHA-256, never a fresh render. Never changed nor
-- deleted, so the archive says exactly what was sent.
CREATE TABLE documents (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    application_id BIGINT REFERENCES applications (id) ON DELETE SET NULL,
    kind TEXT NOT NULL CHECK (kind IN ('cv', 'letter')),
    filename TEXT NOT NULL,
    sha256 TEXT NOT NULL,
    content BYTEA NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE FUNCTION documents_frozen() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'UPDATE' AND NEW.content = OLD.content AND NEW.sha256 = OLD.sha256
        AND NEW.filename = OLD.filename THEN
        RETURN NEW;  -- an application deleted: its link is cleared, the bytes stay
    END IF;
    RAISE EXCEPTION 'documents are archived: never changed nor deleted';
END $$;

CREATE TRIGGER documents_frozen BEFORE UPDATE OR DELETE ON documents
    FOR EACH ROW EXECUTE FUNCTION documents_frozen();

-- The approval queue: every message that leaves goes through one row here, approved
-- by a click on the exact payload, then sent by the one executor. `sending` is held
-- between the executor's claim and the outcome, so a double click sends once.
CREATE TABLE pending_actions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('send_email')),
    status TEXT NOT NULL DEFAULT 'proposed'
        CHECK (status IN ('proposed', 'approved', 'sending', 'sent', 'failed', 'rejected')),
    payload JSONB NOT NULL,
    payload_hash TEXT NOT NULL,
    -- The hash the user saw when approving; the executor checks the payload against it.
    approved_hash TEXT,
    application_id BIGINT REFERENCES applications (id) ON DELETE SET NULL,
    -- The received message it answers.
    message_id BIGINT REFERENCES messages (id) ON DELETE SET NULL,
    -- What left, or would have left in a dry run: the exact bytes built by the executor.
    eml BYTEA,
    dry_run BOOLEAN,
    error TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    decided_at TIMESTAMPTZ,
    sent_at TIMESTAMPTZ
);

CREATE INDEX pending_actions_status ON pending_actions (user_id, status, created_at DESC);

-- A payload is immutable: changing it is a new action, approved again. The executor
-- recomputes the hash too: this is the first line, that check the second.
CREATE FUNCTION pending_actions_guard() RETURNS trigger LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'pending_actions are never deleted';
    END IF;
    IF NEW.payload IS DISTINCT FROM OLD.payload
        OR NEW.payload_hash IS DISTINCT FROM OLD.payload_hash THEN
        RAISE EXCEPTION 'pending_actions.payload is immutable';
    END IF;
    RETURN NEW;
END $$;

CREATE TRIGGER pending_actions_guard BEFORE UPDATE OR DELETE ON pending_actions
    FOR EACH ROW EXECUTE FUNCTION pending_actions_guard();

-- The send an event came from.
ALTER TABLE application_events
    ADD COLUMN action_id BIGINT REFERENCES pending_actions (id) ON DELETE SET NULL;
