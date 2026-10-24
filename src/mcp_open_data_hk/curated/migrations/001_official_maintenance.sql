-- Additive maintenance state; old captures and published memberships stay immutable.
ALTER TABLE curated.official_captures ADD COLUMN IF NOT EXISTS transform_version text NOT NULL DEFAULT 'official-v1-9f7f2fb';
ALTER TABLE curated.official_captures ADD COLUMN IF NOT EXISTS transform_sha256 text;
CREATE TABLE IF NOT EXISTS curated.official_inventory (
 source_key text PRIMARY KEY, week text NOT NULL, register text NOT NULL,
 verification_url text NOT NULL, inventory_hash text NOT NULL,
 discovered_at timestamptz NOT NULL DEFAULT now(), checked_at timestamptz NOT NULL DEFAULT now(),
 present boolean NOT NULL DEFAULT true, state text NOT NULL DEFAULT 'discovered');
CREATE TABLE IF NOT EXISTS curated.official_jobs (
 job_id text PRIMARY KEY, family text NOT NULL, operation text NOT NULL,
 scheduled_for timestamptz NOT NULL, started_at timestamptz NOT NULL DEFAULT now(),
 finished_at timestamptz, status text NOT NULL DEFAULT 'running',
 collection_status text NOT NULL DEFAULT 'pending', publication_status text NOT NULL DEFAULT 'pending',
 backup_status text NOT NULL DEFAULT 'not_observed', receipt jsonb NOT NULL DEFAULT '{}',
 UNIQUE(family,operation,scheduled_for));
CREATE TABLE IF NOT EXISTS curated.official_source_state (
 family text PRIMARY KEY, checked_at timestamptz, hold_until timestamptz,
 state jsonb NOT NULL DEFAULT '{}');
CREATE TABLE IF NOT EXISTS curated.official_daily_budgets (
 provider text NOT NULL, day date NOT NULL, requests integer NOT NULL DEFAULT 0,
 bytes bigint NOT NULL DEFAULT 0, PRIMARY KEY(provider,day));
CREATE TABLE IF NOT EXISTS curated.official_staged (
 source_key text PRIMARY KEY, capture_id text NOT NULL REFERENCES curated.official_captures,
 group_key text NOT NULL, staged_at timestamptz NOT NULL DEFAULT now());
CREATE TABLE IF NOT EXISTS curated.official_address_queue (
 entity_id text PRIMARY KEY, last_attempt timestamptz, last_success timestamptz,
 next_due timestamptz NOT NULL DEFAULT '-infinity', outcome text NOT NULL DEFAULT 'never',
 latest_capture text REFERENCES curated.official_captures);
CREATE INDEX IF NOT EXISTS official_address_due ON curated.official_address_queue(next_due,last_success NULLS FIRST,entity_id);
CREATE TABLE IF NOT EXISTS curated.official_address_checks (
 job_id text NOT NULL REFERENCES curated.official_jobs, entity_id text NOT NULL,
 checked_at timestamptz NOT NULL DEFAULT now(), outcome text NOT NULL,
 capture_id text REFERENCES curated.official_captures, PRIMARY KEY(job_id,entity_id));
CREATE TABLE IF NOT EXISTS curated.official_address_observations (
 observation_id text PRIMARY KEY, entity_id text NOT NULL,
 source_key text NOT NULL, capture_id text NOT NULL REFERENCES curated.official_captures,
 observed_at timestamptz NOT NULL, previous_id text,
 UNIQUE(source_key,capture_id));
CREATE INDEX IF NOT EXISTS official_address_observed ON curated.official_address_observations(entity_id,observed_at DESC,observation_id);
ALTER TABLE curated.official_address_queue ADD COLUMN IF NOT EXISTS latest_observation text REFERENCES curated.official_address_observations;
-- Seed legacy occurrences using their original source capture date, never now().
INSERT INTO curated.official_address_observations(observation_id,entity_id,source_key,capture_id,observed_at)
 SELECT DISTINCT md5(m.source_key||':'||m.capture_id),r.entity_id,m.source_key,m.capture_id,(c.receipt->>'fetchedAt')::timestamptz
 FROM curated.official_members m JOIN curated.official_captures c USING(capture_id)
 JOIN curated.official_records r USING(capture_id)
 WHERE r.record->>'kind'='address_observation' AND c.receipt->>'fetchedAt' IS NOT NULL
 ON CONFLICT DO NOTHING;
ALTER TABLE curated.official_jobs ADD COLUMN IF NOT EXISTS published_at timestamptz;

-- Actual unchanged v1 parser module hash; original fetchedAt stays untouched.
UPDATE curated.official_captures SET transform_sha256='3ea3dbef4e1fd85aec7bf1981c3cf8404720243c6565c0554a0eea7fe577ffb6' WHERE transform_version='official-v1-9f7f2fb' AND transform_sha256 IS NULL;
-- Reconcile today's legacy requests once, so migration cannot reset the provider budget.
WITH marker AS (
 INSERT INTO curated.official_source_state(family,checked_at,state)
 VALUES('legacy_budget_seed',now(),'{"status":"seeded"}') ON CONFLICT DO NOTHING RETURNING 1
), legacy AS (
 SELECT coalesce(sum((r.receipt->>'requests')::integer),0) AS requests,
 coalesce(sum((r.receipt->>'bytes')::bigint),0) AS bytes
 FROM curated.official_runs r LEFT JOIN curated.official_jobs j ON j.job_id=r.run_id
 WHERE j.job_id IS NULL AND r.started_at>=(now() AT TIME ZONE 'UTC')::date
 AND jsonb_typeof(r.receipt->'requests')='number' AND jsonb_typeof(r.receipt->'bytes')='number'
)
INSERT INTO curated.official_daily_budgets(provider,day,requests,bytes)
 SELECT 'cr',(now() AT TIME ZONE 'UTC')::date,legacy.requests,legacy.bytes FROM legacy,marker
 ON CONFLICT(provider,day) DO UPDATE SET requests=official_daily_budgets.requests+EXCLUDED.requests,bytes=official_daily_budgets.bytes+EXCLUDED.bytes;
