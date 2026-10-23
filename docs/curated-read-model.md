# Hong Kong archival entity read model

This optional component transforms the qualified original Enigma release into a
persistent PostgreSQL model and a private query service. It does not enable a new
pack on the public mcp.hk gateway. The existing application starts without
PostgreSQL or its optional driver. Gateway REST/MCP tools, catalogue/UI integration,
current-government reconciliation, downloadable exports, production hosting and
offsite recovery remain separate milestones.

## Scope and identity

Primary organisations qualify through Hong Kong domicile, the source's explicit
`orgType=27` (registered non-HK), an issue listed on HK Main/GEM, or SFC firm records.
Include referenced officer organisations and people, plus SFC staff, to close the
selected relationships. Do not recursively expand foreign organisations' own
appointments. Former names cover primary organisations; dependency parties retain
archive name observations. These are archival organisations, including dissolved
and non-company bodies, rather than a verified current company register.

`PersonID` is the shared source identity namespace for both organisations and
people. Never merge records by name. Names retain original spelling, bilingual
variants and source fact IDs. Person surname/given-name fields stay separate; the
search display uses `surname, given names`. Search keys use Unicode NFKC/casefold
and trim outer whitespace. Search is literal prefix matching, including Chinese;
`%` and `_` are ordinary characters. A company can appear more than once when
several name facts match. Stable pagination is over matching name facts, not
inferred unique-name identities.

Identifiers preserve leading zeros. `webb:incorporation:<source domicile ID>` is
the original incorporation number, **not a verified CRN/BRN crosswalk**.
`webb:person` identifies the source entity; `sfc:ce_reference` preserves the
archived CE reference. Identity crosswalks to new official sources remain future
work. SFC staff role codes retain the source meanings: 0 = representative, 1 = responsible officer. Corporate licensing and officer appointments remain separate facts.

Personal identity numbers, birth/death fields and internal user fields are
not copied into this model.

## Facts and time

Version-isolated typed tables: `entities`, `entity_identifiers`, `entity_names`,
`officer_appointments`, `licences`, `licence_relationships`, `source_references`.
`curated.dataset_versions` records the immutable source hashes, transform identity,
counts and validation/restore evidence; `curated.published_releases` is an atomic
pack pointer. Every fact belongs to a version/schema and has its original record
key (or a source-table/column-derived name-fact key). The version manifest records
the release, original notice and attribution. This v1 control model stores source
capture lineage in the manifest; separate multi-source release/capture/run tables
are deferred until incremental official-source ingestion.

Original dates and source accuracy remain available alongside parsed dates. Source
accuracy codes are preserved as `year`, `month`, `unknown`, `year_end`, `month_end`,
or `day` where no reduction is declared. Invalid/zero dates retain raw text and a
null parsed date. Null bounds remain unknown. `JoinedY` does not manufacture an
appointment date. Former-name facts preserve the source change date as their
qualified upper boundary; there is no invented start date. Archive names have no
inferred effective-from date. Source update/check timestamps remain text with no
invented timezone or observation date. Download time does not make a fact current.

Relationship boundaries retain the original right-open convention. No exact
as-of reconstruction is offered: `asOf` returns `AS_OF_UNSUPPORTED`. The measured
archive has reversed officer date ranges; these remain source claims, are counted
in qualification, and are exposed through `temporalQualification`. An empty end
date does not prove a role is current. The response always labels `view=archive`
and `asOfSupported=false`.

## Build and publication

Use Python 3.12 for both the qualified importer and backend (the container pins this minor version), and an isolated owner-operated PostgreSQL database. Keep source SQL, PostgreSQL
files and backups outside Git, the gateway image and its SQLite/R2 checkpoint.
Use the [archive audit](enigma-audit.md) before staging; do not re-download/reimport
the archive for routine projection work.

```sh
.venv/bin/python -m pip install -r requirements.lock
.venv/bin/python -m pip install --no-deps -e .
.venv/bin/python -m pip install 'psycopg[binary]==3.2.13'
# Set CURATED_DSN to a dedicated local owner DSN, without printing credentials.
mcp-hk-curated stage --version enigma251227-hk-v1 \
  --workspace "$AUDIT_WORKSPACE" --container "$AUDIT_CONTAINER" \
  --database audit_enigma_checked
mcp-hk-curated inspect --version enigma251227-hk-v1 > original-inspection.json
```

The source container remains disconnected and bound to the audited datadir. Only
our fixed allowlisted SELECT projections run; the source session is read-only.
Rows stream through COPY. Private temporary spools contain only the selected
public fields. The in-memory closure set contains referenced IDs, not millions of
complete source objects. Source queries/streams and import SQL have explicit
timeouts. The inherited 20 GiB disk reserve applies to source-workspace checks;
preflight separately for destination, temporary spools, indexes, WAL and restore.
Reserve at least 12 GiB of additional scratch beyond the source workspace for this
measured model; a simultaneous full restore needs another model copy and WAL.

Versions are exclusive: a retry uses a fresh version and retains the unsuccessful
candidate/evidence. A staged candidate is never served. Validated row counts,
constraints and dictionary references must reconcile. A failed candidate never
changes the accepted pointer. Do not mutate accepted schemas; build a new version.
The serving role cannot write them. Retain published versions for at least the
48-hour cursor window; this implementation does not delete versions automatically.

Back up all retained curated schemas/control metadata with a matching PG client:

```sh
mcp-hk-curated backup --container "$PG_CONTAINER" --database curated \
  --version enigma251227-hk-v1 --artifact "$BACKUP_PATH" > backup-receipt.json
# Create a fresh isolated target database; restore refuses checksum mismatch.
mcp-hk-curated restore --container "$RESTORE_CONTAINER" --database curated_restore \
  --artifact "$BACKUP_PATH" --backup-sha256 "$BACKUP_SHA256"
# CURATED_RESTORE_DSN names that independent database.
mcp-hk-curated accept-restore --version enigma251227-hk-v1 \
  --backup-sha256 "$BACKUP_SHA256"
mcp-hk-curated publish --version enigma251227-hk-v1
```

`accept-restore` compares all seven table counts, validated constraints,
dictionaries, temporal diagnostics and 30 deterministic row hashes per table.
Database identity uses the actual cluster system identifier and database name,
not DSN string inequality. This is aggregate/sample verification plus the complete
backup checksum, not an all-row cryptographic equality proof or offsite recovery.

For a disk-constrained disaster-recovery rehearsal, retain `inspect` output with
`backupSha256` added from the backup receipt before taking the original disposable
database offline. On the restored owner DSN use `accept-restore --source-receipt
original-receipt.json --artifact "$BACKUP_PATH"`. It verifies artifact bytes,
distinct database identity and the same comparisons, then validates the restored
candidate. Treat receipts as trusted operator evidence, not remote attestations.

Publication is transactional and serialized. Roll back by publishing a previously
accepted version; signed cursors continue using their original retained version.
No transaction remains open across pages. A concrete production retention,
publication cadence, encrypted offsite backup and hosting/cost decision are still
required before deployment. One measured version is about 6.25 GB including its
indexes; three retained/staging copies need about 18.8 GB before WAL, backups and
restore headroom. The existing gateway's sub-GB checkpoint cannot hold this model.

## Read-only service

Provision a dedicated non-superuser login without role/database creation powers,
and set its password through the operator's secret flow. `grant-reader --role
curated_reader` grants USAGE/SELECT only and defaults its transactions to read-only.
Reapply after staging a new version. The reader independently rejects elevated
roles, schema CREATE, ownership or table-write privileges.

Configure separate `CURATED_DSN` (serving role), `CURATED_BACKEND_TOKEN` and
`CURATED_CURSOR_SECRET` (each secret at least 32 characters). Start
`mcp-hk-curated-backend`. No source credentials are used by the service. Private
routes require the dedicated bearer token, including `/health`:

- `GET /v1/companies?name=香港` or explicit `namespace`/`value`.
- `GET /v1/entities/{source-id}`.
- `GET /v1/entities/{source-id}/{names|officers|licences|licence_relationships}`.

Default page size 20, max 100. Prefix length 2–200, cursor max 2048 characters.
Queries use fixed parameterized SQL, C-collated B-tree prefix/range indexes,
release-pinned signed cursors, four query slots, a two-second SQL timeout, 250 ms
lock timeout and 2 MiB output cap. Cursor expiry is 48 hours. Missing/expired/
unavailable/timeout states remain distinct. The backend access log is disabled
so query terms do not enter URL logs. It is a private backend: gateway budgets,
public envelopes and MCP parity are the next adapter milestone.

For local Compose use `deploy/curated/compose.yaml`: PostgreSQL has no published
host port; the optional `serve` profile binds the backend only to loopback. Supply
all required variables before Compose interpolation, even when starting only the
database. The database is an ordinary persistent volume; keep credentials out of
committed files. This configuration is local development, not production hosting.

## Verification

```sh
CURATED_REQUIRE_DB=1 CURATED_TEST_DSN="$TEST_DSN" \
  CURATED_TEST_CONTAINER="$OWNED_PG_CONTAINER" \
  bash scripts/check.sh all
```

The dedicated CI lane supplies PostgreSQL and fails when its service/container is
unavailable. It tests normalization, identity, bilingual prefixes, physical backup/
restore, publication/rollback, signed cursor continuity, real statement/lock
limits, SELECT-only privileges and private HTTP/library parity. Ordinary base
Python CI runs without the optional driver/database. No archive is downloaded in
CI. Full-scale receipts are separate from these reproducible synthetic contracts.

Full-scale local evidence: [23 October qualification](data/enigma-hk-read-model-20261023.md).
