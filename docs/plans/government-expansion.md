# Government open-data expansion: engineering plan and acceptance contract

Date: 2026-10-16. Owner: mcp.hk. Status: implementation in progress.

## Outcome and verified starting gap

The goal is reusable access to Hong Kong government open data, not more hand-written
packs. Existing catalogue search returned **773** entries in a live probe, whereas
the official quarterly list (as of 2026-10-05) contains **3,832 dataset IDs and
46,410 resource descriptions**. The descriptions lack resource URLs/IDs and include
public/private providers. CSDI CSW independently reports **1,154 metadata records**.
These are different denominators and must not be summed as distinct government data.
The current three government packs and independent Plate.hk pack remain available.

## 1. Inventory and reconciliation

- Enumerate DATA.GOV.HK `package_list`, retrieve every `package_show` (search is not
  a complete index), reconcile IDs against the published quarterly list. Preserve
  additions/removals and the list's publication date. Read all pages, reject duplicate
  IDs, empty intermediate pages, count changes, truncated results and identity mismatch.
- Harvest CSDI CSW plus full ISO metadata; join exact CSDI URLs/identifiers to portal
  resources. Keep uncertain cross-catalogue matches explicit rather than merging by title.
- Stable dataset ID is source namespace + native identity. A resource is a distinct
  canonical URL within a dataset; language aliases with identical URLs share access,
  while different language files remain distinct resources. Keep all original IDs,
  shared IDs, language, format and title aliases.
- Retain provider, provider type with evidence, source/catalogue links, data dictionary,
  source publication/reference dates, cadence and raw metadata terms. Unknown terms,
  units and reference periods stay unknown. Do not infer government ownership merely
  from presence in the portal or `hk-` prefix.
- Publish generation/checkpoint, exact counts per catalogue/provider/format/status,
  reconciliation differences and full paginated exception directory. Catalogue
  discovery, resource validation and data freshness are separate metrics.

## 2. Resource access and storage decision

One basic container has 1 GiB memory, one instance and existing 25 MB compressed /
150 MB SQLite recovery bounds. Do not bulk-load all 46k resource files into it.
Use SQLite for metadata, receipts and a bounded cache of completed validated records.
Keep the original source authoritative. Cache budget, response byte/row/depth limits,
concurrency and deadlines are explicit. Public reads never trigger a whole catalogue
refresh. Downloads are by inventoried resource ID, never arbitrary user URLs.

Implement shared `search -> resources -> schema -> query` services and HTTP/MCP
adapters with equality filters, field projection and bounded pagination. Preserve
nested objects and strings (including leading zeros, missing values and units).
JSON record paths and workbook sheets/XML record paths must be explicit when ambiguous.
Return content hash, schema, original links, checked/retrieved dates, source metadata,
completeness scope and pagination semantics. Reject oversized/truncated/invalid data
rather than offering partial records as complete. CSV (UTF-8/BOM/Big5), JSON, GeoJSON,
XLSX/XLS, XML/RSS, ArcGIS layers and observed department JSON families are required.
ArcGIS must prove full ID coverage or use explicitly live paging with upstream totals;
never silently accept `exceededTransferLimit`. Add WFS if the inventory requires it.

Security: fixed catalogue endpoints; source destinations must be public HTTP(S),
resolve to public IPs, prohibit credentials/private networks and validate every
redirect. Query fields/operators cannot become SQL or upstream expressions. Bound
compression expansion, XML entities, workbook expansion and PDF parsing. Cache only
completed values; reject unknown resource IDs before network access.

## 3. Documents and other formats

PDF access returns page-numbered extracted text with source hash/page links and an
explicit unverified-extraction status. It is not a structured dataset. Empty/scanned
pages require OCR/verification; do not fabricate tables. Preserve unsupported raster,
CAD, binary/archive and restricted/dead endpoints with precise reason and last check.
ZIP support must be bounded and list members; never extract paths onto the filesystem.
Accessible exceptions are implementation backlog, not external blockers.

## 4. Deterministic operations

Operator catalogue sync is resumable, bounded and conditional (ETag/Last-Modified),
publishes validated inventory atomically, and retains prior inventory on failure.
A normal scheduled script compares checkpoints before work. Resource checks process
bounded batches with persisted cursor, validate before publication, detect schema
drift and keep the previous accepted version on failure. Never retry an unchanged
schema/parser failure in a tight loop. Record unavailable, restricted and size limits
separately. Preserve old generation for pagination/rollback. Back up and restore-test
metadata/accepted caches with existing R2 path and enforce capacity before publication.
Use Cloudflare Cron/ordinary scripts, no scheduled model calls and no new paid service.

## 5. Public coverage and developer journey

Add `/coverage` and a resource explorer. Show exact datasets/resources discovered,
validated queryable, stale, unavailable, unsupported, pending and document-only
counts with denominators, source scope, reasons and timestamps. Allow search, resource
selection, schema inspection and a real paged record query. Show equivalent HTTP/MCP
requests and citations, plus honest empty/loading/failure states. Maintain mcp.hk name,
hk_ tool compatibility and existing pack demos. Service health is not coverage.

## 6. Acceptance and release gates

- Inventory IDs reconcile against both native enumeration and official list; all
  native resource records processed, aliases accounted for, CSDI overlap explicit.
- Deterministic tests cover every supported format/family, ambiguous nesting,
  encodings, malicious URLs/redirects, expansion/size limits, empty/duplicate/truncated
  pages, schema drift, unchanged checks, stale fallback, rollback and recovery.
- Live audit visits every inventoried resource; persisted receipt includes exactly
  which resources are queryable, unsupported, unavailable or externally restricted.
  Coverage is never claimed from a filename/format label or a small sample.
- Required Python 3.10/3.11/3.12 CI, lint, packaging, JS syntax, Worker types/tests pass.
  Focused review resolves actionable defects. Merge through normal GitHub PR path.
- Deploy checked release SHA; verify actual Python backend routes/tool inventory,
  public HTTP filters/pages/schema/provenance, remote MCP parity, browser explorer,
  and a real Codex client through server **mcp.hk**. Preserve exact receipts.
- R2 backup and isolated restore pass with expanded inventory. Observe ordinary
  schedules and freshness independent of data reference periods.

## Completion rule

This task is complete only when accessible supported resources have been implemented
and validated across the reconciled inventory and release gates pass. Any residual
resource must have an inspectable status/reason. Internal capacity/parser backlog is
not an external blocker and does not justify calling all government data connected.
