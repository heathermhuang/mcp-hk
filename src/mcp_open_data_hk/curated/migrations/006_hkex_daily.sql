-- Public daily-summary observations. Separate from Webb archives and full-form windows.
CREATE SCHEMA IF NOT EXISTS hkex_daily;
REVOKE ALL ON SCHEMA hkex_daily FROM PUBLIC;
CREATE TABLE IF NOT EXISTS hkex_daily.versions (
 version text PRIMARY KEY, state text NOT NULL CHECK(state IN ('staged','qualified','published')),
 base_version text, published_revision bigint, manifest jsonb NOT NULL, restore_proof jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS hkex_daily.control (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton), accepted_version text REFERENCES hkex_daily.versions,
 last_checked timestamptz, last_success timestamptz, last_changed timestamptz,
 latest_source_date date, accepted_revision bigint NOT NULL DEFAULT 0, hold_code text, hold_until timestamptz, last_read_at timestamptz
);
INSERT INTO hkex_daily.control(singleton) VALUES(true) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS hkex_daily.reports (
 sha256 text PRIMARY KEY, day date NOT NULL, category integer NOT NULL CHECK(category BETWEEN 1 AND 4),
 source_sha256 text NOT NULL, transform_sha256 text NOT NULL,
 record_count integer NOT NULL CHECK(record_count BETWEEN 0 AND 5000), source_bytes integer NOT NULL,
 etag text, modified text, observed_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS hkex_daily_report_key ON hkex_daily.reports(day,category,transform_sha256,observed_at DESC);
CREATE TABLE IF NOT EXISTS hkex_daily.records (
 report_sha256 text NOT NULL REFERENCES hkex_daily.reports, id text NOT NULL,
 serial text NOT NULL, issuer_id text NOT NULL, stock_code text NOT NULL,
 summary_date date NOT NULL, category integer NOT NULL, facts jsonb NOT NULL,
 PRIMARY KEY(report_sha256,id)
);
CREATE INDEX IF NOT EXISTS hkex_daily_serial ON hkex_daily.records(serial,summary_date DESC,id);
CREATE INDEX IF NOT EXISTS hkex_daily_stock ON hkex_daily.records(stock_code,summary_date DESC,id);
CREATE INDEX IF NOT EXISTS hkex_daily_date ON hkex_daily.records(summary_date DESC,id);
CREATE TABLE IF NOT EXISTS hkex_daily.version_reports (
 version text NOT NULL REFERENCES hkex_daily.versions, day date NOT NULL, category integer NOT NULL,
 report_sha256 text NOT NULL REFERENCES hkex_daily.reports, PRIMARY KEY(version,day,category)
);
CREATE TABLE IF NOT EXISTS hkex_daily.runs (
 id text PRIMARY KEY, started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
 scheduled_for timestamptz, provenance text NOT NULL CHECK(provenance IN ('manual','timer')),
 state text NOT NULL DEFAULT 'running', code text, version text, latest_source_date date,
 request_count integer NOT NULL DEFAULT 0, received_bytes bigint NOT NULL DEFAULT 0
);
CREATE TABLE IF NOT EXISTS hkex_daily.requests (
 id bigserial PRIMARY KEY, run_id text NOT NULL REFERENCES hkex_daily.runs,
 path text NOT NULL, reserved_at timestamptz NOT NULL DEFAULT now(), state text NOT NULL,
 status integer, received_bytes integer, reserved_bytes integer NOT NULL,
 sha256 text, UNIQUE(run_id,path)
);
REVOKE ALL ON ALL TABLES IN SCHEMA hkex_daily FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA hkex_daily FROM PUBLIC;
