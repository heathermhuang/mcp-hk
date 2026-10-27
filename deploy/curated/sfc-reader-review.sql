-- Review only; do not execute without the separate source/access decision.
-- Source migrations must exist first. No LOGIN, password or role membership.
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sfc_reader') THEN
  CREATE ROLE sfc_reader NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS CONNECTION LIMIT 4;
 END IF;
END $$;
GRANT USAGE ON SCHEMA curated_sfc TO sfc_reader;
GRANT SELECT ON curated_sfc.policies,curated_sfc.versions,curated_sfc.corporations,curated_sfc.pointer TO sfc_reader;
GRANT SELECT (run_id,scheduled_for,started_at,state,requests,provenance,source_release,job_outcomes,job_updated_at) ON curated_sfc.runs TO sfc_reader;
GRANT SELECT (state,settled_at) ON curated_sfc.attempts TO sfc_reader;
-- No source capture locations, provider attempts, budgets, other-source tables,
-- schema CREATE, table mutation, owner membership or administrator access.
GRANT SELECT (until_at,reason) ON curated_sfc.holds TO sfc_reader;
ALTER ROLE sfc_reader SET default_transaction_read_only=on;
