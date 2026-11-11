-- An adapted CV belongs to an application: it is made from the application's page, and
-- sent with it. Drafts made for an offer move to the live application of that offer, if
-- any; the others keep their offer and stay readable by their link.
ALTER TABLE cv_drafts
    ADD COLUMN application_id BIGINT REFERENCES applications (id) ON DELETE SET NULL;

UPDATE cv_drafts d SET application_id = a.id
FROM applications a
WHERE d.offer_id IS NOT NULL AND a.user_id = d.user_id AND a.offer_id = d.offer_id
    AND a.deleted_at IS NULL;

CREATE INDEX cv_drafts_application ON cv_drafts (user_id, application_id, created_at);
