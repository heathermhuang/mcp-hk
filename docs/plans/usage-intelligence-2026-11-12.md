# mcp.hk usage intelligence: implementation plan

Date: 2026-11-12. Status: implementation prepared in isolated feature branch; not deployed.

## Outcome

Understand how often external clients query mcp.hk, which datasets and sanitised
keywords they request, what results the service delivers, and where demand is unmet.
Keep anonymous reads working without registration or an API key. Provide a private
report and a deterministic daily digest independent of Google Analytics.

The first useful release includes collection, a readable report, and daily summaries.
Do not postpone reporting until optional installation tracking or deeper tracing exists.

## Verified baseline and implementation starting point

Source was inspected on GitHub at main commit
`8e4e037a237e768240ac448902b2f1361f7b1edb`; this is source evidence, not proof of
the currently adopted production controller/container version. The primary local
checkout is older and contains unrelated untracked files. Implement from refreshed
main in an isolated checkout, preserving those files.

- `deploy/cloudflare/usage.ts`: 90-day daily counters, bounded response inspection,
  HTTP/MCP outcomes, byte counts, returned counts when known, and summed duration.
- `deploy/cloudflare/worker.ts`: existing request admission, streaming meter,
  authenticated `/__ops/usage`, and five maintenance schedules. Keep that report compatible.
- `src/mcp_open_data_hk/api.py:36`: `stateless_http=True`. Neither an initialize
  request nor a network address establishes a persistent individual session.
- The operation allowlist omits newer tools. Dataset attribution and returned-item
  extraction also have gaps. Inventory HTTP routes and MCP tools together.
- Existing tests intentionally prohibit query and identity storage. Replace only
  the expectations this feature deliberately changes; retain secret/body exclusions.
- The public analytics policy currently promises no query/client event retention.
  Update English/Traditional Chinese notices with the actual new fields and limits
  in the same release, preserving explicit opt-outs and DNT/GPC handling.
- Reading live totals is currently blocked by an inaccessible local operator
  credential and an expired GA connection. Fresh production verification requires
  normal operator access; implementation and local tests can proceed independently.

## Measurement contract

Every report includes schema version, collection start, timezone, last processed
checkpoint, coverage, exclusions, unknown counts, retention and any truncation.

| Measure | Definition |
| --- | --- |
| Backend requests | Requests reaching the accounting boundary; distinguish admission rejects and protocol/control requests. Not all edge traffic. |
| Data queries | Recognised record/search/download operations, broken down by operation class. Catalogue discovery is separate from record retrieval. |
| Successful data responses | Completed successful data operations; nonempty, empty and unknown returned-count categories remain separate. This is not proven user success. |
| Estimated daily network clients | Distinct day-scoped HMAC network buckets, excluding missing identity. Shared gateways merge people; changing networks splits them. |
| Identified application coverage | Fraction with reported client metadata or classified user-agent; application labels are self-reported or inferred, never verified ownership. |
| Returning installations | Available only for clients voluntarily sending a stable random installation ID; report coverage and observation window. Not returning people. |
| Query journeys | Explicitly correlated requests only. No linking by IP, timing similarity or keywords. |
| Latency | Time-to-headers and observed stream duration separately; bounded histograms with explicit bucket-derived quantile estimates. |
| Unmet demand | Catalogue no-match, valid query no-match, unsupported capability, unavailable source and stale-only results as separate categories. |

Store timestamps in UTC; aggregate hours so reports and digests can use
Asia/Hong_Kong calendar days. Scope audience HMACs to that same reporting day,
separately from existing UTC quota keys. Never sum daily uniques into monthly uniques.

## Architecture and bounded storage

Use a separate SQLite-backed UsageAnalytics Durable Object. Detailed analytics cannot
fill the controller database used for admission. Preserve the source database and
quota semantics. No new vendor or external service is required.

Data flow: trusted edge classification -> admission/request record -> streamed
response accounting -> one terminal outcome -> hourly rollups -> operator report
and daily digest. Generate the analytics event ID server-side. Never trust incoming
internal telemetry headers or use client JSON-RPC IDs as global event IDs.

Proposed additive tables:

- `usage_events_v2`: bounded recent request summaries and sanitised query fields.
- `usage_hourly_v2`: low-cardinality totals by operation/dataset/client family/outcome,
  bytes, known/unknown item counts and latency buckets.
- `usage_clients_daily_v2`: distinct day-scoped network pseudonyms; report global
  and operation-level distinct counts without adding per-dataset counts together.
- `usage_keywords_daily_v2`: bounded keyword demand counts and outcome categories.
- `usage_digest_v2`: completed-period summary, checkpoint, generation status and
  explicitly recorded notification status.

Defaults to validate under load: recent detail for seven days, at most 10,000
events and 2 KiB serialized metadata per event; hourly aggregates for 90 days;
daily identity buckets for eight reporting days; a maximum of 256 distinct
retained keywords per day, using Space-Saving estimates so late popular terms can displace early rare terms.
Reports disclose candidate-count bounds and eviction limitations.
Keep unknown operations/client versions and free-text cardinality bounded.
Detail limits must not silently reduce the aggregate request totals. Reports show
the retained-detail period, omitted detail and keyword coverage. Preserve existing
90-day aggregates; longer monthly retention can follow after measuring cost.

Use indexed queries and bounded cleanup batches, outside the per-request full-table
scan path. Make aggregate writes and terminal-state updates atomic and idempotent.
Protect stream cancellation/error paths against double completion. Real client
retries remain real requests; count them separately when an explicit correlation
allows retry identification. Interrupted finalization stays unknown, not success.

Collection errors must not change public response bodies/status or quota decisions.
Expose write/enrichment failures, last successful write, pending finalizations,
overflows, scrubbed fields and unclassified requests. Storage outages can lose
telemetry: label degraded coverage rather than promising exact totals during outages.

## Query and result capture

Use a per-operation extractor registry shared by reporting and classification,
checked against actual HTTP/MCP registrations. Do not persist arbitrary tool names,
URLs, raw request bodies, headers, returned records or exception messages.

Allowed fields include dataset/resource IDs, selected public field names, filter
operators, requested format/language, page size, and bounded sanitised keywords.
Retain exact filter values only for explicit safe fields such as district codes;
otherwise retain field/operator and value type. Suppress address-search text, exact
coordinates, personal identifiers and credential-like content. For approved general
catalogue searches, normalise Unicode/whitespace/case and cap text at 160 characters.
Preserve Chinese and English separately; no model-based translation or guessed intent.
Rule-based redaction is imperfect: limit eligible operations and test realistic
sensitive inputs; do not claim arbitrary free text can be made anonymous.

Result summaries contain known returned count, explicitly provided matching total,
pagination availability, source/version, warning codes and error category. Never
substitute a dataset inventory total for returned rows or infer no-match from an
unparseable response. At most ten public result IDs may be retained for approved
non-sensitive operations; suppress sensitive query/result identifiers together.
Exact historical response replay is outside this release and needs retained source
snapshots plus the full query contract.

Keep existing bounded streaming inspection. Oversized/unparseable envelopes retain
bytes and unknown metadata. For deeper coverage in the second increment, add typed
backend metadata before serialization and a bounded authenticated internal delivery
channel keyed to the edge event ID. Its updates enrich the existing event; they
must not increment request totals again. Strip internal metadata at the public
boundary; cap buffering, retries and pending updates, and expose dropped enrichment.
Do not introduce an unbounded response parser or buffer downloads for analytics.

Classify traffic as operator/test (trusted), recognised crawler (heuristic),
external candidate or unknown. Do not treat an arbitrary public user-agent/header
as proof of operator traffic. Ordinary AI-agent queries are legitimate usage.
Keep physical service load visible even when excluded from external-usage views.

## Client identity and optional cooperation

Parse bounded application name/version from client metadata where actually supplied,
supporting the protocol versions in use. In stateless mode, initialization metadata
cannot be attached to later calls without explicit correlation; keep those unknown.
Normalised user-agent family is a lower-confidence fallback. Do not infer the model
name, person, organisation or actual user location from gateway infrastructure.

Derive network pseudonyms with a dedicated analytics secret and domain-separated
HMAC inputs. Raw IPs remain transient. Missing network identity is unknown, never
one shared pseudo-user. Do not reuse the operations bearer or quota identity value
as an analytics identifier. Analytics identity never affects admission or access.

The second increment may accept optional random installation, session and workflow
IDs through a documented bounded header/metadata contract. Hash before storage,
apply 30-day observation retention, and disclose the limits. These IDs grant no
authority, do not bypass limits, and cannot prove cross-client task completion.
Browser audience remains separate; preserve existing opt-outs and DNT/GPC, including
at the first-party collection boundary. Do not require cookies for server metrics.

## Delivery sequence and acceptance

| Increment | Implementation | Acceptance evidence |
| --- | --- | --- |
| 1A: reliable foundation | Refresh isolated source; inventory tools/routes; versioned event contract; add tables; classify operations; estimated daily clients; outcome taxonomy; redaction; instrumentation health. | Every supported operation is classified or explicitly unknown; quota unchanged; sensitive input absent from storage; concurrent and streaming cases reconcile. |
| 1B: usable reporting | Extend authenticated JSON report compatibly; add dependency-light operator CLI and locally generated HTML dashboard with daily/weekly comparisons. | Report works without GA or importing the application runtime; query count, dataset demand, clients, keywords, unmet demand and failures are readable; no credential is embedded in HTML. |
| 1C: automatic summaries | Generate a daily digest at/after 09:00 Hong Kong for the previous local day using an existing scheduler tick; persist it independently of source maintenance. | One digest per day/version; duplicate ticks are idempotent; missed work resumes from checkpoint; no source reads or container wakeup is needed for analytics. |
| 2: deeper attribution | Optional client correlation, typed backend enrichment, cache/upstream timing and explicit workflow observation. | Stateless/unknown clients still work; enrichment cannot double-count; gateway limitations and correlation coverage are shown. |

Ship 1A-1C as the first technical milestone. Accessible notification delivery is an additional
explicit completion condition, currently pending a destination. Inside 1C, compute a deterministic
weekly comparison when a full week exists; show insufficient baseline before then.
Do not fabricate pre-release keyword/identity history from older aggregates.

The local dashboard is an operator artifact, not a public route exposing query
data or a bearer token. A hosted dashboard requires an existing approved operator
authentication boundary; do not invent an insecure browser token-storage flow.

Daily digest: query volume and change, estimated clients, client-metadata coverage,
top datasets, top unmet searches, outcome/error rates, latency, throughput and
instrumentation health. Show low-volume caveats and unknown denominators.
Start anomaly flags with explicit rules (write failures immediately; otherwise
error rate above 5% with at least 100 eligible queries, or p95 above twice the
comparable baseline with at least 100 observations). Thresholds are proposed
operating defaults to tune from measured baseline, not service guarantees.

The scheduler uses existing ticks without altering the five source schedules.
Analytics has its own bounded checkpoint/lock and cannot acquire or clear the
source-maintenance lease. It reads controller rollups only. First delivery is a
persisted private digest plus dashboard. External email/Slack/push delivery requires
an explicit recipient/channel instruction; generation and delivery have separate
receipts and bounded retry policy. No outbound messaging is authorized by this plan.

## Verification and release

Meaningful tests cover HTTP/MCP parity; all tool registrations; UTF-8/Chinese text;
redaction and oversized fields; malformed requests; unknown/missing/spoofed identity;
shared networks; opt-outs; large JSON/SSE; partial/cancelled streams; MCP errors
inside HTTP 200; genuine zero matches versus source failure; atomic completion;
retention/cardinality caps; restart persistence; duplicate cron ticks; timezone day
boundaries; missed/failed digests; report authentication and HTML escaping.

Use real SQLite/runtime integration for migrations and concurrency in addition to
extractor unit tests. Compare unchanged response bytes/status and quota decisions.
Run repository-required Python checks, Worker tests/types and the push hook. Run a
bounded local before/after load comparison, including report reads during queries;
initial bar is no more than 5 ms added p95 controller overhead and no public-path
failure from telemetry exceptions. Record CPU/storage writes, event size and dropped
detail. If that bar fails, simplify writes or isolate reporting before release.

Keep legacy reports compatible and new migrations additive. Feature flags separate
collection, keyword detail, optional identity and digest generation. A rollback
disables new collection/report generation without changing admission, deleting old
tables or resetting data. Existing core counters continue.

For release, follow `docs/production.md` and current AGENTS.md: pause only resource
cron, respect propagation and owning leases, verify actual controller/container
adoption, then restore all five source schedules. Verify a fresh accepted public-data
backup in an isolated restore as required. Controller telemetry is a separate
database: add an authenticated bounded aggregate export to private R2, explicit
retention, and a separate restore/reconciliation check; do not assume the container
snapshot includes it. Avoid backing up short-lived detail/client IDs by default.

Use explicitly marked operator requests for live smoke checks and keep them out of
external-usage views. Verify real ordinary traffic only when observed; absence of
traffic is no adoption claim. Completion requires a readable report, visible healthy
collection, correct exclusions, and an actual scheduled digest receipt. Source/CI,
production adoption, daily operation and external customer use remain distinct.

## Review corrections and implemented scope

- Isolated analytics storage from quotas. Collection has a caller-side 600/minute
  observation cap, a collector 50,000/day cap, bounded dimensions/identities/detail,
  and a 64 MiB storage circuit breaker. Rejections do not create detailed events.
- Mirrored stored browser refusals into a first-party refusal-only cookie before
  data scripts; forward only the opt-out signal after credential removal. DNT/GPC
  and the documented API opt-out suppress detailed demand/client collection.
- Replaced first-seen keyword retention with bounded Space-Saving rankings. Daily
  candidate bounds and cross-day eviction limitations are disclosed.
- Distinguished persisted digest generation, report accessibility and notification
  delivery. External delivery remains unconfigured; no destination was invented.
- Added independent closed-day R2 aggregate archives, read-back checksum receipts,
  three attempts per archive/reporting day, and isolated restore qualification.
- The first implementation reports known returned counts, version, outcome/stale
  categories and observed-duration histograms. It does not promise complete result
  replay, exact model/person identity, retained raw filters, or gateway end-user counts.
- Optional installation/workflow identity, backend enrichment, upstream/cache traces,
  automated anomaly notifications and a hosted operator login remain later work.
  Initial HTML reports are private operator exports, not publicly hosted dashboards.

## References

- [Current accounting source](https://github.com/heathermhuang/mcp-hk/blob/8e4e037a237e768240ac448902b2f1361f7b1edb/deploy/cloudflare/usage.ts).
- [Current stateless MCP adapter](https://github.com/heathermhuang/mcp-hk/blob/8e4e037a237e768240ac448902b2f1361f7b1edb/src/mcp_open_data_hk/api.py).
- [Cloudflare SQLite storage and transactions](https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/).
- [Cloudflare Durable Object concurrency guidance](https://developers.cloudflare.com/durable-objects/best-practices/rules-of-durable-objects/).
