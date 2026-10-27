-- Review packet only. Do not run without the source/access decision.
-- Apply source migrations with the existing database administrator first.
-- This role is intentionally NOLOGIN; no password is created by this packet.
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='sfc_writer') THEN
  CREATE ROLE sfc_writer NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT NOBYPASSRLS CONNECTION LIMIT 4;
 END IF;
END $$;
GRANT USAGE ON SCHEMA curated_sfc TO sfc_writer;
GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA curated_sfc TO sfc_writer;
GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA curated_sfc TO sfc_writer;
GRANT EXECUTE ON FUNCTION pg_catalog.pg_control_system() TO sfc_writer;
-- No grants on company, Racing, HKEX or public schemas; no role membership.
-- LOGIN/password provisioning, if approved, is a separate protected step.
