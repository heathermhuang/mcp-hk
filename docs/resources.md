# Reconciled catalogue and resource queries

`/api/v1/datasets` and the eight inherited tools remain live CKAN metadata
interfaces for compatibility. CKAN **search is incomplete**: the observed search
index returned 773 entries, while native `package_list` enumerated 3,830. Use the
reconciled inventory for coverage and new applications:

1. `GET /api/v1/catalogue/datasets?q=public%20holidays` / `hk_catalogue_search`.
2. `GET /api/v1/catalogue/datasets/{id}/resources` / `hk_dataset_resources`.
3. `GET /api/v1/resources/{resourceId}/schema` / `hk_resource_schema`.
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
Use exact field names from schema, up to ten filters, 100 selected fields and
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

Initial bounds: 8 MB decoded source, 100k rows, 2m cells, 1k fields, archive expansion
32 MB, PDF 200 pages. These are internal capacity limits, **not external blockers**.
Readers, API adapters, specialised binary formats, deeper verification and capacity
extensions remain implementation work wherever the directory records them. Directory
status `pending` means no validation evidence. `queryable` means an actual accepted
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
Catalogue sync runs Sunday 12:00 HK; a resource batch runs hourly at minute 20. These
are ordinary deterministic jobs with persisted cursors and a maintenance lease.
This bounded schedule does not promise that all discovered resources are fresh;
coverage and timestamps expose the actual progress. Structural/schema failures are
held for operator review, not retried in a tight loop. API responses use a five-minute cache; reference files use a one-day validation interval. Recover through a restore-tested
R2 checkpoint, correct a reader with a source fixture, then resume missing checks.
