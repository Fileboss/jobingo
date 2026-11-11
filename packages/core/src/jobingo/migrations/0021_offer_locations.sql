-- An offer can be based in several cities (« Paris ou Toulouse »): the filter on the
-- place must see them all. The single city stored so far becomes a list of one.
ALTER TABLE offers ADD COLUMN locations TEXT[] NOT NULL DEFAULT '{}';
UPDATE offers SET locations = ARRAY[location] WHERE location <> '';
ALTER TABLE offers DROP COLUMN location;
