-- Add source-declared price kinds and filing-scoped control relationships.
-- Aggregate before/after interest rows do not necessarily specify capacity.
ALTER TABLE hkex.interests ALTER COLUMN capacity_code DROP NOT NULL;
ALTER TABLE hkex.securities ADD COLUMN IF NOT EXISTS issued_shares numeric;
ALTER TABLE hkex.securities ADD COLUMN IF NOT EXISTS issued_shares_raw text;
ALTER TABLE hkex.particulars ADD COLUMN IF NOT EXISTS security_id text;
ALTER TABLE hkex.particulars ADD COLUMN IF NOT EXISTS capacity_before text;
ALTER TABLE hkex.particulars ADD COLUMN IF NOT EXISTS capacity_after text;
ALTER TABLE hkex.particulars ADD COLUMN IF NOT EXISTS prices jsonb NOT NULL DEFAULT '[]';
ALTER TABLE hkex.particulars ADD COLUMN IF NOT EXISTS position text NOT NULL DEFAULT 'unknown';
DO $$ BEGIN
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='hkex.securities'::regclass AND conname='hkex_issued_raw_pair') THEN
  ALTER TABLE hkex.securities ADD CONSTRAINT hkex_issued_raw_pair CHECK((issued_shares IS NULL)=(issued_shares_raw IS NULL));
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='hkex.particulars'::regclass AND conname='hkex_prices_array') THEN
  ALTER TABLE hkex.particulars ADD CONSTRAINT hkex_prices_array CHECK(jsonb_typeof(prices)='array');
 END IF;
 IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='hkex.particulars'::regclass AND conname='hkex_event_position') THEN
  ALTER TABLE hkex.particulars ADD CONSTRAINT hkex_event_position CHECK(position IN ('long','short','unknown'));
 END IF;
END $$;
CREATE TABLE IF NOT EXISTS hkex.controls (
 version text NOT NULL, serial text NOT NULL, line text NOT NULL,
 controlled_party_ref text NOT NULL, controlling_party_ref text NOT NULL,
 percentage_control numeric, percentage_control_raw text,
 direct_interest text NOT NULL CHECK(direct_interest IN ('yes','no','unknown')),
 PRIMARY KEY(version,serial,line),
 FOREIGN KEY(version,serial) REFERENCES hkex.filings(version,serial),
 FOREIGN KEY(version,serial,controlled_party_ref) REFERENCES hkex.parties(version,serial,ref),
 FOREIGN KEY(version,serial,controlling_party_ref) REFERENCES hkex.parties(version,serial,ref),
 CHECK((percentage_control IS NULL)=(percentage_control_raw IS NULL)),
 CHECK(percentage_control BETWEEN 0 AND 100),
 CHECK(controlled_party_ref<>controlling_party_ref)
);
REVOKE ALL ON hkex.controls FROM PUBLIC;
