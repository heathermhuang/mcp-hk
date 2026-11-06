# HKO forecast-track list — released 7 November 2026

PR [#177](https://github.com/heathermhuang/mcp-hk/pull/177) is deployed at
`7cb7aed5a83a62f18f127c8770d36bbedbf25e15`. All five exact-main workflows passed. Actual Worker
`4891f426-04d0-4b82-b19b-5050d00083bc`, controller, immutable image and native application /
running instance version 87 passed adoption/readiness.

The exact original XML list matched hosted HTTP/native MCP. Observed raw entries:
0; source empty collection: True. The
[publisher dictionary](https://www.weather.gov.hk/wxinfo/currwx/HKO_TCTrackInfo_DataDictionary_en.pdf)
declares four XML text fields and explicitly permits absent TropicalCyclone items
when HKO issues no forecast track. An empty list therefore exposes the declared
schema with zero observed values. Populated lists preserve original IDs, text and
URLs without fetching linked tracks. Strict structure and field checks remain.
This is a statement about that issuer's list, not worldwide cyclone absence,
current observation, emergency advice or safety. The separate GML track placeholder
remains unqualified; no empty-list rule was extended to it. A 300-second validation
target is operational and does not promise a provider update interval.

The recovery pipeline waited for natural 601-second expiry before staging current
contexts; timestamps and TTLs were not altered. Staged versions may differ from
earlier live versions. Fresh accepted archive
`d5122bfaa2c094e47ec1f387efc1f1a38ebc31a8001031884cc7683f2f657076` was retrieved from immutable R2 and independently
restored: 121,970,117 archive / 363,311,104 SQLite /
394,466,387 total restored bytes. Checksums, SQLite integrity,
accepted packs, captures, source registry, inventories and retained bindings/facts
passed. Staged cyclone-list HTTP/native MCP matched with zero provider attempts. Prior
legacy list metadata retained its version, schema hash and record count; this does
not claim historical record bodies were recovered.
Legacy transport, points, scoped actions, lookup, published interfaces, recycling,
HKSTP, wind and Hydro-held recovery checks passed. These checks do not establish
new geographic, current-service, active-vacancy or wind-observation semantics.

Hydro records remain denied pending source reuse clarification. No source rights
or public Hydro access was activated. Original request, cache, variant, source and
150/500/750 MB recovery bounds remain. Only resource cron was paused, with native
schedule read-back, full propagation and natural lease clearance. The pre-release
checkpoint restored before deployment. All five schedules were restored/read back,
final health passed and only the owned slot closed. Qualification lanes resumed
the same validated processes or retained their terminal reasons.

A read-only reconciliation of saved graphs before the source pause recorded
1,156 accepted ArcGIS query selections, 44 WFS selections, 671 non-report workbook
selections and 3,952 report selections. Known missing operations were respectively
219, 1,027, 1,217 and 1,565. These are dated graph-operation counts, not unique
datasets or semantic gains; unknown branches may add choices. Source failures and
all observed bounds remain retained. See `saved-graphs-summary.json`. A separate
zero-HTTP pass records each cohort's exact next unsaved operation under the
qualifier's ordering in `saved-frontiers.json`; this is a continuation pointer,
not evidence that an operation was attempted.

The two exact published CSDI references absent from the frozen native catalogue
were checked once at the native metadata endpoint. Both returned HTTP 404 with
`Id not found.` Replacement IDs remain unverified. This does not prove that either
dataset is globally unavailable; no record requests, catalogue writes or acceptance
changes were made. See `csdi-exact-missing-reference-review.json`.

The whole programme remains open: wider frozen graphs, source-native builder and
format/capacity work, exact access/reuse holds and independently supported semantic
tasks. A selected raw operation is not whole-dataset or semantic acceptance.
