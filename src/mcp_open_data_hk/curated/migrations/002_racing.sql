-- Independent additive migration; never depends on sibling source schemas.
CREATE SCHEMA IF NOT EXISTS racing;
REVOKE ALL ON SCHEMA racing FROM PUBLIC;
CREATE TABLE IF NOT EXISTS racing.policies (
 digest text PRIMARY KEY CHECK (digest ~ '^[a-f0-9]{64}$'), record jsonb NOT NULL,
 active boolean NOT NULL DEFAULT false, installed_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS racing.versions (
 version text PRIMARY KEY, state text NOT NULL CHECK(state IN ('staging','validated','restore-qualified','published')),
 policy_digest text NOT NULL REFERENCES racing.policies, manifest jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT now(), restore_proof jsonb
);
CREATE TABLE IF NOT EXISTS racing.accepted (
 pack text PRIMARY KEY CHECK(pack='hkjc_racing'), version text NOT NULL REFERENCES racing.versions,
 published_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS racing.captures (
 version text REFERENCES racing.versions, capture_id text NOT NULL,
 family text NOT NULL, canonical_location text NOT NULL, retrieved_at timestamptz NOT NULL,
 raw_sha256 text NOT NULL CHECK(raw_sha256 ~ '^[a-f0-9]{64}$'), transform_sha256 text NOT NULL CHECK(transform_sha256 ~ '^[a-f0-9]{64}$'),
 run_id text NOT NULL, policy_digest text NOT NULL REFERENCES racing.policies,
 source_timezone text NOT NULL, source_date_precision text NOT NULL,
 validation jsonb NOT NULL, PRIMARY KEY(version,capture_id)
);
CREATE TABLE IF NOT EXISTS racing.meetings (
 version text REFERENCES racing.versions, meeting_id text NOT NULL, season text NOT NULL,
 local_date date NOT NULL, venue text NOT NULL CHECK(venue IN ('ST','HV')),
 status text NOT NULL CHECK(status IN ('scheduled','in_progress','completed','abandoned','postponed','cancelled')),
 capture_id text NOT NULL, PRIMARY KEY(version,meeting_id),
 FOREIGN KEY(version,capture_id) REFERENCES racing.captures
);
CREATE TABLE IF NOT EXISTS racing.races (
 version text, race_id text NOT NULL, meeting_id text NOT NULL, race_number integer NOT NULL CHECK(race_number BETWEEN 1 AND 20),
 distance_m integer CHECK(distance_m > 0), surface text, course text, going text, class_raw text,
 scheduled_raw text, actual_raw text, time_precision text NOT NULL,
 status text NOT NULL, capture_id text NOT NULL, PRIMARY KEY(version,race_id),
 UNIQUE(version,meeting_id,race_number), FOREIGN KEY(version,meeting_id) REFERENCES racing.meetings,
 FOREIGN KEY(version,capture_id) REFERENCES racing.captures
);
CREATE TABLE IF NOT EXISTS racing.participants (
 version text REFERENCES racing.versions, participant_id text NOT NULL,
 kind text NOT NULL CHECK(kind IN ('horse','jockey','trainer')), source_id text NOT NULL,
 name_en text, name_zh text, capture_id text NOT NULL, PRIMARY KEY(version,participant_id),
 UNIQUE(version,kind,source_id), FOREIGN KEY(version,capture_id) REFERENCES racing.captures
);
CREATE TABLE IF NOT EXISTS racing.runners (
 version text, race_id text NOT NULL, participant_id text NOT NULL,
 horse_number text NOT NULL, draw text, weight_lb numeric, claim_lb numeric,
 status text NOT NULL, capture_id text NOT NULL,
 PRIMARY KEY(version,race_id,participant_id), UNIQUE(version,race_id,horse_number),
 FOREIGN KEY(version,race_id) REFERENCES racing.races,
 FOREIGN KEY(version,participant_id) REFERENCES racing.participants,
 FOREIGN KEY(version,capture_id) REFERENCES racing.captures
);
CREATE TABLE IF NOT EXISTS racing.results (
 version text, fact_id text NOT NULL, revision text NOT NULL, supersedes text,
 race_id text NOT NULL, participant_id text NOT NULL, placing_raw text NOT NULL,
 "placing" integer CHECK("placing">0), status text NOT NULL, dead_heat boolean NOT NULL,
 margin_raw text, time_raw text, time_seconds numeric, time_precision text,
 capture_id text NOT NULL, PRIMARY KEY(version,fact_id,revision),
 FOREIGN KEY(version,race_id,participant_id) REFERENCES racing.runners,
 FOREIGN KEY(version,capture_id) REFERENCES racing.captures
);
CREATE TABLE IF NOT EXISTS racing.profile_observations (
 version text, participant_id text NOT NULL, capture_id text NOT NULL,
 effective_date date, attributes jsonb NOT NULL, PRIMARY KEY(version,participant_id,capture_id),
 FOREIGN KEY(version,participant_id) REFERENCES racing.participants,
 FOREIGN KEY(version,capture_id) REFERENCES racing.captures
);
CREATE TABLE IF NOT EXISTS racing.sectionals (
 version text, fact_id text NOT NULL, revision text NOT NULL,
 race_id text NOT NULL, participant_id text, kind text NOT NULL CHECK(kind IN ('race','runner')),
 segment integer NOT NULL CHECK(segment>0), distance_m integer NOT NULL CHECK(distance_m>0),
 seconds numeric NOT NULL, precision_raw text NOT NULL, capture_id text NOT NULL,
 PRIMARY KEY(version,fact_id,revision), FOREIGN KEY(version,race_id) REFERENCES racing.races,
 FOREIGN KEY(version,participant_id) REFERENCES racing.participants,
 FOREIGN KEY(version,capture_id) REFERENCES racing.captures,
 CHECK ((kind='race' AND participant_id IS NULL) OR (kind='runner' AND participant_id IS NOT NULL))
);
CREATE TABLE IF NOT EXISTS racing.dividends (
 version text REFERENCES racing.versions, fact_id text NOT NULL, revision text NOT NULL,
 race_ids text[] NOT NULL, pool text NOT NULL, combination text[] NOT NULL,
 semantics text NOT NULL CHECK(semantics IN ('ordered','unordered')),
 amount_hkd numeric, stake_hkd numeric NOT NULL CHECK(stake_hkd>0),
 status text NOT NULL CHECK(status IN ('payout','refund','carryover','jackpot')),
 capture_id text NOT NULL, PRIMARY KEY(version,fact_id,revision),
 FOREIGN KEY(version,capture_id) REFERENCES racing.captures
);
CREATE TABLE IF NOT EXISTS racing.family_facts (
 version text REFERENCES racing.versions, family text NOT NULL CHECK(family IN ('barrier_trials','comments','jockey_rankings','trainer_rankings','track_conditions','jackpots')),
 fact_id text NOT NULL, revision text NOT NULL, source_period text, metric text,
 unit text, attributes jsonb NOT NULL, capture_id text NOT NULL,
 PRIMARY KEY(version,family,fact_id,revision), FOREIGN KEY(version,capture_id) REFERENCES racing.captures
);
CREATE TABLE IF NOT EXISTS racing.observations (
 version text REFERENCES racing.versions, series_id text NOT NULL, race_id text NOT NULL,
 market text NOT NULL, selection text NOT NULL, source_time_raw text, source_time_precision text NOT NULL,
 observed_at timestamptz NOT NULL, sequence bigint NOT NULL,
 kind text NOT NULL CHECK(kind IN ('odds','pool_investments','changes')), value numeric,
 raw_unit text NOT NULL, state text NOT NULL CHECK(state IN ('open','suspended','closed','corrected')),
 capture_id text NOT NULL, PRIMARY KEY(version,series_id,sequence,selection),
 FOREIGN KEY(version,race_id) REFERENCES racing.races,
 FOREIGN KEY(version,capture_id) REFERENCES racing.captures
);
CREATE TABLE IF NOT EXISTS racing.coverage (
 version text REFERENCES racing.versions, family text NOT NULL, group_id text NOT NULL,
 scope text NOT NULL CHECK(scope IN ('season','meeting','race','family')),
 expected_ids text[] NOT NULL, observed_ids text[] NOT NULL,
 complete boolean NOT NULL, proof jsonb NOT NULL, PRIMARY KEY(version,family,group_id)
);
CREATE TABLE IF NOT EXISTS racing.jobs (
 operation text NOT NULL, scheduled_for timestamptz NOT NULL, run_id text UNIQUE NOT NULL,
 state text NOT NULL CHECK(state IN ('running','partial','failed','unknown','unchanged','complete')),
 checkpoint jsonb NOT NULL DEFAULT '{}', started_at timestamptz NOT NULL DEFAULT now(),
 PRIMARY KEY(operation,scheduled_for)
);
CREATE TABLE IF NOT EXISTS racing.budgets (
 utc_day date PRIMARY KEY, attempts integer NOT NULL DEFAULT 0,
 reserved_bytes bigint NOT NULL DEFAULT 0, hold_until timestamptz
);
CREATE TABLE IF NOT EXISTS racing.requests (
 request_id text PRIMARY KEY, run_id text NOT NULL REFERENCES racing.jobs(run_id),
 route_hash text NOT NULL, reserved_at timestamptz NOT NULL DEFAULT now(),
 settled_at timestamptz, outcome text NOT NULL DEFAULT 'unknown', bytes bigint NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS racing_races_meeting ON racing.races(version,meeting_id,race_id);
CREATE INDEX IF NOT EXISTS racing_results_race ON racing.results(version,race_id,fact_id,revision);
CREATE INDEX IF NOT EXISTS racing_observations_time ON racing.observations(version,race_id,market,observed_at,series_id,sequence,selection);
REVOKE ALL ON ALL TABLES IN SCHEMA racing FROM PUBLIC;
CREATE TABLE IF NOT EXISTS racing.source_state (
 source text PRIMARY KEY CHECK(source='hkjc'), hold_until timestamptz
);
INSERT INTO racing.source_state(source) VALUES('hkjc') ON CONFLICT DO NOTHING;
-- Freeze facts after validation, including INSERT. Revocation changes policy active only.
CREATE OR REPLACE FUNCTION racing.guard_facts() RETURNS trigger LANGUAGE plpgsql AS $$
DECLARE selected_version text;
BEGIN
 IF TG_OP='DELETE' THEN selected_version := OLD.version; ELSE selected_version := NEW.version; END IF;
 IF TG_OP<>'INSERT' AND EXISTS(SELECT 1 FROM racing.versions WHERE version=OLD.version AND state<>'staging') THEN
  RAISE EXCEPTION 'RACING_IMMUTABLE_VERSION';
 END IF;
 IF EXISTS(SELECT 1 FROM racing.versions WHERE version=selected_version AND state<>'staging') THEN
  RAISE EXCEPTION 'RACING_IMMUTABLE_VERSION';
 END IF;
 RETURN CASE WHEN TG_OP='DELETE' THEN OLD ELSE NEW END;
END $$;
DO $$ DECLARE t text; BEGIN
 FOREACH t IN ARRAY ARRAY['captures','meetings','races','participants','runners','results','profile_observations','sectionals','dividends','family_facts','observations','coverage'] LOOP
  IF NOT EXISTS(SELECT 1 FROM pg_trigger WHERE tgname='racing_freeze_'||t AND tgrelid=('racing.'||t)::regclass) THEN
   EXECUTE format('CREATE TRIGGER %I BEFORE INSERT OR UPDATE OR DELETE ON racing.%I FOR EACH ROW EXECUTE FUNCTION racing.guard_facts()', 'racing_freeze_'||t,t);
  END IF;
 END LOOP;
END $$;
REVOKE ALL ON ALL TABLES IN SCHEMA racing FROM PUBLIC;
-- Optional private source bytes require explicit policy raw-retention permission.
CREATE TABLE IF NOT EXISTS racing.capture_buffer (
 capture_id text PRIMARY KEY, run_id text NOT NULL REFERENCES racing.jobs(run_id),
 family text NOT NULL, route text NOT NULL, raw_sha256 text NOT NULL,
 body bytea, retrieved_at timestamptz NOT NULL,
 expires_at timestamptz NOT NULL, policy_digest text NOT NULL REFERENCES racing.policies
);
REVOKE ALL ON racing.capture_buffer FROM PUBLIC;
