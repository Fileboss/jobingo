-- Mail read from the mailbox, read-only: nothing here is ever written back to it.
-- `mailbox` is the address read, so switching from the local server to Gmail mixes
-- nothing. The Message-ID makes a message read twice one row.
CREATE TABLE messages (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    mailbox TEXT NOT NULL,
    folder TEXT NOT NULL,
    message_id TEXT NOT NULL,
    thread_id TEXT NOT NULL,
    in_reply_to TEXT NOT NULL,
    from_addr TEXT NOT NULL,
    to_addrs TEXT NOT NULL,
    subject TEXT NOT NULL,
    body_text TEXT NOT NULL,
    body_html TEXT NOT NULL,
    list_unsubscribe BOOLEAN NOT NULL,
    received_at TIMESTAMPTZ NOT NULL,
    -- Sorted at sync time: a job alert read for its offers, or a message to classify.
    kind TEXT CHECK (kind IN ('alert', 'message')),
    -- When the alert's offers were stored, or the message classified.
    processed_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, mailbox, message_id)
);

CREATE INDEX messages_received ON messages (user_id, received_at DESC);

-- Where each folder's reading stopped. A new UIDVALIDITY means the server renumbered
-- the folder: it is read again, and the Message-ID drops what is already stored.
CREATE TABLE mail_folders (
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    mailbox TEXT NOT NULL,
    folder TEXT NOT NULL,
    uidvalidity TEXT NOT NULL,
    last_uid BIGINT NOT NULL,
    synced_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (user_id, mailbox, folder)
);

-- An offer read from an alert points to it; a pasted one does not.
ALTER TABLE offers ADD COLUMN message_id BIGINT REFERENCES messages (id) ON DELETE SET NULL;
