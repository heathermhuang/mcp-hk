# Usage accounting, limits and website analytics

The public policy pages are `/terms` and `/privacy`, in English and Traditional
Chinese. Their footer links and analytics settings are shared with the homepage
and data explorer. The project is described as mcp.hk; no unverified legal company
name or private email address is invented. General contact uses the existing
repository issues channel, with instructions not to publish personal information.

## Operational usage

The existing Cloudflare Container Durable Object stores daily aggregate counters
in its own durable SQLite database, separate from the container's public-data
snapshots. Container sleep/replacement does not erase these counters. No new paid
analytics service is required. Counters start at deployment; earlier traffic is
not reconstructed or presented as measured data.

Each completed backend request is grouped by UTC day, HTTP/MCP, allowlisted
operation, dataset/resource identifier when available, HTTP status and outcome.
Recorded measures are requests, request body bytes, observed streamed response
body bytes, returned items when known and total duration in milliseconds.
MCP `isError` and JSON-RPC errors count as failures even with HTTP 200. Cancelled
streams and stream failures retain the bytes observed so far. Bodies are inspected
in memory up to 256 KiB to extract response metadata, then discarded; larger
responses retain byte counts and explicitly unknown item counts. SQL failures
emit only the fixed `usage_write_failed` event and do not expose request bodies.

These are application payload bytes before edge compression, not wire bandwidth,
provider download bytes, billing or unique visitors. Returned items are the
returned page, including catalogue metadata, never `meta.total` for the dataset.
Some metadata-only operations do not have a meaningful item count. A dataset ID
is resolved from a successful resource response or known pack provenance;
failures may only identify the requested resource. Unknown operations are grouped
as `other`, without recording arbitrary URL paths, tool names or arguments.

The original aggregate counters retain no query strings, arguments, response records,
user-agent strings or identities and continue for essential operations. Retention
is 90 UTC days. The separate, private usage-intelligence collector below is opt-out
aware and has a different, explicitly bounded data contract.

## Private demand intelligence

A separate SQLite Durable Object (`USAGE_ANALYTICS`) prevents demand/event storage
from consuming the controller database used for quotas. `USAGE_INTELLIGENCE_ENABLED`
is the collection switch. Anonymous reads and existing rate limits are unchanged.
The collector receives completed, non-429 backend observations after the response;
it does not observe static page loads, edge-only responses, interrupted runtime
finalizations or rejected ingress beyond its budgets. `/__ops/usage` remains the
independent legacy request/throttle report. These populations must not be conflated.

Collected dimensions are recognised operation/application family (self-reported or
user-agent inferred), public dataset/resource, outcome, safe field selection,
language/format and sanitised general catalogue keywords. Address searches,
precise coordinates, record bodies, credentials and arbitrary arguments are excluded.
Client metadata from an initialize request does not label later stateless calls.
There is no authenticated-person or returning-installation claim.

A dedicated random key lives only in the analytics object's private storage. Network
IP is transient and becomes a day-scoped HMAC for Hong Kong calendar days. Hashes
last eight reporting days; daily estimates last 90 days and cannot be added to
produce weekly/monthly people. Missing/opted-out identities are unresolved. A daily
10,000-client cap makes estimates lower bounds; reports expose capped observations.

Limits are 600 offered observations/minute, 50,000 accepted/day, 512 ordinary
aggregate dimensions/day plus fixed overflow groups, 256 Space-Saving keyword
candidates/day, 10,000 recent detail rows (at most seven days), and a 64 MiB storage
circuit breaker. Aggregates and sanitised keyword candidates last 90 days.
Space-Saving reports lower/upper candidate-count bounds; multiday bounds omit
occurrences on days when that candidate was evicted. Empty/error observations are
not estimated error rates. Missing, suppressed, capped and unknown data is explicit.
The initial maximum is not a promise of all-request capture.

Browser refusals are mirrored before data scripts into `__Host-mhk_analytics=off`;
credential stripping preserves only a minimal opt-out signal. GPC, DNT and
`x-mcp-analytics-opt-out: 1` suppress keyword/event/client data. Essential counters
and coarse operation/dataset outcomes continue. Refusal cookies contain no identity
and expire after one year, refreshed from the saved explicit choice. No affirmative
consent record is fabricated. Production-host restrictions remain in effect.

Read the private report without importing the Python application runtime:

```sh
python3 scripts/usage_report.py --days 7
python3 scripts/usage_report.py --days 7 --output /private/tmp/mcp-hk-usage.html
```

It uses authenticated `GET /__ops/analytics`; unauthenticated requests return 404.
The standalone HTML contains no credential or external scripts/resources. It may
contain sanitised search demand: keep it private. `--input saved-report.json` can
render an exported report offline. The report also includes the legacy full backend request totals with an explicit
UTC-window label, separate from bounded HK-time demand observations. These
populations and time windows must not be divided to claim a capture rate.
The report includes current-incarnation ingress
loss/failure diagnostics, persisted last-write time, budget drops, detail limits,
unknown outcomes, audience limitations and completed-week comparison windows.

At/after 09:00 Asia/Hong_Kong, existing scheduler ticks generate yesterday's digest
and recover up to seven missed days, one per tick. Work is independent of source
maintenance and does not wake the container for data reads. Digest generation and
notification delivery are separate: no external recipient is configured or contacted.
The report displays `notification.status=not_configured`; notification delivery is
an outstanding integration, not a completed milestone.

Daily closed-period aggregates are independently archived under private R2
`usage/daily/`, read back and SHA-256 verified before an archive receipt is saved.
A failed upload/read leaves the archive pending for a next-tick retry, capped at
three attempts per archive per reporting day. Failure/hold status is visible.
Archives exclude raw IP, HMAC keys, client hashes and recent events. Archive retention
is 90 days. The container public-data snapshot does not contain this database.
Cloudflare platform storage recovery may retain deleted versions for up to 30 days.
The runtime integration test qualifies an independent SQLite restore of actual R2
archive rows; live backup/restore and adoption remain production-release checks.

Read the authenticated operator report (never put its token in a URL):

```sh
PYTHONPATH=src .venv/bin/python scripts/cloudflare_ops.py usage --days 7
```

This uses `GET /__ops/usage?days=7` with the existing operations Bearer credential.
Unauthenticated access returns 404. The report includes full-period totals, up to
5,000 grouped rows and a `truncated` flag. Request 1–90 days to narrow the report.
The private report is not sent to Google Analytics. Cloudflare observability and
the R2 public-data backup manifest are separate evidence sources.

## Enforced limits

`GET /api/v1/limits` returns the current policy. Admission is serialized through
the one production Durable Object, across Cloudflare locations. Limits are:

- 60 backend requests per network IP per fixed UTC minute;
- 50,000 admitted backend requests per UTC day, shared across clients;
- 10,000 address requests per UTC day, shared across clients;
- 65,536 request-body bytes, enforced while reading, including chunked bodies;
- one JSON-RPC operation per MCP request (batch arrays are rejected).

`RateLimit-Limit`, `RateLimit-Remaining` and `RateLimit-Reset` are exposed to browser
clients; Reset is seconds until the fixed window ends. A 429 includes
`Retry-After` and `scope=client_minute` or `shared_daily_budget`. Daily exhaustion
retries at the next UTC day, not after an arbitrary minute. Shared networks share
an allowance. Static pages/assets and private maintenance bypass these backend
limits. Rejected requests are still counted as failures/throttles; the daily
admission budget counts admitted requests, so the two totals need not match.

The edge replaces any client-supplied `x-mcp-client-ip` with Cloudflare's network
identity before calling the object. Its quota key is a daily HMAC using the
existing secret; raw IPs are not stored in new quota buckets. Buckets cover up to
three minutes and expired entries are pruned on traffic or hourly maintenance.
This is not an individual-user identity or unique-visitor estimate.

## Google Analytics activation

`GA_MEASUREMENT_ID` is a non-secret production configuration value. The dedicated
GA4 property is `mcp.hk` (property `559386431`, account `39547952`), with web stream
`mcp.hk web` (`16147472136`) and measurement ID `G-Y1PSQCCW4C`. It uses Hong Kong
reporting time and HKD currency. Enhanced Measurement was disabled with explicit
owner approval on 2026-10-17. Google Signals and user-provided data collection
were confirmed off. Current GA4 retention settings are 2 months for event data,
14 months for user data, with reset on new user activity enabled. These controls
do not cap aggregated standard reports.
Never copy an ID from a different project or invent one. `/assets/site-config.json`
exposes only a validated `G-…` value, with no operations credential. A missing ID
disables the Allow analytics button and sends no Google requests.

Before activation, configure the GA4 stream with Enhanced Measurement disabled
(including automatic page changes, site search, form interactions and outbound
clicks), advertising/Google Signals disabled and the desired event-retention
setting. The app sends explicit page views for document and in-app navigation.
Do not claim receipt in the correct GA property from merely loading the script.
Verify real tag emission with third-party requests intercepted; confirm automatic
fresh-visit collection and suppression after an explicit refusal or browser opt-out.

Public Google Analytics starts automatically for eligible production visits without
an initial prompt. Existing explicit refusals, DNT/GPC and production-host isolation
remain enforced. Events use only origin + pathname, an empty referrer and the generic
mcp.hk title. API/MCP calls and query contents are not sent to GA. Explicit refusals
persist until changed; other browser choices and analytics cookies expire after
180 days. Refusing analytics disables the tag, clears first-party `_ga` cookies and
reloads the page. First-party demand measurement follows the separate policy above.

References: [Google consent implementation](https://developers.google.com/tag-platform/security/guides/consent?consentmode=basic),
[GA4 configuration](https://developers.google.com/analytics/devguides/collection/ga4/reference/config),
[Cloudflare Durable Object SQL](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/),
[PCPD policy guidance](https://www.pcpd.org.hk/misc/dpoc/files/pics_and_pps.pdf).

## Automatic website analytics — 5 November 2026

The production browser starts GA4 on a fresh public visit without an opt-in
prompt or a stored affirmative choice. Existing explicit refusals and DNT/GPC
remain effective. Settings open only on request. Page paths exclude queries and
fragments; API arguments and records never enter GA4. API usage accounting
continues independently. No historic traffic is reconstructed.
