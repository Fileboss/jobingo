-- An offer has two scores, fit and salary, never mixed: the global one averaged the
-- salary rating in, and an offer stating no salary, the common case, fell for it. Every
-- row already holds its fit score, so nothing is recomputed.
ALTER TABLE offer_scores DROP COLUMN score;
