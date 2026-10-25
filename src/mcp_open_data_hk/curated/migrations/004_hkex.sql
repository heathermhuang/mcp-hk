-- Independent source schema: no changes/grants in curated or sibling schemas.
CREATE SCHEMA IF NOT EXISTS hkex;
REVOKE ALL ON SCHEMA hkex FROM PUBLIC;
CREATE TABLE IF NOT EXISTS hkex.policies (
 hash text PRIMARY KEY CHECK (hash ~ '^[a-f0-9]{64}$'), document jsonb NOT NULL,
 activated_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS hkex.control (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 policy_hash text REFERENCES hkex.policies,
 hold_until timestamptz, hold_code text, last_read_at timestamptz
);
INSERT INTO hkex.control(singleton) VALUES(true) ON CONFLICT DO NOTHING;
CREATE TABLE IF NOT EXISTS hkex.runs (
 id text PRIMARY KEY, operation text NOT NULL, scheduled_for timestamptz NOT NULL,
 policy_hash text NOT NULL REFERENCES hkex.policies, scope_window jsonb NOT NULL,
 state text NOT NULL CHECK(state IN ('running','partial','failed','validated','unchanged')),
 started_at timestamptz NOT NULL DEFAULT now(), finished_at timestamptz,
 error_code text, inventory jsonb, checkpoint jsonb NOT NULL DEFAULT '{}',
 UNIQUE(operation, scheduled_for)
);
CREATE TABLE IF NOT EXISTS hkex.requests (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 run_id text NOT NULL REFERENCES hkex.runs, reserved_at timestamptz NOT NULL DEFAULT now(),
 kind text NOT NULL CHECK(kind IN ('listing','detail','inventory')),
 request_key text NOT NULL, state text NOT NULL DEFAULT 'unknown'
 CHECK(state IN ('unknown','success','failed')), status integer,
 reserved_bytes integer NOT NULL CHECK(reserved_bytes>0), received_bytes integer,
 sha256 text, UNIQUE(run_id,kind,request_key)
);
CREATE INDEX IF NOT EXISTS hkex_request_day ON hkex.requests(reserved_at);
CREATE TABLE IF NOT EXISTS hkex.captures (
 id text PRIMARY KEY, run_id text NOT NULL REFERENCES hkex.runs,
 policy_hash text NOT NULL REFERENCES hkex.policies,
 kind text NOT NULL CHECK(kind IN ('listing','detail','inventory')),
 source_location text NOT NULL, observed_at timestamptz NOT NULL,
 raw_sha256 text NOT NULL CHECK(raw_sha256 ~ '^[a-f0-9]{64}$'),
 transform_sha256 text NOT NULL CHECK(transform_sha256 ~ '^[a-f0-9]{64}$'),
 raw_bytes bytea, validation text NOT NULL CHECK(validation IN ('validated','rejected'))
);
CREATE TABLE IF NOT EXISTS hkex.versions (
 version text PRIMARY KEY, run_id text NOT NULL UNIQUE REFERENCES hkex.runs,
 policy_hash text NOT NULL REFERENCES hkex.policies,
 state text NOT NULL CHECK(state IN ('staging','validated','restore-qualified','published')),
 manifest jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
 restore_proof jsonb, published_at timestamptz
);
CREATE TABLE IF NOT EXISTS hkex.issuers (
 version text NOT NULL REFERENCES hkex.versions, id text NOT NULL,
 name text NOT NULL, search_key text COLLATE "C" NOT NULL, PRIMARY KEY(version,id)
);
CREATE INDEX IF NOT EXISTS hkex_issuer_prefix ON hkex.issuers(version,search_key,id);
CREATE TABLE IF NOT EXISTS hkex.securities (
 version text NOT NULL, issuer_id text NOT NULL, id text NOT NULL,
 stock_code text NOT NULL CHECK(stock_code ~ '^[0-9]{5}$'),
 share_class text NOT NULL, name text NOT NULL, name_date jsonb NOT NULL,
 PRIMARY KEY(version,issuer_id,id),
 FOREIGN KEY(version,issuer_id) REFERENCES hkex.issuers(version,id)
);
CREATE INDEX IF NOT EXISTS hkex_security_code ON hkex.securities(version,stock_code,issuer_id);
CREATE TABLE IF NOT EXISTS hkex.filings (
 version text NOT NULL, serial text NOT NULL, issuer_id text NOT NULL,
 capture_id text NOT NULL REFERENCES hkex.captures,
 form text NOT NULL CHECK(form IN ('1','2','3A','3B','3C','3D')),
 channel text NOT NULL CHECK(channel IN ('dion','pre_dion')),
 state text NOT NULL CHECK(state IN ('original','amendment','superseded','withdrawn')),
 event_date date, filed_date date, published_date date, payload jsonb NOT NULL,
 PRIMARY KEY(version,serial), FOREIGN KEY(version,issuer_id) REFERENCES hkex.issuers(version,id)
);
CREATE INDEX IF NOT EXISTS hkex_filed_range ON hkex.filings(version,issuer_id,filed_date,serial);
CREATE INDEX IF NOT EXISTS hkex_event_range ON hkex.filings(version,issuer_id,event_date,serial);
CREATE INDEX IF NOT EXISTS hkex_published_range ON hkex.filings(version,issuer_id,published_date,serial);
CREATE TABLE IF NOT EXISTS hkex.revisions (
 version text NOT NULL REFERENCES hkex.versions, older text NOT NULL, newer text NOT NULL,
 resolved boolean NOT NULL, PRIMARY KEY(version,older,newer), CHECK(older<>newer)
);
CREATE TABLE IF NOT EXISTS hkex.interests (
 version text NOT NULL, serial text NOT NULL, section text NOT NULL, line text NOT NULL,
 security_id text NOT NULL, capacity_code text NOT NULL, nature text NOT NULL,
 position text NOT NULL, phase text NOT NULL, instrument text NOT NULL,
 shares numeric, shares_raw text, percentage numeric, percentage_raw text,
 unit text NOT NULL, party_ref text, PRIMARY KEY(version,serial,section,line),
 FOREIGN KEY(version,serial) REFERENCES hkex.filings(version,serial),
 CHECK((shares IS NULL)=(shares_raw IS NULL)), CHECK((percentage IS NULL)=(percentage_raw IS NULL))
);
CREATE TABLE IF NOT EXISTS hkex.particulars (
 version text NOT NULL, serial text NOT NULL, line text NOT NULL,
 reason_code text NOT NULL, shares numeric, shares_raw text, price numeric, price_raw text,
 currency text, unit text NOT NULL, PRIMARY KEY(version,serial,line),
 FOREIGN KEY(version,serial) REFERENCES hkex.filings(version,serial)
);
CREATE TABLE IF NOT EXISTS hkex.parties (
 version text NOT NULL, serial text NOT NULL, ref text NOT NULL,
 disclosed_name text NOT NULL, source_global_id text, association text,
 PRIMARY KEY(version,serial,ref), FOREIGN KEY(version,serial) REFERENCES hkex.filings(version,serial)
);
CREATE TABLE IF NOT EXISTS hkex.codes (
 version text NOT NULL REFERENCES hkex.versions, family text NOT NULL,
 code text NOT NULL, label text NOT NULL, policy_hash text NOT NULL REFERENCES hkex.policies,
 PRIMARY KEY(version,family,code)
);
CREATE TABLE IF NOT EXISTS hkex.accepted (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 version text NOT NULL REFERENCES hkex.versions,
 accepted_at timestamptz NOT NULL DEFAULT now()
);
REVOKE ALL ON ALL TABLES IN SCHEMA hkex FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA hkex FROM PUBLIC;

CREATE OR REPLACE VIEW hkex.capture_metadata AS
 SELECT id,run_id,policy_hash,observed_at,raw_sha256,transform_sha256 FROM hkex.captures WHERE validation='validated';
REVOKE ALL ON hkex.capture_metadata FROM PUBLIC;
