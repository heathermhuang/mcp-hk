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
| Bounded resource validation + backup | `20 * * * *` | Hourly at minute 20 |

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
