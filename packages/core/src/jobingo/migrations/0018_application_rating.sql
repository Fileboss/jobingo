-- The user's own rating of an application, from 1 to 5 stars: theirs alone, apart from
-- the scores the code computes. NULL: not rated.
ALTER TABLE applications ADD COLUMN rating SMALLINT CHECK (rating BETWEEN 1 AND 5);
