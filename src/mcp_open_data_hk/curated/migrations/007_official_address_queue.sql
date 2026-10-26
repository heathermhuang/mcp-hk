-- Independent of other source migrations. Never changes accepted address facts.
ALTER TABLE curated.official_address_queue ADD COLUMN IF NOT EXISTS priority boolean NOT NULL DEFAULT false;
ALTER TABLE curated.official_address_checks ADD COLUMN IF NOT EXISTS receipt jsonb NOT NULL DEFAULT '{}';
ALTER TABLE curated.official_address_checks ADD COLUMN IF NOT EXISTS retry_category text;
ALTER TABLE curated.official_address_checks ADD COLUMN IF NOT EXISTS cohort text;
CREATE INDEX IF NOT EXISTS official_address_cohort_due ON curated.official_address_queue(priority,(last_success IS NULL),next_due,last_attempt,entity_id);
