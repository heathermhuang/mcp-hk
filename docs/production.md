# Production: Cloudflare Containers + R2

The Python service remains the data/MCP implementation. A small Cloudflare Worker
serves static assets and forwards API/MCP traffic to one named Durable Object and
one `standard-1` container (half a vCPU, 4 GiB memory, maximum one instance). It
sleeps after ten idle minutes, longer than the five-minute resource review cadence. All state needed to recover accepted data is restored from a private R2
checkpoint on startup; the container's local disk is not considered durable.

## Deploy

```sh
cd deploy/cloudflare
npm ci
npm run types
npm run check
python3 ../../scripts/build_discovery.py
wrangler deploy --secrets-file .ops-secrets.json --var RELEASE_COMMIT:<verified-git-sha>
```

`OPS_TOKEN` is the dedicated maintenance/edge credential. Keep it in the ignored,
owner-only `.ops-secrets.json` file and the Worker secret binding; never place it
in a URL, image layer, repository, connection example or log. The container receives
it at runtime. Public data clients do not need this secret or any server API key.

The initial seed is a SQLite backup-API copy plus retained content-addressed source
captures, packed as a tar.gz with SHA256. `scripts/prepare_seed.py` restore-tests it
before upload. From the repository root:

```sh
uv run python scripts/prepare_seed.py
uv run python scripts/cloudflare_ops.py seed
uv run python scripts/cloudflare_ops.py restore-test
```

The operator helper reads its credential from the ignored file and refuses redirects
or destinations other than the known mcp.hk/Worker origins. Recovery validates the
outer checksum, archive paths/file types, source capture hashes, SQLite integrity,
and the presence of both accepted data packs before replacing the database. It runs
before the HTTP port opens. No startup model calls or full government re-import is
required to recover a sleeping or replaced container.

## Scheduled operations

Cloudflare Cron Triggers invoke the single controller, protected by a durable
maintenance lease:

| Operation | UTC cron | Hong Kong time |
|---|---|---|
| Backup | `0 1 * * *` | Daily 09:00 |
| Restaurant refresh + backup | `0 2 * * *` | Daily 10:00 |
| Population check + backup | `0 3 * * SUN` | Sunday 11:00 |
| Reconciled catalogue sync + backup | `0 4 * * SUN` | Sunday 12:00 |
| Cadence-aware resource review + backup | `2-59/5 * * * *` | Every five minutes at minutes 2,7,...57 |

Every successful operation stores an immutable version under `backups/`, then
publishes `latest.snapshot.tar.gz` and a manifest. Only complete, validated imports
can advance an accepted generation. A failed refresh retains the prior data and
backup, and records failure in the durable maintenance status. Re-run only after
investigating a changed condition. There is no model-based recurring automation.

Daily/weekly jobs are recorded durably before attempting the shared lease. If
another job holds the lease, the next resource tick services the oldest pending
job instead of starting another resource batch. Selection happens only after
acquiring the normal lease. Each of the four infrequent jobs retains its latest
scheduled time and pending/success/failed state in private diagnostics. Duplicate
cron delivery does not requeue a settled job. Known source/checkpoint failures
settle as failed and are not retried by resource ticks; the next regular schedule
or an investigated operator action is required. Interrupted requests never clear
leases, and a newer schedule cannot be erased by an older completion.

R2 versions are retained for 30 days. Local pruning retains active and previous
generations, all recently retired generations for a 48-hour pagination window,
associated source captures, and unexpired address cache entries. Full R2 checkpoints
recover database and captures together. Test an offsite restore after deployment:

```sh
uv run python scripts/cloudflare_ops.py backup
uv run python scripts/cloudflare_ops.py restore-test
uv run python scripts/cloudflare_ops.py status
```

## Boundaries and operational checks

- Only the one named controller can forward traffic. It enforces 60 requests/minute/IP,
  50,000 API/MCP requests/day and 10,000 address-tool requests/day in durable storage.
  Static assets do not start the container. Address budgets conservatively count
  tool requests, including cache hits, and therefore survive container restarts.
- The Worker replaces forwarded client identity and injects an edge credential.
  Container edge mode rejects requests without that credential. No forwarded header
  supplied by a public caller is trusted directly by the Python process.
- `__ops` endpoints require a constant-time credential comparison. They are not MCP
  tools or public OpenAPI operations. Unsigned traffic receives 404.
- The backup bucket is private. `/api/v1/operations` exposes only backup and schedule
  metadata, never archive bytes or credentials. Source failure/freshness remain on
  `/api/v1/status` independently of service health.
- Invocation logs are disabled so raw address query strings are not retained by the
  Worker invocation logger. Application access logging remains disabled. Structured
  operation receipts contain no user query or credential.
- `/healthz` indicates process health; `/readyz` requires accepted restaurant and
  population packs; `X-Mcp-Release` identifies the deployed source commit.
- Cloudflare manages public TLS for the custom domains. `www.mcp.hk` redirects to
  `mcp.hk`. The registrar delegation must match the owning Cloudflare zone.

For rollback, deploy the previously verified image/Worker source and retain the R2
checkpoint. For data rollback, restore a previously validated archive through the
operator seed path while the service is stopped, then restart and verify readiness,
source counts, MCP tool calls and the browser journey. Do not overwrite a live WAL
database. A code rollback does not itself reverse data.

Hosting is metered on the existing Cloudflare account; maximum one instance and the
durable daily request budgets bound application capacity. They are not a provider
hard billing cap. Review actual usage after launch before raising limits.

## Independent Plate.hk pack

The adapter reads Plate.hk’s existing public API; Plate.hk owns its auction-data
refreshes. No second auction crawler or refresh schedule is installed in mcp.hk.
Validated queries have a 300-second cache, capped at 200 cached responses and 5,000
uncached reads per UTC day, with three concurrent source reads. Cache entries and
source-check receipts use the existing SQLite store and backup path. The new pack
is optional for readiness: Plate.hk downtime does not disable the government packs.
An expired query cache never disguises a provider failure as an empty result.

Expanded inventory recovery uses streamed R2 checkpoints, capped at 150 MB compressed, 500 MB SQLite and 750 MB total restored bytes. Checkpoints carry the authenticated producer checksum; bootstrap independently verifies it. Fixed-length streaming rejects truncated/overflowed uploads before recovery pointers advance. The first expanded restore test recovered a 55 MB checkpoint; see resource contracts for cache and query bounds.

The full audit grew its restore-tested checkpoint to 71 MB before finishing. Streaming remains bounded without holding the archive in Worker memory; the larger bound accommodates full receipts and two metadata generations. The host remains one container; its current size is `standard-1`.

After uploading a restore-tested operator seed, `scripts/cloudflare_ops.py restart`
restarts only the named mcp.hk container against the exact accepted checkpoint SHA.
The private authenticated endpoint checks the R2 object and acquires the maintenance
lease before stopping; the next request performs normal authenticated bootstrap.
A missing or changed checkpoint prevents the stop. Use this controlled recovery
path to adopt a new inventory seed without waiting for an incidental idle shutdown.

Private `/__ops/diagnostics` reports maintenance lease expiry and whether a seed
lease is held, without the lease owner or credentials. Seed errors identify lease,
upload or release phase to the authenticated operator; credentials are redacted.
A lease conflict returns 409 and never changes the accepted recovery pointer.

Hosted checkpoint responses use a transform stream. Workerd rejected native
`pipeTo()` between that response and `FixedLengthStream`, although direct operator
seed streams worked. Checkpoint transfer therefore uses an explicit bounded
reader/writer pump, aborts both sides on failure, and advances recovery pointers only
after immutable storage succeeds. Regression tests cover the unsupported pipe and
retain the previous pointer on truncation.

Checkpoint copies expand compressed inventory/schema metadata to equivalent JSON
text before shared archive compression. Live metadata and the bounded record cache
are unchanged. The measured archive fell from 82.7 MB to 46.8 MB; the restored SQLite
file grew to 244 MB, within the existing 500 MB bound. Both metadata tables retained
identical logical checksums. Cold MCP startup still requires a 120-second client
window; a real cold Codex test passed after the default 30-second window timed out.

Transient container proxy responses (plain-text 502/503/504) are converted to the
JSON `SERVICE_RECOVERING` envelope with `Retry-After`. Existing JSON source errors
keep their own codes. The coverage explorer retries only that recovery signal,
with at most three attempts; out-of-order searches/resource lists cannot replace
newer selections. It never retries unchanged provider or schema failures.

### Public pages and language

`/docs` serves Swagger UI 5.34.0 from the same-origin `/assets` paths, with its
initializer in `api-docs.js`. The API's `script-src 'self'` policy remains intact;
no runtime CDN, inline-script allowance or external schema validator is needed.
`/redoc` redirects to this reference. Vendored files originate from the npm
`swagger-ui-dist@5.34.0` archive. Its Apache-2.0 license, NOTICE and bundled
third-party license notices are preserved alongside the assets.
SHA-256: bundle `3f6abf70480db7e07914df4c98a77385f22ea585eaf457a3e6415ba0eae2d167`;
CSS `c3cfe8248c4b0b89673600fb829924eafbac6de4bc4b2b06f5f5243483074d0a`.
For upgrades, obtain a pinned package, preserve its license, update these hashes,
and verify a real docs request under the production security headers.

The homepage reads `/assets/overview.json` for dated catalogue, resource and
validated-queryable counts. The Worker serves a compact R2 summary without calling
the query container; if it is missing or R2 is unavailable, a verified, dated release
snapshot is served from static assets. The original packs are example workflows, not the full library. Topic links
open the resource explorer with a search query. A failed coverage request shows an
unavailable state rather than a hard-coded count.

All public landing/demo/explorer pages share `i18n.js` and `translations.js`.
`?lang=en` or `?lang=zh-Hant` takes precedence over the saved language; the switch
updates both the URL and local preference. Internal links retain the language and
existing query parameters. UI copy, status messages, form labels and connection help
are translated; original records, source titles and API identifiers retain source text.

The existing maintenance jobs publish the summary after saving their checkpoints.
A failed summary update retains the prior publication and is recorded under
`maintenanceStatus.overview`; the UI always shows the summary timestamp. To republish
manually, run `python scripts/cloudflare_ops.py publish-overview` from the project
environment. No browser request triggers publication or warms the container. Source
status is requested only when the Sources page is opened. Actual resource queries
and the detailed coverage explorer still use the backend.


The resource maintenance job now chooses due eligible sources rather than advancing
through held IDs. Each run has a 256-attempt/90-second bound, six concurrent reviews (two per host),
and a persisted 50,000-attempt UTC-day maintenance budget. Two independent source
slots remain available to interactive reads. Short recovery batches save an accepted
checkpoint after each run; the legacy recovery name is an alias for one such batch. Query-cache expiry and cadence-based review debt are
reported separately. Source status also exposes failed/overdue government refreshes
while retaining accepted snapshots and source-label quality counts.


A held maintenance lease returns operator HTTP 409 `MAINTENANCE_BUSY` with
`Retry-After`, rather than a generic Worker 500. The helper prints the bounded
code/deadline without response bodies or credentials. Wait for expiry; never clear
a lease just because a rollout interrupted an operator response. Other maintenance
failures return a structured, redacted 503 and retain their owning failure receipt.


Maintenance also checks the backend's source-review policy handshake before
acquiring its lease. A Worker whose matching data image is still rolling out gets
`SERVICE_RECOVERING`/503 without taking a lease. The Python/Worker policy contract
is regression-tested, so a source-policy update cannot silently start maintenance
against the previous image. Active leases still expire naturally and are never
cleared merely to speed a deployment.

## Coordinating container and controller releases

Pause the resource cron using `wrangler triggers deploy` with a temporary config
that removes only that cron; preserve the other four schedules. Cloudflare cron
changes can take up to 15 minutes to propagate. Wait for both propagation and any
existing job's accepted checkpoint/lease release before replacing Worker or
Durable Object code. Never clear a lease after an interrupted response.

Static `X-Mcp-Release` headers do not prove controller adoption. Read the private
controller diagnostics and the actual backend `/healthz` policy. A controller can
continue executing an older release after the public Worker changes. A matching
policy guard protects maintenance only after that controller version is active.
Keep the temporary four-cron configuration throughout the Worker/container rollout,
verify both versions, and then restore the original five schedules using
`wrangler triggers deploy` with the checked-in configuration.

Retain uncertain/failed receipts and the last accepted R2 checkpoint. Do not label
a completed source-review phase as a saved checkpoint. After adoption, resume only
the missing bounded review work and test a fresh accepted snapshot's checksum,
SQLite integrity, accepted packs and source registry in isolation.

Reference: https://developers.cloudflare.com/workers/configuration/cron-triggers/

## Optional agent authorization state

The `AgentAuth` SQLite Durable Object, bound as `AGENT_AUTH`, is separate from the
data container and R2 backups. Its durable signing key and revocation/claim state
survive Worker changes. Deploy migration `v2-agent-auth` once; retain that migration
and namespace in later rollouts. Anonymous public reads remain available if the
optional auth service is unavailable. See [agent-auth.md](agent-auth.md) for
credential lifetimes, private bulk revocation, recovery caveats and smoke checks.

## Official company observations (P6)

The dedicated curated host owns `curated.official_*` state. Its independent
`mcp-hk-official.timer` runs at 05:00 UTC daily (13:00 HKT), with persistent catch-up
and a 15-minute service deadline. Install the checked-in units from
`deploy/curated/systemd/` after deploying the reviewed source to `/opt/mcp-hk`.
`run-official.sh` uses the existing owner-only `/etc/mcp-hk-curated/owner.env` inside
an ephemeral collector container on the existing private Docker network; the public
backend retains its SELECT-only role. Grant SELECT on new curated tables directly
to that existing role after schema creation. Do not put owner credentials in the
backend or gateway. No new host or paid service is required.

The collector enforces 48 requests, 64 MiB response bytes, six weekly CSV/XLS pairs,
four lender CSV/XLS pairs and at most 20 exact tracked BRN address reads per run.
A source failure retains the accepted official pointer. Individually rejected
addresses retain their previous observation and appear as explicit gaps while
independent verified weekly/lender files may publish. Discovered weeks and accepted
weeks are distinct; previous published versions remain available. Interrupted
`running` receipts are evidence of an incomplete run, never success. The advisory
writer lock is released by connection termination, without operator lease clearing.

`backup-official.sh` creates an immutable custom-format logical dump of the curated
metadata schema, including all official source bytes, verification bytes, records,
run receipts, versions and accepted pointer. It verifies its archive index and
retains local copies for 30 days. The existing weekly provider snapshot policy
covers `/srv/mcp-hk-curated/` and these database/backups; do not claim a future
provider snapshot has occurred. Release qualification copies a fresh dump to the
existing private R2 bucket, retrieves and checksum-verifies it, then restores into
a fresh isolated database. The original immutable Enigma model and complete export
retain their separately qualified backup/download paths. Daily collection stops
before a run if host free space falls below 10 GiB.

For data rollback, invoke the collector image with the existing owner configuration
and `python -m mcp_open_data_hk.curated.official_ingest --rollback <accepted-version>`.
The writer lock and version-existence check protect the pointer; no historical
capture is deleted. Verify search/get parity against the chosen version afterward.
To suspend only these updates, stop `mcp-hk-official.timer`; do not alter gateway
schedules or unrelated host timers. A failed scheduled collection or backup makes
the systemd unit fail and leaves its durable run receipt and journal evidence.

### Company maintenance continuation

The additive `curated/migrations/001_official_maintenance.sql` retains the original
captures, versions and pointers and labels their original transform. New captures
include the explicit transform code hash in their identity, separately from raw
SHA-256. The packaged migration is applied by the owner collector; serving roles
remain SELECT only. Grant SELECT on the additional tables before swapping readers.

`python -m mcp_open_data_hk.curated.official_ingest` accepts `freshness` (default),
`backfill`, `addresses`, `publish`, `plan` and `verify-run`. Pass an explicit
`--scheduled-for` occurrence with timezone for ordinary scheduler work; duplicate
family/operation/occurrence cannot execute again. A running receipt left by an
interruption stays unknown until the owning process is known to have stopped.
Do not delete a receipt to retry or clear another writer's lock. `plan` uses stored
inventory and makes no network reads. `backfill --pairs 1` is the initial pilot;
maximum `--pairs 4` reads 16 objects and stages complete local/foreign groups.
It never calls the lender/address/daily collector. Discovery must be under 36 hours
old. At most 12 batches/day, one sequential source read, 64 MiB/batch and 8 MiB/object
apply. Failed and uncertain requests consume the shared 500/day CR budget; Retry-After
on 429/503 sets a persisted shared hold. Interrupted requests retain byte reservations.

Freshness checks the latest two pairs and the four-file same-period lender group.
An unrelated failed group cannot suppress verified staging. Daily publication
merges staged membership after acquiring the writer lock and comparing its base;
accepted state and its successful job receipt commit atomically. Normal publication
occurs at most once per UTC date. Backfilled staged counts remain distinct from
public accepted counts. Missing catalogue entries are retained as discovery gaps.
No new public version is promised by a successful staged-only batch.

The address due queue is keyed by register plus exact BRN; it selects indexed SQL
pages and preserves prior successful observations after provider/empty/schema
failure. Repeated unchanged addresses have new check evidence without an invented
move. Changed observations retain previous accepted memberships. `latestAddress`
is queried separately so the detail response's first 100 observations cannot hide
it. The address stage remains 20/day until offsite recovery and measured 100/day
qualification pass. No reader starts collection.

The host runner enforces 512 MiB/one CPU on collectors, requires 1 GiB available
memory and 10 GiB disk, and records local backup independently after collection,
even on partial/failure. Health units compare a bounded expected occurrence at
05:20 UTC and again at 06:00 only when the earlier result was running. Missing,
interrupted, collection, publication and backup failures remain distinct. No
staffed alert channel or daily offsite RPO is implied. A manual unit start is not
scheduled success: retain timer LastTriggerUSec and unit start/end evidence.

Install/enable the health timer only after a manual no-network verifier probe.
The checked-in backfill timer is a deployment template and remains disabled until
pilot, recovery/headroom and provider-backup-window qualification. Do not enable
it simply because code passed CI. Existing daily local retention stays 30 days;
this release adds no public-version/raw-history pruning. Do not prune unresolved
receipts or the only verified recovery copy.

Daily offsite uploads and source-gated Gazette/SFC/HKEX integrations require the
explicit decisions in [the unsent briefs](data/qualification/company-permission-briefs.md).
Release-time R2 upload/retrieval and restore do not establish unattended daily RPO.
Synthetic contract fixtures neither grant source permissions nor implement a live
connector. Rollback stops only newly installed timers, preserves staged/raw/job
state and restores an accepted pointer separately from code. Old version/cursor
windows and the immutable archive remain retained.

Host source ownership: an earlier release populated `/opt/mcp-hk` while its Git
metadata remained at the original archive configuration commit. Treat that dirty
checkout as owned work. Deploy this continuation into a new immutable
`/opt/mcp-hk-releases/<main-commit>` directory and point only
`/opt/mcp-hk-maintenance-current` and the official units at it. Use Compose project
`curated` when building/replacing only its backend. Leave the existing PostgreSQL
and proxy services, configuration, source checkout and their mounts intact.
The runner resolves its own release directory rather than assuming `/opt/mcp-hk`.

Official address history is available through
`GET /api/v1/companies/<exact-cr-entity>/addresses?view=latest_observed` and
`hk_company_address_history`, with bounded signed pagination and selected-version
pinning. Occurrence IDs are distinct from reusable raw payload IDs, preserving
A→B→A reversion order. The six archival tools and their integer Webb IDs remain.

Approved uploader activation uses only a newly generated host capability in
owner-only `/etc/mcp-hk-curated/official-uploader.json` and the distinct Worker
secret `OFFICIAL_BACKUP_TOKEN`. Never reuse OPS_TOKEN or host an R2 parent token.
The offsite unit runs at 05:17 UTC, independently of collection. It creates an
immutable dump plus complete table/raw-checksum metadata, uploads/retrieves both,
then writes/retrieves the immutable manifest. Its job and last attempt/success
are independent of publication/local backup. A failed attempt retains the prior
offsite pointer and closes the growth gate. An interrupted upload stays unknown.

`official_offsite_job qualify-restore` accepts operator restore evidence only for
the exact latest dump checksum and records the qualified schema hashes. Catch-up
requires a successful offsite attempt within 24 hours and that restored schema;
known upload failure or schema drift closes the gate. Public status separately
reports present offsite coverage, observed normal daily cadence and target RPO.
A scheduled qualification probe is labelled `qualification`, not normal daily
cadence. The target daily RPO stays unqualified until a normal daily upload is
actually observed. The next daily trigger remains visible independently.

Catch-up compares the stored inventory before work and does no collection/backup
when unchanged and complete. It respects the checked host provider-window policy
and the shared host maintenance lock. Around 10%, 50% and full qualification it
starts the independent milestone service: checksum-verified retrieval, isolated
restore, every table/raw checksum, bounded staged prefix/identifier/detail/page
queries and p95 below one second. A restore/performance failure closes the growth
gate and retains its clone and receipts. The publisher holds new historical weeks
while allowing independently valid existing weeks/lenders/addresses to advance.
Successful disposable clones are removed only by their validated owning job name;
production, public-version history and offsite objects remain retained.

The dedicated capability also has persisted aggregate daily upload/read budgets
in the existing controller: at most 16 PUT attempts and 1 GiB plus 8 MiB metadata,
64 read admissions and 2 GiB retrieved bytes. Failed attempts consume admission;
caller-selected object names do not reset it. A recovery manifest requires its
exact stored dump/source sizes and provider-verified checksums. No auth token or
query text is stored in these counters. Host restoration reserves 10 GiB plus a
20-times compressed-size forecast before creating its disposable database.

Verified retrieved offsite duplicates also have a 30-day local grace. Bounded
pruning considers at most four expired copies per run, preserves the latest two
qualified copies, requires matching restore proof, local SHA-256 and a still-
present checksum/size-matching offsite object, and never deletes R2 objects or
unverified/failed evidence. No public version, cursor, original archive or other
bucket prefix is pruned by this workflow.

Address expansion is a persisted owner policy, initially 20/day. Both new check
rows and pre-migration address source reads count, including failed attempts.
`official_address_stage --set 100` requires the recovery gate. Admission to 250
requires at least 100 observed same-day attempts, at most 5% settled identity/no-
match failures, no network/hold/schema failures, at least 50 timed source samples,
mean at most 7.5 seconds and p95 at most 20 seconds (within the 780-second sequential
100-read envelope), memory below 512 MiB and a fresh enlarged-state restore after
the latest address attempt. A failed gate retains the qualified prior stage.
The 09/10/11 HKT address timer requests at most 100 per batch; the durable daily
policy yields 100/100/50 at 250, and later deliveries become no-ops. Freshness also
uses the same remaining address policy and 500/day CR provider budget. Publication
seeds new exact identities into the queue without changing existing due/hold state.

A retained January 2025 workbook exposed an Excel XF `f123Prefix` difference:
one CSV company-name value starts with an apostrophe while the XLS logical text
omits it and explicitly flags the prefix. Transform `official-v3` reads formatting
metadata and permits only an unambiguous full-row match by reconstructing one
apostrophe on flagged text cells. Unflagged or unrelated differences still fail;
raw CSV values, IDs, dates and multiplicities are unchanged. See the
[Microsoft XLS XF definition](https://learn.microsoft.com/en-us/openspecs/office_file_formats/ms-xls/993d15c4-ec04-43e9-ba36-594dfb336c6d).
Saved-byte replay supplies the original `fetchedAt`; `reparsedAt` identifies the
later transform. Old rejected captures and accepted public versions remain intact.

### UX release adoption observation (25 October 2026)

For the source-aware UX release, public headers and the new gateway capability
were current while the controller still reported its old environment. The CLI's
immediate flag and a same-version activation did not establish adoption. With
resource cron already paused, propagation complete and no maintenance/seed lease,
setting `durable_objects.code_update_strategy` to `{"mode":"immediate"}` in the
**temporary** four-schedule config and activating the verified version produced the
expected private `controllerContract` and release. Preserve the normal checked-in
schedules/defaults; this is not permission to force code adoption during maintenance.
Always verify actual diagnostics, backend readiness and required recovery before
restoring the five schedules. See `docs/verification/ux-20261025/RELEASED.md`.

### SFC capability-only integration

The SFC engineering branch adds a static gated capability page/status. It installs
no production SFC schema or scheduler and changes no accepted PostgreSQL pointer.
Only source-free status may be released while [SFC rights](verification/sfc-20261025/RIGHTS.md)
remain unresolved. A live dataset release still requires its real cohort,
route/parser/output qualification, atomic source pointer, source-scoped offsite
restore and ordinary occurrence. Do not silently apply `003_sfc.sql`, enable a
collector or add SFC to the CR offsite inventory during an unrelated gateway release.
