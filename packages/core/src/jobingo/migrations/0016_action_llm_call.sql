-- The model call a message was drafted from, when it was: the user's edits are the
-- payload, the call is the trail.
ALTER TABLE pending_actions
    ADD COLUMN llm_call_id BIGINT REFERENCES llm_calls (id) ON DELETE SET NULL;
