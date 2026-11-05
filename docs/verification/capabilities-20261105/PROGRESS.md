# Capability expansion, 5 November 2026

Authorized programme: P0/P1 discovery, P2 selections/predicates, P3 independently
qualified school/clinic nearby, P4 complete bus ETA comparison, P5 first cohort.
No source-policy activation, credentials, new services, schedules or paid evals.

## Checklist

- [x] Recheck clean isolated checkout and PR #128 at 199435c: open, mergeable,
  required Python versions, PostgreSQL restore, Worker and browser CI green.
- [x] Implement P0 read-only SQLite report without Store initialization or requests.
- [x] Implement P1 resource/selection receipt projections and existing tool discovery.
- [x] Focused report/scope/failure/discovery and HTTP/MCP regressions: 55 passed.
- [ ] First unfinished package: P0/P1 real checkpoint reconciliation, performance,
  final review, required checks and reviewable PR.
- [ ] P2 persist typed options without replacing source failure; typed predicates.
- [ ] P3 independent EDB and DH source dictionaries, grain/CRS checks and nearby.
- [ ] P4 all reference candidates before ETA ranking, occurrence identity, coverage.
- [ ] P5 measured first-cohort and unchanged-checkpoint onboarding acceptance.
- [ ] Required CI, merge dependency #128 and implementation increments.
- [ ] Coordinated release, actual HTTP/MCP clients, fresh backup/isolated restore,
  read-back of five schedules. A PR or header alone is not deployment proof.

Projections add no tables or stored index: current/previous inventory, existing
50-per-resource receipts and existing checkpoint limits remain authoritative.
P0 alternatives mean accepted representations under the same dataset identity;
language, period, scope equivalence and task benefits remain unqualified.

P2 selector increment: typed metadata options, bounded to 1 MB globally and 100 per
kind; real SQLite backup retains them. WFS discovery restricts names to FeatureType
children. Selection discovery preserves existing unavailable/restricted receipts.
Requested selectors are retained before adapters rewrite their internal record path.

DEBUG REPORT: selector fixture failure. Symptom: workbook test returned parse error.
Root cause: the fake fetch omitted the positional headers argument used by load.
Fix: match the fetch signature in the fixture. Evidence/regression: four selector
regressions pass, including the workbook failure-retention and physical restore test.
Status: DONE. No application error was hidden or source guard relaxed.

P2 predicates: allowlisted numeric and qualified temporal comparisons; bounded,
version-pinned ordering over in-memory and real disk-backed sources. No CSV casts.
85 focused predicate/resource/quality tests passed, including unsafe integer
precision, half-open dates, unknown types, raw IDs, complete streamed matching totals,
null ordering and HTTP/MCP parity. Existing HKO updateTime uses its source contract;
arbitrary date-looking strings remain unqualified. Required exact-head checks/CI
and deployment remain pending for this increment.

P3 investigation: current EDB CSV sample coordinates are decimal-looking while its
DATA.GOV.HK metadata says DMS. This conflict must be reconciled before activating
its point binding. DH sample has Point [longitude,latitude], separate category and
OBJECTID; unique-facility identity, CRS and source context still need qualification.

P4 implementation: compare all candidates before presentation limits, deduplicate
fresh source reads, retain loop visit identity and source service variants, expose
eligible/settled/failed/unchecked coverage, and rank only unexpired future predictions.
24 focused transport/capability regressions pass. The real HTTP/MCP verifier compares
reference parity separately from dynamic ETA ranking and validates both clients'
coverage. Production source verification is still pending.

P0 report performance fix: EXPLAIN on the older local checkpoint showed a repeated
full scan of 40,767 variant receipts without an index. One grouped fingerprint read
now processes 63,360 resources/4,984 datasets in 2.09 s, with zero provider requests
or record/status mutations. Counts reconcile; 3,961 datasets have accepted records,
1,023 lack one. These are the October 17 local generation f8d8e9945a694617b6a2a9eb565e2a03,
not the current 5,048-entry production generation. WMS backlog entries are explicitly
imagery opportunities, not candidate table unlocks.

Local isolated-copy sizing: 60 warm resource projections, p50 6.71 ms/p95 17.11 ms,
max 32.99 ms; initialization/index installation 0.76 s. Four before/after lexical
queries are retained under local-checkpoint/. No FTS index is justified by these
measurements. Production performance and fresh accepted recovery remain pending.

P3 source/replay qualification completed for two independently reviewed overlays.
The original 289,205-byte DH export hash matches the version-pinned 200-feature
public gateway response exactly. CSDI's current GeoJSON policy establishes WGS84,
while underlying metadata retains EPSG:2326. Geometry, not inconsistent property
coordinates, drives distance: 33 differences exceed 5 m; maximum 53.91 m.

EDB's dictionary and its documented dataset-linked WGS84 nearest API support the
explicit decimal-coordinate inference. Two bounded API samples yielded 19 exact
coordinate matches and one identity absent from the current CSV. This is convention
evidence, not equivalent API/CSV coverage. Full CSV checks found 3,496 valid coordinate
rows, 3,481 source IDs, 15 exact duplicates, no missing/invalid IDs and matching
bilingual coordinates. Neither profile claims unique physical facilities or service
availability.

Actual local HTTP and native FastMCP clients agree over both original source-file
replays. Cold schema/qualification: DH 59.56 ms, EDB 176.51 ms; warm nearby queries:
13.31/41.29 ms. These include source parsing/query work and are not the warmed
single-resource metadata lookup target. This remains local replay, not new-code
production source-path proof. A built wheel contained both profile JSON files.

14 spatial regressions pass, including exact source identity, bilingual filters,
original types, duplicate/missing IDs, malformed coordinates, totals-before-limit,
version-pinned pages, explicit wrong CRS, profile/context drift, source failure holds
and HTTP/MCP discovery parity. Full compatibility subset: 78 tests passed before
final documentation. Full exact-head checks and CI remain gates.

DEBUG REPORT: the real replay initially found HTTP 400 on capability=nearby.
Root cause: the transport enum omitted the new value while the store supported it.
Fix: one shared HTTP/MCP capability alias and an explicit parity regression.
Evidence: the same replay and 14 spatial tests now pass. Status: DONE.
