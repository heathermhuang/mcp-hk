# Production: Cloudflare Containers + R2

The Python service remains the data/MCP implementation. A small Cloudflare Worker
serves static assets and forwards API/MCP traffic to one named Durable Object and
one `basic` container (1 GiB memory, maximum one instance). It sleeps after two idle
minutes. All state needed to recover accepted data is restored from a private R2
checkpoint on startup; the container's local disk is not considered durable.

## Deploy

```sh
cd deploy/cloudflare
npm ci
npm run types
npm run check
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
| Cadence-aware resource review + backup | `20 * * * *` | Hourly at minute 20 |

Every successful operation stores an immutable version under `backups/`, then
publishes `latest.snapshot.tar.gz` and a manifest. Only complete, validated imports
can advance an accepted generation. A failed refresh retains the prior data and
backup, and records failure in the durable maintenance status. Re-run only after
investigating a changed condition. There is no model-based recurring automation.

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

The full audit grew its restore-tested checkpoint to 71 MB before finishing. Streaming remains bounded without holding the archive in Worker memory; the larger bound accommodates full receipts and two metadata generations. The host remains one basic container with no new infrastructure.

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
through held IDs. It has a 100-read/90-second run bound and a persisted 2,400-read
UTC-day maintenance budget. Query-cache expiry and cadence-based review debt are
reported separately. Source status also exposes failed/overdue government refreshes
while retaining accepted snapshots and source-label quality counts.
