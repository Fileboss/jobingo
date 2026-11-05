-- What goes on the page of the CV: the ids of the items left out, and the template's
-- options. Everything not listed is on the page, so a new CV item is selected.
CREATE TABLE cv_selections (
    user_id BIGINT NOT NULL REFERENCES users (id) ON DELETE CASCADE,
    lang TEXT NOT NULL CHECK (lang IN ('fr', 'en')),
    excluded_ids TEXT[] NOT NULL,
    photo BOOLEAN NOT NULL,
    panneau_competences BOOLEAN NOT NULL,
    loisirs BOOLEAN NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (user_id, lang)
);
