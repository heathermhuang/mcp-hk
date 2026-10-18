# Reconciled catalogue and resource queries

`/api/v1/datasets` and the eight inherited tools remain live CKAN metadata
interfaces for compatibility. CKAN **search is incomplete**: the observed search
index returned 773 entries, while native `package_list` enumerated 3,830. Use the
reconciled inventory for coverage and new applications:

1. `GET /api/v1/catalogue/datasets?q=public%20holidays` / `hk_catalogue_search`.
2. `GET /api/v1/catalogue/datasets/{id}/resources` / `hk_dataset_resources`.
3. `GET /api/v1/resources/{resourceId}/schema` or read-only `POST .../schema` with source selectors/parameters / `hk_resource_schema`.
4. `POST /api/v1/resources/{resourceId}/query` / `hk_resource_query`.

The `/coverage` browser explorer performs these requests against actual sources.
`GET /api/v1/resources?status=unavailable&limit=100&offset=0` enumerates exceptions;
`GET /api/v1/coverage` / `hk_coverage` gives exact denominators and reconciliation.
These are resource entries in native catalogues, not a count of every distinct
Hong Kong government dataset. Public/private/statutory providers remain attributed;
unresolved provider classifications remain unclassified. Never infer government
ownership from presence on DATA.GOV.HK.

## Query contract

```json
{"filters":{"source_field":"exact value"},"fields":["source_field"],"limit":20,"offset":0,"recordPath":"","sheet":"","layer":0,"requireFresh":false}
```

Equality filters preserve source types: CSV `"001"` is not JSON number `1`.
No SQL, source query expressions, arbitrary URLs or network credentials are accepted.
Use exact field names from `schema.fields` or nested selectors from `schema.queryFields` (for example `properties.name` or `attributes.DC_ENG`). Exact top-level dotted keys take precedence. Projection preserves the requested selector as its output key. Up to ten filters, 100 selected fields and
100 records/page. Pass returned `meta.version` on every later page; changed content
returns 409 so clients restart instead of mixing source versions. Catalogue directory
pagination is live within the reported inventory generation; restart if it changes.

JSON arrays and nested objects retain their original values. `recordPath` selects
slash-separated object keys and explicit array indices, e.g.
`vcalendar/0/vevent` for public holidays. Escape literal `/` and `~` as `~1`/`~0`.
`schema.availableRecordPaths` and `schema.sourceContext` retain nesting and ancestor
metadata including source units. No unit/reference-date conversion is inferred.
GeoJSON geometry, properties and source CRS are preserved. ArcGIS attributes and
geometry retain the layer CRS; they are not silently relabelled WGS84.

CSV supports UTF-8/BOM, UTF-16 BOM and Big5/HKSCS. Schema states the selected encoding.
Blank, duplicate or extra table columns receive explicit positional names and original
header/column mappings. First-row header interpretation is explicitly unverified;
statistical tables are not automatically normalised. Empty strings, absent cells,
leading zeros and raw footnotes remain distinct. Workbooks require a sheet when there
are several. XLSX formulas are returned as formulas, never executed. Legacy XLS returns
stored cell results and an explicit warning. XML preserves namespaces, attributes and
repeated elements. XML entities are rejected.

ArcGIS service roots expose layers/tables in schema; select `layer`. Complete layer
reads reconcile every object ID, all batch identities and a final ID set. Changed ID
sets, overfull/truncated pages and transfer-limit flags fail closed. WFS schema exposes
feature types; pass a type name in `recordPath`. WFS GetFeature requires an exact
matched-feature count. Neither family silently presents a partial layer as complete.
Department JSON responses retain response context and scope. Generic API response
access does not imply that pagination, arbitrary endpoint parameters or full history
have been integrated. Inventoried URL templates accept only their exact named `parameters` (up to ten string values), URL-encoded into the fixed source endpoint; credentials and parameterised hosts are rejected. Other API specifications and pagination families still require adapters.

ZIP/GTFS/KMZ and ZIP responses labelled CSV/GeoJSON are read in memory, without
filesystem extraction. Every supported member has `_sourceArchiveMember` provenance;
unread binary members are listed. Nested archive expansion, member count, decoded
bytes, rows, cells, fields, XML entities and document parsing are bounded.

PDF responses are **unverified page text**, with page numbers and source page links;
they are excluded from structured-queryable coverage. Scanned/empty pages are listed.
Extraction runs in an isolated process with CPU/output/deadline limits and a Linux
address-space limit. Extracted tables are not automatically promoted to datasets.

## Freshness, failure and capacity

Public reads download only the selected resource after an inventory lookup; they
never trigger catalogue reimports. Completed records use a 4 MB total SQLite cache;
individual larger accepted representations are served transiently. Two source reads
run concurrently. Live API responses cache for five minutes; other files for one day.
Every response carries actual checked/retrieved dates and source publication metadata,
independent of statistical reference periods. Successful unchanged conditional reads
advance validation time while preserving retrieval time. Source/schema failure retains
an accepted cached representation with a stale warning; `requireFresh` rejects it.

Small-response bounds: 8 MB decoded source, 100k rows, 2m cells, 1k fields, archive expansion
32 MB, PDF 200 pages. These are internal capacity limits, **not external blockers**.
Readers, API adapters, specialised binary formats, deeper verification and capacity
extensions remain implementation work wherever the directory records them. Directory
status `needs_adapter` marks parsing/shape implementation work; it is not an external source outage. `pending` means no validation evidence. `queryable` means an actual accepted
representation, not full historical or semantic qualification of the entire dataset.

## Inventory and operator jobs

```sh
mcp-hk-catalogue sync
mcp-hk-catalogue audit --batch 100 --cycles 1000
mcp-hk-catalogue coverage
```

Sync harvests all native DATA.GOV.HK dataset IDs and resources, reconciles the official
quarterly list and separately harvests CSDI CSW/ISO metadata. Identical resource URLs
within a dataset collapse to one ID with all language aliases. Different language URLs
remain distinct. Exact cross-catalogue URL overlap is reported separately; catalogue
dataset counts are never added and described as distinct government data.
CSDI default paginated relevance order proved unstable. A single bounded complete
CSW response is used and rejected if its returned/unique counts do not match.

Only complete validated inventories publish transactionally. Native IDs are checked
again at the end of the DATA.GOV.HK harvest. ETag/Last-Modified validators are used when
supplied. Runs retain failure receipts; accepted inventory survives a failed run.
The active and previous inventory generations remain in SQLite; immutable R2 backups
retain older recovery points. Metadata payloads and schemas are compressed separately
from the bounded record cache. Full raw files are not committed or put in the image.

Hosted operator commands add `catalogue` and `resources` to `scripts/cloudflare_ops.py`.
Catalogue sync runs Sunday 12:00 HK; a cadence-aware resource batch runs every five minutes at minutes 2,7,...57. These
are ordinary deterministic jobs with persisted cursors and a maintenance lease.
This bounded schedule does not promise that all discovered resources are fresh;
coverage and timestamps expose the actual progress. Structural/schema failures are
held for operator review, not retried in a tight loop. API responses use a five-minute cache; reference files use a one-day validation interval. Recover through a restore-tested
R2 checkpoint, correct a reader with a source fixture, then resume missing checks.


## Audit-driven streaming and department adapters

CSV/JSON/GeoJSON above the small-response budget use DNS-pinned downloads to private
128 MB temporary files and a complete streaming validation pass (up to 1m rows,
10m cells, 1k fields, JSON depth 30 and 1 MB per JSON record). Queries scan the accepted
file and retain only the requested page; files are removed explicitly afterwards.
Large JSON objects require an explicit array `recordPath`. No full-file record cache
or raw-dataset repository commit is created. Streamed pagination versions hash selected
records, while source provenance separately retains the actual response hash.

C&SD `web_table.html?...download_csv=1`/Excel links are interactive download pages.
The table adapter explicitly resolves their official JSON-equivalent endpoint,
preserves fields and units such as `svDesc`, and requires its declared complete row
count. Original and resolved source links and the access method are returned. A live
96-record table passed this reconciliation; a previously oversized JSON table streamed
58,374 records successfully.

The HKMA adapter reconciles `datasize` across all bounded `offset`/`pagesize` pages and
rejects early termination, count changes and repeated pages. Its pagination remains
live because the provider supplies no snapshot token. The local egress path returned
an upstream HTTP 405 access page during verification; fixture success is not a live
provider clearance. Recheck from production after deployment before reporting access.

ArcGIS complete-layer reads spool to the same disk-backed reader after exact object-ID
batch reconciliation, with up to 1m IDs, 128 MB representation and a 120-second adapter
deadline. Each page contributes to a response-chain hash, and the final ID set must
match the initial set. These bounds remain internal capacity limits wherever exceeded.

HTTP POST schema inspection accepts only `parameters`, `recordPath`, `sheet`, `layer` and `requireFresh`; it shares the MCP selector contract. GET remains available for simple selectors. The browser uses POST so filled source parameters reach inspection as well as queries.

Catalogue jobs have a ten-minute overall deadline and cancel/drain outstanding source tasks on failure or cancellation. A failed job retains the accepted generation and records its failure rather than leaving source requests running after the job ends.

Template discovery accepts `{name}`, `<name>` and bracketed query-value format hints such as HKO `date=[YYYY-MM-DD]`. Bracket hints use the actual query parameter name (`date`), preserve independent start/end values and leave numeric array literals unchanged. Provenance links to the resolved request URL and retains the original inventoried resource URL. Credential parameter names remain rejected.

Dataset resource lists accept exact `format` and optional validation `status` filters over both HTTP and MCP. The explorer offers a format selector, so clients can select JSON APIs without paging through hundreds of workbook resources.


## Validation freshness and semantic quality

A prior successful read is access evidence, not current observations or a verified
analytical table. Directory entries expose `validation.freshness`; query/schema
responses expose `validationFreshness` and `quality`. Cache TTL, review cadence,
publication dates and reference periods remain separate. Generic source headers,
units and grain are explicitly unverified; positional columns remain labelled.
A lone exact no-record message becomes zero observations with its source context
retained. Other messages and genuine error envelopes keep their own meanings.

The scheduled queue selects due eligible resources before limiting the batch. It
uses the dataset's declared cadence (annual: 90-day review, quarterly: 21 days,
monthly: seven days, weekly: one day, daily: six hours; explicit one-off/retired:
one year; unknown: one day or one hour for APIs). These are review targets, not
claims that source observations are new. Interactive cache TTL remains five
minutes for APIs and one day for other files; arrival feeds retain 10/20 seconds.

Each scheduled run is capped at 256 eligible review attempts, 90 seconds, six concurrent
reviews (at most two per source host), and a persisted 50,000-attempt daily budget.
Interactive reads retain their separate two-slot pool. Review attempts may involve
multiple bounded HTTP requests; the budget does not count individual HTTP calls. Held structural/selection failures and arrival
feeds do not consume scan slots. The queue reuses accepted sheet, record-path and
ArcGIS layer selectors, respects successful interactive validations and backs off
on failed reads. Pending discovery and due accepted sources precede repeated
failures. Policy, last-run counters and overdue-review counts are public under
`validationFreshness` in coverage. These budgets bound work; they do not promise
zero backlog or full semantic qualification of every discovered resource.


Compound cadence descriptions use the fastest declared update. A historical-only,
closed availability period is not classified as a current hourly feed. Policy
revisions preserve failure cooldowns, and coverage reports the active policy
revision rather than silently applying older review intervals.


### Sustainable capacity and recovery

`validationFreshness.capacity` compares the accepted inventory's review demand with
both the daily budget and the deployed five-minute batch capacity, with 20% minimum
headroom. It reports an insufficient plan as degraded. Configured capacity is
separate from measured run throughput and actual backlog. `overdueAcceptedCount`
keeps previously accepted sources visible even after a new source read fails;
failures cannot make the backlog disappear by leaving the queryable denominator.
Source cadence, cache TTL and semantic qualifications are unchanged.

For operator-controlled catch-up, repeat short `resources` batches, preserving
each accepted checkpoint. The hosted `resources-recovery` name is a compatibility
alias for one ordinary 90-second batch, not a ten-minute HTTP operation. Long
synchronous catch-up calls returned before their checkpoint while server work
continued; bounded calls avoid that uncertain transport lifetime. Stop when the
relevant debt is cleared, the daily budget is exhausted, or the next unchanged
failure needs investigation. Never bypass a held lease.
Fast-compression checkpoints retain the same checksum and restore validation.


Background reviews send accepted ETag/Last-Modified validators even when the small
row cache has evicted a representation. A 304 refreshes only the exact accepted
variant's validation time, with hash/schema compare guards; it retains content
hash, observation/retrieval time and record count and does not fabricate cached
records. Public record queries without a row cache still read actual source data.
Changed 200 responses still pass the full parser and schema-drift checks. Heavy
acceptance serialization and SQLite work run outside the async request loop.

Do not deploy Worker/DO code during an active maintenance lease. Wait for the
receipt/checkpoint or the bounded lease deadline, reconcile state, then preserve
completed progress through an operator backup before rolling the container.


The HKO current-weather `warningMessage` contract permits a string array or an
empty string when no warning is present, as specified in the [official API
dictionary](https://www.hko.gov.hk/tc/weatherAPI/doc/files/HKO_Open_Data_API_Documentation.pdf).
That source-scoped representation change is compatible across accepted snapshots;
raw values and observed types remain unchanged. Other field drift and malformed
warning values still require review.

The hosted reader uses `standard-1` (half a vCPU, 4 GiB) after measured ordinary
review throughput on `basic` fell below the required review rate. Verify actual
throughput and interactive latency after a size change; nominal budgets alone
do not establish sustainable capacity.


The container idle timeout is ten minutes, longer than the five-minute review
cadence. Otherwise each cron can wake a stopped runtime and fail readiness before
its accepted snapshot restores. Scheduled jobs retry only DATA_RUNTIME_NOT_READY,
at most twice with 30-second pauses and before acquiring a maintenance lease.
Held leases and actual review/checkpoint failures are never retried by this wrapper.


Accepted-variant lookup has a `(resource, validated DESC)` index. Both selector
replay and per-resource variant pruning must search that resource's rows rather
than scanning the full accepted catalogue. Confirm query plans and benchmark a
production-checkpoint copy when changing these paths. Legacy reader-version
variants are not reused to bypass a new parser's required validation.

Operator diagnostics expose the executing Durable Object's `workerRelease` as
well as its safety lease and accepted receipt. Verify the expected release and
backend policy before starting recovery after a rollout. The hosted recovery
window is at most 256 attempts / 90 seconds per checkpointed request.

Due background reviews always contact the source (including conditional GET), even
when a cached body has a longer TTL than the review interval. Normal interactive
cache reuse is unchanged.

For 33 exact, previously accepted public URLs from Highways, Public Libraries and
Companies Registry and SmartPLAY, the hosted reader uses the existing authenticated Worker as a
streaming HTTPS transport. Native Worker requests reach these origins where the
container's TCP path times out. The packaged allowlist is finite; callers cannot
supply a URL, credentials, cookies or request body. Redirects stay on the approved
HTTPS host. Original government source URLs and bytes remain the data provenance;
`sourceTransport` discloses this transport. The reader still enforces public DNS
addresses and decoded response limits.

RSS acceptance verifies RSS, Atom or RSS 1.0 root structure, rejecting HTML error
pages. Optional feed fields are extensible. Rows preserve the selected raw XML
structure: the default channel count is not a count of books. Select
`recordPath=channel/item` for RSS item rows when the actual feed exposes that path.

Exhausting a review run's time budget defers unfinished attempts; it does not
classify the source as failed or impose a provider cooldown. Deferred sources
remain due for the next bounded batch. Policy 8 repairs legacy cooldowns only for
accepted sources that are still queryable and whose last source check predates
the failed review. Real unavailable/restricted/schema failures retain backoff.
MTR Bus's explicit status-0 temporary-unavailability advisory remains an error,
with the provider's message, rather than becoming a successful empty arrivals list.
