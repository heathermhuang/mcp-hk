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

No query strings, raw arguments, returned records, user-agent strings, individual
event logs or client identifiers are persisted in aggregate usage. Retention is
90 UTC days. Expired counters are removed on activity and hourly maintenance.

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

`GA_MEASUREMENT_ID` is a non-secret production configuration value. It is empty
until the owner supplies/verifies the correct GA4 web-stream measurement ID.
Never copy an ID from a different project or invent one. `/assets/site-config.json`
exposes only a validated `G-…` value, with no operations credential. A missing ID
disables the Allow analytics button and sends no Google requests.

Before activation, configure the GA4 stream with Enhanced Measurement disabled
(including automatic page changes, site search, form interactions and outbound
clicks), advertising/Google Signals disabled and the desired event-retention
setting. The app sends explicit page views for document and in-app navigation.
Do not claim receipt in the correct GA property from merely loading the script.
Verify the stream's Realtime/DebugView after a consented test, and confirm no
collection before consent or after rejection.

The implementation uses Google's **basic consent mode**: the Google tag is not
loaded until affirmative consent. There are no pre-consent cookieless pings.
GPC or DNT keeps Google Analytics off; localhost and preview hosts cannot load it.
Events use only origin + pathname, an empty referrer and the generic mcp.hk title.
API/MCP calls and data/query contents are not sent as GA events. Browser choice
and Analytics cookies expire after 180 days. Rejecting a previously accepted
choice disables the tag, clears first-party `_ga` cookies and reloads the page.

References: [Google consent implementation](https://developers.google.com/tag-platform/security/guides/consent?consentmode=basic),
[GA4 configuration](https://developers.google.com/analytics/devguides/collection/ga4/reference/config),
[Cloudflare Durable Object SQL](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/),
[PCPD policy guidance](https://www.pcpd.org.hk/misc/dpoc/files/pics_and_pps.pdf).
