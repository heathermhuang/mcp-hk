# Native-ID notification detail — released 7 November 2026

PR [#181](https://github.com/heathermhuang/mcp-hk/pull/181) is deployed at
`b22381d510976d23b2ddb5c0505f7c3ec7fbfddd`. All five exact-main workflows passed. Actual Worker
`fd014cfe-131a-457a-bfdd-d2957ced4d49`, controller, immutable image and native application /
running instance version 88 passed adoption/readiness.

The exact original detail resource matched hosted HTTP/native MCP for the explicit
native ID in `notification-live.json`: one original record and ten fields, with
source identity checked against the requested ID. The complete `NotiDetail(...)`
wrapper is decoded without executing JavaScript. Subject/message strings, source
ID and timestamp integers remain native. Embedded HTML, structured-message strings,
image/link references and other content are neither rendered nor followed by the
adapter. The [publisher dictionary](https://www.gov.hk/en/about/govdirectory/mobileapps/psi/iamsmart_newsandalerts/datasets/iAMSmartNews%26AlertsDataSpec.pdf)
links detail IDs to the list. Its list/detail timestamp-unit descriptions differ;
units and active-alert/currentness/safety qualification remain unverified. A dated
accepted detail does not establish a complete or currently active notification feed.

The recovery pipeline waited for natural 601-second expiry before refreshing its
accepted contexts; validation timestamps, TTLs and clocks were not modified. This
does not force a provider read for every unexpired cache. Refreshed staged versions
may differ from earlier live versions. Fresh accepted archive
`eed97306163931b89b1b4aaec6c9e9f314cb06906d51a682471ccb593008694e` was retrieved from immutable R2 and independently
restored: 123,143,850 archive / 365,322,240 SQLite /
396,477,523 total restored bytes. Checksum, SQLite integrity,
captures, accepted packs, source registry, both inventory generations and retained
bindings/facts passed. Staged notification HTTP/native MCP matched with zero
provider attempts. Available legacy transport, points, explicit actions, location, three published
record interfaces, recycling, HKSTP, wind, cyclone-list and Hydro-held checks passed.
RVD and Identify record canaries remain separately recorded source holds.
Retained legacy cyclone metadata kept its version, schema hash and count; historical
record bodies are not claimed recovered. Expired transport observations are not
current-service evidence. Geographic, vacancy, wind-time and safety claims remain
outside these raw-operation checks.

Only resource cron was paused, with native schedule read-back, full propagation
and natural lease clearance. A fresh pre-deployment checkpoint restored before
rollout. All five schedules were restored/read back; final health passed and only
the owned slot closed. Qualification lanes resumed their same validated processes
or retained their terminal reasons. Source/row/field/cache/variant and 150/500/750 MB
recovery limits remain unchanged. Hydro records remain denied pending reuse
clarification. No new source permission, credential, quota or provider identity was
introduced. The build evidence preserves the single earlier source-pilot overlap;
release/source checks use the coordinated paused lanes.

## RVD and Identify source holds; verifier limitations

The exact `csdi:RVD028` record canary returned HTTP 502. The first verifier raised
before saving its response body; its original failed receipt is retained locally
and identified by hash in `rvd-first-failure-summary.json`. Current readonly
HTTP/native MCP metadata agrees on `SOURCE_UNAVAILABLE` and held record access.
The exact fetch/protocol/query code is unchanged from the preceding production
release, and this resource cannot enter the new notification profile. The precise
transport cause remains unknown; no provider request was retried or alternate
host/header/proxy introduced. Prior 22-row metadata/version/schema facts survive
fresh isolated recovery with matching HTTP/native MCP held metadata and zero
provider attempts. This is not recovery or availability of current RVD records.
The release receipt sets full legacy-regression clearance to false and separates
available-scope successes from this hold.

The Identify API query also returned HTTP 502, with a captured SOURCE_UNAVAILABLE /
connection-timeout message. The other three published record interfaces passed.
Its current held metadata and prior two-row version/schema/count facts matched
isolated HTTP/native MCP with zero provider attempts. No Identify source retry
or current-record recovery is claimed. Both holds remain in the release receipt;
the closing verifier was corrected to require these exact held outcomes instead
of asserting all four published record canaries succeeded.

A subsequent verifier stopped before execution because two copied helper files
were absent. They were restored and all referenced paths checked. Failed logs
were preserved; the already passed steps were reused and only unrun live checks
continued. The future query verifier now saves bounded error/correlation metadata
before raising. These operational corrections did not change production code,
source observations, request identity or quotas.

## Saved qualification and failure evidence

The zero-source-call saved-graph checkpoint recorded accepted query selections
1,313 ArcGIS, 44 WFS, 671 non-report workbook and 4,434 report selections. Missing branches and exact saved frontiers remain in the adjacent
receipts. These dated, overlapping raw-operation counts do not count unique
datasets, entities or semantic gains. Further discovery can add choices.

The separate `unresolved-failure-audit/` compares the original 451 unresolved-cause
planning routes with the earlier accepted capacity checkpoint
`bedd08ce92ee3028e00596398c75c963b258ed8d7a1c1eaa6284f5991e917e92`.
Ten resources have explicit saved error receipts (three HTTP 403 messages and seven
connection-timeout messages); the other 441 lack those scoped receipts. Latest
root-check statuses and accepted variant metadata are recorded separately: nine
resources retain fourteen accepted variants. Isolated HTTP/native MCP catalogue
metadata matched for all nine with zero provider attempts. No record queries or
raw-record availability claims were made, and no new acceptance was counted.
A readable LegCo catalogue and document-reader timeouts do not establish its API
failure cause. All unknown causes, source denials and dated facts remain preserved;
none was retried or reinterpreted as empty data.

A separate bounded inspection, while both qualification lanes were confirmed
paused, fetched the three original historical Census XML-labelled archives once
each. All returned HTTP 200. Their outer ZIPs contain 23 / 19 / 25 nested ZIPs;
the existing reader stops because it does not select nested archives. Saved-byte
inspection found native XML and XSD in each inner archive, with 29,090,610 total
expanded bytes across all three resources. The ordinary XML reader replayed all
67 saved `Observation` scopes (11,078 / 8,460 / 10,551 raw elements) without source
calls. This is an unfinished nested-archive selection adapter, not an upstream
refusal or whole-resource acceptance. Original language/table/file equivalence and
statistical normalization remain unqualified. Full receipts are compressed under
`census16-nested-xml-frontier/`; no public source-status write or reader activation
was made by this diagnostic. This becomes the next demonstrated B2 reader task.

The complete programme remains open: wider frozen selections, source-native task/
reader and capacity work, and independently supported semantic tasks. This release
closes only the demonstrated native-ID detail framing gap and its release gates.
