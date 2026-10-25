-- Independent source schema: no dependency on CR, racing, HKEX or archive tables.
CREATE SCHEMA IF NOT EXISTS curated_sfc;
REVOKE ALL ON SCHEMA curated_sfc FROM PUBLIC;
CREATE TABLE curated_sfc.migrations(version text PRIMARY KEY, sha256 text NOT NULL);
CREATE TABLE curated_sfc.policies (
 sha256 text PRIMARY KEY CHECK(sha256 ~ '^[a-f0-9]{64}$'),
 record jsonb NOT NULL, active boolean NOT NULL DEFAULT false,
 activated_at timestamptz NOT NULL, revoked_at timestamptz
);
CREATE UNIQUE INDEX one_active_policy ON curated_sfc.policies(active) WHERE active;
CREATE TABLE curated_sfc.runs (
 run_id text PRIMARY KEY, scheduled_for timestamptz NOT NULL UNIQUE,
 policy_sha256 text NOT NULL REFERENCES curated_sfc.policies,
 cohort text[] NOT NULL CHECK(cardinality(cohort) BETWEEN 1 AND 25),
 started_at timestamptz NOT NULL DEFAULT now(),
 state text NOT NULL CHECK(state IN ('running','partial','failed','validated','published')),
 requests integer NOT NULL DEFAULT 0, reserved_bytes bigint NOT NULL DEFAULT 0,
 CHECK(requests BETWEEN 0 AND 25), CHECK(reserved_bytes BETWEEN 0 AND 8388608)
);
CREATE TABLE curated_sfc.budgets (
 day date PRIMARY KEY, requests integer NOT NULL CHECK(requests BETWEEN 0 AND 100),
 bytes bigint NOT NULL CHECK(bytes BETWEEN 0 AND 16777216)
);
CREATE TABLE curated_sfc.holds (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 until_at timestamptz NOT NULL, reason text NOT NULL CHECK(reason IN ('forbidden','rate_limited','uncertain'))
);
CREATE TABLE curated_sfc.attempts (
 attempt_id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 run_id text NOT NULL REFERENCES curated_sfc.runs,
 ce text NOT NULL CHECK(ce ~ '^[A-Z]{3}[0-9]{3}$'),
 kind text NOT NULL CHECK(kind IN ('session','detail','retry')),
 reserved_bytes integer NOT NULL CHECK(reserved_bytes > 0),
 state text NOT NULL CHECK(state IN ('unknown','ok','not_modified','missing','rejected','failed')),
 requested_at timestamptz NOT NULL DEFAULT now(), settled_at timestamptz
);
CREATE TABLE curated_sfc.versions (
 version text PRIMARY KEY CHECK(version ~ '^sfc-[a-f0-9]{32}$'),
 run_id text NOT NULL UNIQUE REFERENCES curated_sfc.runs,
 policy_sha256 text NOT NULL REFERENCES curated_sfc.policies,
 manifest jsonb NOT NULL, facts_sha256 text NOT NULL,
 expires_at timestamptz NOT NULL,
 restore_proof jsonb, published_at timestamptz
);
CREATE TABLE curated_sfc.captures (
 capture_id text PRIMARY KEY CHECK(capture_id ~ '^[a-f0-9]{64}$'),
 version text NOT NULL REFERENCES curated_sfc.versions,
 ce text NOT NULL CHECK(ce ~ '^[A-Z]{3}[0-9]{3}$'),
 attempt_id bigint NOT NULL UNIQUE REFERENCES curated_sfc.attempts,
 source_url text NOT NULL, observed_at timestamptz NOT NULL,
 normalized_payload_sha256 text NOT NULL CHECK(normalized_payload_sha256 ~ '^[a-f0-9]{64}$'),
 transform_sha256 text NOT NULL CHECK(transform_sha256 ~ '^[a-f0-9]{64}$'),
 UNIQUE(version,ce)
);
CREATE TABLE curated_sfc.corporations (
 version text NOT NULL REFERENCES curated_sfc.versions,
 ce text NOT NULL CHECK(ce ~ '^[A-Z]{3}[0-9]{3}$'),
 capture_id text NOT NULL UNIQUE REFERENCES curated_sfc.captures,
 fact jsonb NOT NULL, PRIMARY KEY(version,ce),
 CHECK(fact->>'ce'=ce), CHECK(fact->>'entityType'='corporation'),
 CHECK(fact->>'regime'='SFO'), CHECK(fact->>'licenceType'='licensed_corporation')
);
CREATE TABLE curated_sfc.pointer (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 version text NOT NULL REFERENCES curated_sfc.versions
);
REVOKE ALL ON ALL TABLES IN SCHEMA curated_sfc FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA curated_sfc FROM PUBLIC;
