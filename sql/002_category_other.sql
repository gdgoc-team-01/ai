-- Apply atomically before deploying the new AI server and category writers.
BEGIN;
ALTER TABLE posts ADD COLUMN IF NOT EXISTS category VARCHAR(30) NOT NULL DEFAULT 'OTHER';
ALTER TABLE posts ALTER COLUMN category SET DEFAULT 'OTHER';
UPDATE posts SET category = 'OTHER' WHERE category IS NULL OR category = 'UNKNOWN';
ALTER TABLE posts ALTER COLUMN category SET NOT NULL;
COMMIT;
