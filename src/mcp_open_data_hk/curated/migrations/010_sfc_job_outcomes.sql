-- Preserve applied source migration 003. Timer provenance and recovery outcomes
-- are source job metadata, distinct from collection success and accepted facts.
ALTER TABLE curated_sfc.runs ADD COLUMN IF NOT EXISTS provenance text NOT NULL DEFAULT 'manual'
 CHECK(provenance IN ('manual','timer'));
ALTER TABLE curated_sfc.runs ADD COLUMN IF NOT EXISTS source_release text;
ALTER TABLE curated_sfc.runs ADD COLUMN IF NOT EXISTS job_outcomes jsonb NOT NULL DEFAULT '{}';
ALTER TABLE curated_sfc.runs ADD COLUMN IF NOT EXISTS job_updated_at timestamptz;
CREATE INDEX IF NOT EXISTS sfc_ce_versions ON curated_sfc.corporations(ce,version);
CREATE INDEX IF NOT EXISTS sfc_published_versions ON curated_sfc.versions(published_at DESC,version)
 WHERE published_at IS NOT NULL;
