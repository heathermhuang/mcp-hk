-- Already-released Webb archive. Independent from fresh HKEX policy/state.
CREATE SCHEMA IF NOT EXISTS webb_sdi;
REVOKE ALL ON SCHEMA webb_sdi FROM PUBLIC;
CREATE TABLE IF NOT EXISTS webb_sdi.versions (
 version text PRIMARY KEY, state text NOT NULL CHECK(state IN ('staging','validated','restore-qualified','published')),
 manifest jsonb NOT NULL, restore_proof jsonb, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS webb_sdi.accepted (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 version text NOT NULL REFERENCES webb_sdi.versions,
 published_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS webb_sdi.issues (
 version text NOT NULL REFERENCES webb_sdi.versions, id bigint NOT NULL,
 issuer_id bigint NOT NULL, source jsonb NOT NULL, PRIMARY KEY(version,id)
);
CREATE TABLE IF NOT EXISTS webb_sdi.filings (
 version text NOT NULL REFERENCES webb_sdi.versions, id bigint NOT NULL,
 serial text, legacy_filing text, issue_id bigint NOT NULL, issuer_id bigint NOT NULL,
 stock_code text NOT NULL, issuer_name text NOT NULL, issuer_search_key text COLLATE "C" NOT NULL,
 event_date date, signed_date date, source jsonb NOT NULL, PRIMARY KEY(version,id),
 FOREIGN KEY(version,issue_id) REFERENCES webb_sdi.issues(version,id)
);
CREATE UNIQUE INDEX IF NOT EXISTS webb_sdi_serial ON webb_sdi.filings(version,serial) WHERE serial IS NOT NULL;
CREATE INDEX IF NOT EXISTS webb_sdi_stock ON webb_sdi.filings(version,stock_code,issuer_id,id);
CREATE INDEX IF NOT EXISTS webb_sdi_issuer ON webb_sdi.filings(version,issuer_id,(COALESCE(event_date,'0001-01-01'::date)) DESC,id DESC);
CREATE INDEX IF NOT EXISTS webb_sdi_prefix ON webb_sdi.filings(version,issuer_search_key,issuer_id);
CREATE TABLE IF NOT EXISTS webb_sdi.capacities (
 version text NOT NULL, filing_id bigint NOT NULL, code text NOT NULL,
 position_code text NOT NULL, shares text, PRIMARY KEY(version,filing_id,code,position_code),
 FOREIGN KEY(version,filing_id) REFERENCES webb_sdi.filings(version,id)
);
CREATE TABLE IF NOT EXISTS webb_sdi.events (
 version text NOT NULL, filing_id bigint NOT NULL, position_code text NOT NULL,
 source jsonb NOT NULL, PRIMARY KEY(version,filing_id,position_code),
 FOREIGN KEY(version,filing_id) REFERENCES webb_sdi.filings(version,id)
);
CREATE TABLE IF NOT EXISTS webb_sdi.dictionaries (
 version text NOT NULL REFERENCES webb_sdi.versions, family text NOT NULL,
 code text NOT NULL, label text, source jsonb NOT NULL, PRIMARY KEY(version,family,code)
);
REVOKE ALL ON ALL TABLES IN SCHEMA webb_sdi FROM PUBLIC;
