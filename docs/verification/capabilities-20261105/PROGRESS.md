# Capability expansion, 5 November 2026

Authorized programme: P0/P1 discovery, P2 selections/predicates, P3 independently
qualified school/clinic nearby, P4 complete bus ETA comparison, P5 first cohort.
No source-policy activation, credentials, new services, schedules or paid evals.

## Checklist

- [x] Preserve dirty primary; use isolated checkout and mandatory exact-head hook.
- [x] PR #128 transport/shared-text/GTFS dependency merged after green CI.
- [x] P0/P1 implemented and merged (#129); current 5,048-entry checkpoint reconciled.
- [x] P2 typed selections and predicates merged (#130/#131), including streamed totals.
- [x] P4 complete candidate comparison and source coverage merged (#132).
- [x] P3 shared nearby and independently reviewed school/clinic overlays merged (#134).
- [x] P5 first inherited-service HTTP/MCP cohort and one measured workbook onboarding.
- [x] Fresh accepted pre-release R2 checkpoint independently restored and sized.
- [ ] First unfinished package: final P5 integration checks/PR/CI and merge.
- [ ] Coordinated release: pause only resource cron, propagation/owning lease, actual
  controller/container adoption, live new HTTP/MCP flows, fresh accepted post-release
  backup/isolated restore and read-back of the five configured schedules.
- [ ] Later family batches remain a bounded ongoing backlog, not a promise that every
  representation or all 5,048 entries are semantically qualified.

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

P0 current-generation proof now uses the configured native Cloudflare/R2 login.
Accepted archive: 92,302,122 bytes, producer checksum
00250013b5f436ac2bcd0436800473973a13bdd6772596a7a6e0a2a3ff2c0c56,
accepted 2026-11-05T11:59:30.084Z. Independent restore validated archive/captures,
SQLite integrity and accepted base packs: database 420,438,016 bytes, total restored
451,582,461 bytes. All 150/500/750 MB bounds are unchanged. The read-only report
left the restored database checksum unchanged, with zero government-provider requests.

Generation e10744696ea04c6fad6e96d13c0199d4 reconciles 5,048 datasets/64,012 resources,
41,169 native queryable resources and 4,034 datasets with an accepted representation;
1,014 lack one. These are dated native access counts, not semantic task coverage.
The final report adds an exact unchanged-checkpoint comparison: full matrix 3.32 s,
unchanged comparison 1.08 s locally. WMS/WFS retain their actual protocols even when
hosted by ArcGIS. Candidate uncovered selector cohorts are 99 ArcGIS-layer datasets,
75 WFS datasets and 14 workbook datasets; these groups overlap and are not unlock
promises. Full metadata projection coverage is checked separately from provider reads.

The live inherited-service cohort passed real HTTP and FastMCP calls: declared-C
station temperature with source observation time, 2024 whole-district statistics,
version-pinned official company identities/BRN namespaces including literal leading
zeros, and explicit Enigma archive separation without name-based identity joins.
No collection or model call was started. The historical Census workbook had zero
accepted representations before the cohort; E101e now has a 22-row accepted raw grid,
with 2006/2011/2016 columns preserved. Its other 83 sheets and analytical units remain
unqualified. This is one observed selected-representation gain, not a whole-catalogue
acceptance claim. See inherited-services-live.json.

Final integration preserves failures after invalid defaults and nullable prior check
times, honours literal dotted-key types, hides prior callers' source parameters and
internal cache hashes, pins metadata generations during publication, and terminates
ordered pagination at its declared window. Existing qualified HKO receipts inherit
the documented timezone-aware updateTime comparison without a new provider read.
Backend health exposes resource-capabilities-2 and the immutable point manifest.
Physical checkpoint fixtures restore new options/bindings, active/previous generations,
and old and new client reads. No new index, infrastructure, source policy, quota or
schedule is introduced.

Operator access provenance: initial use of an alternate worktree file was rejected
by automatic review. Read-only inspection then proved the deployed a36e7d9 checkout
already uses that exact file through its configured symlink, with the same repository
remote. Automatic re-review accepted one direct diagnostic request using that intended
configuration; it succeeded with source-review-11, no maintenance lease and no seed
lease. No credential was printed, copied, rotated or introduced. The initial file-source
question is superseded by verified current-release configuration, not inferred consent.

The one metadata-only coverage pass enumerated 5,048 unique current native entries
across 51 pages in 4.25 s; every entry has explicit capabilities or unknown/held
semantics, with zero provider requests and no new per-dataset tools. Final metadata
lookup samples measured resource p95 3.55 ms (64 samples) and single-dataset p95
29.51 ms (62 samples), with a 148.37 ms maximum dataset lookup. These are local
isolated-copy results; production CPU/latency remains a release check.

Final focused regression set: 124 passed, including transport scalar identity guards
which reject boolean stop sequences, unknown ETA directions and an explicit wrong
operator. These malformed feeds cannot be reinterpreted as an empty directional feed.
The full exact-head Python/Worker/format/lint/type hook and final integration CI follow.
