# Operating the first development release

This is one ASGI process on one host with persistent SQLite and capture storage.
Do not run multiple replicas with separate database volumes and call them one
consistent service. The public domain has not been deployed by this change.

## Install and run

```sh
uv sync --extra test --extra dev
uv run mcp-hk-refresh all
uv run mcp-hk-http
```

Visit `http://127.0.0.1:8000/demo`. OpenAPI is at `/openapi.json`, interactive docs
at `/docs`, source status at `/sources`, and remote MCP at `/mcp`.

For Docker, build the image, refresh the mounted `/data` volume explicitly, then
start the service using the same volume. Runtime capture files are not image data:

```sh
docker build -t mcp-hk:dev .
docker run --rm -v mcp-hk-data:/data mcp-hk:dev mcp-hk-refresh all
docker run --rm -p 127.0.0.1:8000:8000 -v mcp-hk-data:/data mcp-hk:dev
```

The nonroot image user needs write ownership of the persistent volume. Back up
SQLite with its backup API (not a bare copy of a live WAL database), and restore
to a separate test directory before release. The volume backup must include captures.

## Configuration and limits

- `MCP_HK_DATABASE`: default `.data/mcp-hk.sqlite3`; container default `/data/mcp-hk.sqlite3`.
- `HOST` / `PORT`: default `127.0.0.1:8000`; image binds `0.0.0.0`.
- `MCP_HK_ALLOWED_HOSTS`: comma-separated trusted public/local hostnames.
- `MCP_HK_ALLOWED_ORIGINS`: exact browser origins allowed to reach MCP.
- `MCP_HK_ADDRESS_DAILY_BUDGET`: default 10000 live ALS requests per UTC day,
  persisted in SQLite; a cache hit does not consume the live-source budget.

The API enforces best-effort 60 requests/minute/client IP per process, with 10/minute
on REST address routes. All MCP tools share the general limit. The shared ALS
service additionally limits concurrency to three and applies the persisted daily
budget to MCP and HTTP alike. Forwarded headers are not trusted by default. Configure
the production reverse proxy and real-IP handling before launch; otherwise proxy
clients share a conservative bucket. This is not a per-person quota.

Live source reads have five-second timeouts and 8 MB decoded-response caps. Request
bodies are capped at 64 KB, including chunked bodies. MCP browser Origins and Hosts
are validated. Anonymous public REST reads have wildcard CORS without credentials.
There are no public import/admin endpoints. Uvicorn access logging is disabled to
avoid recording raw address queries; also review reverse-proxy logs at deployment.

## Refresh and rollback

Run ordinary cron on the same host/storage, e.g. restaurants daily after the stated
09:00 Hong Kong publication time and population weekly. Do not overlap scheduler
jobs: use the host's process-lock mechanism. Publication itself uses an SQLite
transaction and an expected-generation check, so overlapping writers cannot silently
overwrite a newer import. Each run persists a success/failure receipt.

An unchanged normalized snapshot advances the check timestamp without changing its
source retrieval timestamp or population year. Restaurants warn after 36 hours and
population after eight days without a successful check. `requireFresh=true` fails
instead of serving stale pack data; ordinary reads retain warnings and provenance.
ALS query cache expires after 24 hours and has no stale fallback. Metadata catalogue
queries are live. `/readyz` checks that packs are loaded; `/api/v1/status` reports
freshness and failures separately.

Failed schema/coverage/completeness checks retain the previous pack. Inspect
`ingestion_runs` and the latest capture, correct the parser with a regression test,
then rerun that pack. Do not keep retrying an unchanged schema failure.
Use `Store.rollback(pack, snapshot_id)` from an operator-only Python session to
select a previously validated generation; it verifies the pack identity first.
The initial release retains all generations; automated age-based cleanup and bounded
capture retention are still required before long-running public hosting.

## Verification and remaining release gates

```sh
uv run pytest
uv run black --check src tests
uv run flake8 src tests
uv run python -m build
```

Upstream tests which can skip on source failure are opt-in (`pytest --live`). New
deterministic tests fail normally and validate parser fields, units, summaries,
pagination generations, stale behavior and transport parity.

Before production: choose/authorize the container host and spending limit, configure
TLS/DNS and proxy trust, prove backup/restore, schedule/lock refresh jobs, bound capture
retention, run the broader held-out address/client matrix and staging load checks,
and qualify provider redistribution terms. Source metadata capability linking,
complete catalogue mirroring and a release-configured Python registry are follow-ups.
Fork publishing is guarded so no job tries the upstream PyPI publishing identity.
