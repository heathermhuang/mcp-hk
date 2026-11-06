# Remaining backlog execution — 5 November 2026

Authority: plan and implement the remaining programme through source qualification,
reviewable PRs, release, actual HTTP/MCP and fresh recovery. Earlier P0–P4 and first
P5 remain released; this programme extends them. No new source activation,
credential, service, schedule, quota increase or paid evaluation is authorized here.

## Frozen inventory and exact candidates

`candidates.json.gz` is the deterministic, exact candidate ledger produced by
`scripts/plan_backlog.py` from the preceding release's checksum-verified immutable
restore. It identifies every resource, dataset, URL, format, last failure/selection
reason and same-dataset accepted alternative in the three requested families.
It also retains every remaining uncovered dataset/family/reason group, including
binary/API candidates, for demonstrated-task triage rather than silent omission.
The gzip header has a fixed timestamp; it contains no record bodies or credentials.

Checkpoint `ed055c0f5b6106884caa0a6f7b0535cc87bebd0d6276898b74e1241e26544f00`
has 5,048 native datasets, 64,012 resource URLs and 4,036 datasets with an accepted
representation. The earlier opportunity summary had 4,034: these are dated receipt
changes, not two newly implemented capabilities in this chat. The remaining
selection cohorts without accepted alternatives are 99 ArcGIS, 75 WFS and 13
workbook dataset memberships, overlapping. E101e is already accepted.
Across all datasets, 5,584 non-queryable ArcGIS/WFS/workbook representations remain
(1,150 / 1,121 / 3,313). Alternative language/period/scope equivalence is unknown.
No count is a count of distinct government datasets, entities or semantic gains.

## Finite work packages and acceptance

| Package | Exact candidates / sequence | Acceptance and dependencies |
|---|---|---|
| B0 — ledger and capacity | Every `familyCandidates` and `residualUncoveredGroups` entry in the frozen ledger | Reconcile native counts; zero source calls/status writes; measure physical/schema/variant storage, representative incremental growth and unchanged-checkpoint behavior. First required before bulk reads. |
| B1 — explicit selections | Every ledger `needs_selection` entry in ArcGIS/WFS/workbook, prioritizing the 99/75/13 memberships without alternatives; then remaining selections with non-equivalent/unknown alternatives | Discover bounded source options, preserve namespaces/labels/periods, read exact options without inventing defaults, preserve complete ID/count reconciliation, record cost and every failure. A raw-grid/feature read establishes only its selected scope. Record truncated option sets and 50-variant retention limitations. |
| B2 — demonstrated reader gaps | Every non-selection ledger family entry; triage the 1,653 uncovered dataset/family/reason groups against B1 results and accepted source alternatives | Group identical demonstrated failures, repair shared implementation only with a minimal source fixture and uncovered task. A source denial/404 is a source hold; parsing/capacity is internal unfinished work. Binary/SQL/OCR/planner infrastructure stays deferred absent an uncovered task. No repeated whole-provider audit. |
| B3 — reviewed semantics/tasks | Library `368c1b639641cbdb729b8ec9ea4ad865`, museum `b6c922aee8773b1418f41cdaa9d31987`, fire-station `395d43bfacb4461f6774f7d14e22c7db`, ambulance-depot `2c5d0afb1ffb7ec9b27de104cd7e3767`; remaining 83 explicitly named sheets of workbook `5ab93d9a957390f887364456f799eb79`; additional B1 candidates only where their source dictionary supports a task | Independently verify each resource identity, fields, record grain, version-scoped IDs, WGS84 export policy, raw coordinate differences and completeness. Nearby means straight-line source features, no open-now/emergency/service claim. Workbook sheets retain original periods/values/footnotes; normalization requires independent evidence. No model approval. Reuse shared nearby/predicates and qualified source families. |
| B4 — KMB/LWB join | Route list `5e0220a1c8fd74795df45db20cdadf25`, route-stop `e77eb5223d5a6a5a0efd1d3f1ebf613c`, stop `f9bf5abc8a5ba5648102ed3e9f6b3d91`, ETA `853cb7eef6227f6f1c7e8fbdf73e4e02` | Enumerate actual service types/directions, verify route/stop namespace, names/location/current order/repeated visits; preserve service-type ETA ambiguity documented by KMB. Full candidate coverage before presentation; no invented default type. Independent of B1/B3. |
| B5 — NLB join | V2 route list `e93e78ef62922558d254b40ab498debe`, stops `7ecc09ed2263c187ca759ef34faf3587`, ETA `6364bb25c65c4f24f73b9b9a982c05a3` | Investigate exact schema-drift receipt first; verify operator route IDs/destination/order/stop occurrences independently of TD direction. Keep local-time timezone evidence and original ETA keys; empty/error/unknown calendars remain distinct. No automatic V1 fallback to evade a failure. |
| B6 — integration/release/recovery | Exact verified merged head for completed B1–B5, with all remaining individual holds retained | Mandatory local checks/hooks; exact-head Python 3.10/11/12, packaging, quality, Worker, PostgreSQL and browser CI. Own release slot/maintenance leases; resource-only cron pause/15-minute propagation; actual controller/container/backend adoption; HTTP/native MCP regressions; fresh accepted backup and isolated checksum/SQLite/capture/source/selection restore; all-five-schedule independent API read-back. |

## Capacity, stop rules and evidence ledger

The restored SQLite is 447,926,272 bytes, has zero free pages, and leaves
52,073,728 bytes below the unchanged 500 MB ceiling. `resource_variants` occupies
195,362,816 bytes, inventory resources 111,136,768; row cache remains bounded at
4 MB. The prior archive is 82,846,528 bytes, total restore 479,070,717 bytes.
These observations do not establish a sustainable growth rate. Measure before/
after representative source selections, compressibility, retained variants and
checkpoint/restore peak before wider acceptance. Test compaction only on an
isolated copy; never prune accepted/failed/unknown facts to make a release fit.

Keep two interactive scans/source slots, 50 variants/resource, 1 MB option metadata,
64 requests/45 seconds per comparison, existing host/daily budgets and
150/500/750 MB recovery limits. Sequential qualification probes use bounded
request/body/time limits, persist each outcome and do not retry unchanged failures.
No new scheduler/model loop. If projected growth cannot fit, implement a measured
storage repair retaining facts before more acceptance; do not silently raise limits.

Source qualification receipts, local tests, CI, deployment and actual-client results
are separate columns/states. Only source-accepted dataset/operation/selection pairs
count as gains. A metadata option, shared family hint or schema parse is not whole
dataset/task acceptance. Maintain original source fields and missing-evidence holds.

## Progress and first unfinished package

- [x] Preserve dirty primary; clean isolated checkout rebased to main `b4aaae1`.
- [x] Freeze all exact family candidates and residual uncovered groups, native counts.
- [x] B0: measured five-source growth/recovery pilot, read-only report regression,
  36-table lossless comparison and hybrid checkpoint repair. Ordinary VACUUM alone
  saved zero bytes; all-compressed metadata left an unsafe 145 MB archive margin.
  Selected hybrid: 311,255,040 restored SQLite / 106,745,164 archive bytes, with
  all fixed limits retained. Wider cohorts still need measured milestones.
- [ ] B1: every explicit-selection candidate has accepted scope or exact unresolved reason.
- [ ] B2: all demonstrated shared reader defects repaired; individual source/task holds retained.
- [ ] B3: independent new bindings and additional workbook/task evidence.
- [ ] B4: KMB/LWB complete joined comparison and source/client proof.
- [ ] B5: NLB complete joined comparison and source/client proof.
- [ ] B6: PR/CI/merge/deployment/HTTP/MCP/fresh restore/schedules complete.

**First unfinished package: remaining B1 selected reads over the complete
271-resource discovery ledger and the report/raw-workbook cohorts, plus any newly
demonstrated shared reader gaps.** Releases at `a687580`, `ced4b81` and `ad69dc0`
passed actual clients and fresh isolated recovery; see `RELEASED.md`,
`repair-release/` and `wfs-release/`. The exact WFS format and KMB 11C investigations
are resolved as accepted selections or evidenced capacity/mapping holds. This
does not finish the wider B1–B5 scope.
This checklist remains open until every unblocked work package is finished. One
cohort, a PR or a successful deployment does not complete the full backlog.

Discovery checkpoint: all 271 uncovered selection resources received one bounded
inspection, with prior receipts reused. The source advertised 569 workbook, 79 WFS
and 81 apparent ArcGIS choices under the frozen family routing. Four exact 403s
remain access holds; one recovering-runtime response remains an internal pending
read. Twenty-four CSV feature-request URLs are actually WFS, explaining their
empty REST-layer option lists. The new shared protocol detection preserves their
inventoried type name, requests complete matched-count JSON and rejects scope
parameters it cannot safely retain. This is routing correction, not 24 accepted
dataset gains. Native resource/dataset denominators are unchanged.

Implementation status: four point bindings, report/table/series discovery and raw
Census reads, KMB/NLB variant comparison and hybrid recovery are deployed and have
actual HTTP/native MCP and fresh restore proof. KMB's identical bilingual pole-code suffix is a
documented inference from nine official records; full names and strict 35 m/order
checks stay visible. More distant/changed names remain unverified.

Wider qualification uses small deterministic batches and current accepted-backup
size checkpoints. The 729 initially advertised choices are overlapping source
selections, not promised dataset gains or simultaneous retained variants. Retain
the existing 50-variant/1 MB-options bounds and re-read the baseline E101e selection
before final recovery proof. Additional report series and binary tasks require
their own explicit choices/evidence; unknown alternative equivalence is retained.

The subsequent `ad69dc0` WFS release repaired the demonstrated generic-format
failure and passed three exact planning selections plus fresh recovery. Two
related selections retain explicit paging/record capacity holds. KMB 11C's
remaining mapping failure has exact native pole/distance evidence and is held by
the unchanged 35 m gate. See `wfs-release/` for these individual outcomes.

A bounded read-only audit reconciles the 1,770 frozen Census `web_table.html`
workbook-page candidates against the fresh accepted checkpoint: 1,623 have dated
accepted alternatives for the same exact API-table task, while all 147 unresolved
candidates received one terminal check and hit the existing 8 MB decoded-response
ceiling. This establishes neither original-workbook equivalence nor newly current
upstream availability. The separate issue-scoped `wbr.html` report graph and other
unvisited/unknown selections remain open. See `census-task-audit.md`.

Operator `scripts/qualify_backlog.py --read-options --query-options` can qualify a
published leaf choice with the query endpoint's schema/count/data response. Root
metadata and non-leaf report tables still use schema discovery. This avoids a
second complete download for large selections that cannot fit the 4 MB row cache;
it does not increase that cache or any source budget. The receipt remains an actual
`operation=query` response, not an invented schema HTTP request. Existing selected
schema receipts retain their normal flow, and existing query receipts—including
failures—are reused across modes without retrying a known failure through another
endpoint. Query proof requires the complete-source schema, integer total and the
expected bounded data item count.
