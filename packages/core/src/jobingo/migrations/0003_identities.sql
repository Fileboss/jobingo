-- The candidate's identity and photo, apart from the CV: what no model flow may read.
-- A row is replaced by a save, so it has no versions.
CREATE TABLE identities (
    user_id BIGINT PRIMARY KEY REFERENCES users (id) ON DELETE CASCADE,
    name TEXT NOT NULL DEFAULT '',
    email TEXT NOT NULL DEFAULT '',
    phone TEXT NOT NULL DEFAULT '',
    address TEXT NOT NULL DEFAULT '',
    linkedin TEXT NOT NULL DEFAULT '',
    github TEXT NOT NULL DEFAULT '',
    photo BYTEA,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
