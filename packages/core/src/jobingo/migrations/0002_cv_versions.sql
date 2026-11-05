-- The candidate's exhaustive CV, one row per saved version. `content` is the stored
-- Markdown, ids included. Rows are only ever added: the highest version is the current
-- one, and the unique key is what stops two concurrent saves from both winning.
CREATE TABLE cv_versions (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    lang TEXT NOT NULL CHECK (lang IN ('fr', 'en')),
    version INTEGER NOT NULL CHECK (version > 0),
    content TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, lang, version)
);
