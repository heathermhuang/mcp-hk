# Remaining-backlog implementation releases — 6 November 2026

PR #148 is deployed at `b53ae1039642e22908ef9fe5e6da2a93bc4139cf`. All five
exact-main CI groups and the full local checks passed. Cloudflare version
`acac20f5-b1d0-4be6-a991-8fdcac57dd2a` adopted application version 75 and image
`sha256:0585458753edb04094a5673ebd191a1b73b0f085a7c23bd08d05ec4dee0e443f`.
Actual controller diagnostics, backend `hkma-pages-2`, six-binding health and
accepted-pack readiness were verified after the owned pause/propagation/lease gates.

The hosted HKMA query returned `SOURCE_HTTP_ERROR`. HTTP and native MCP metadata
both held the source, with no partial/empty success and no repeated source denial.
This release corrects false completeness; it does not clear HKMA access or claim
new live HKMA records. Existing HTTP/native MCP point, Census, RVD and bus
regressions passed. An additional LWB comparison checked all six expanded native
candidates in 13 resource lookups in each client, with matching coverage and no
failed/unchecked choices. Calendars, unique vehicles and globally earliest service
remain unverified. E101e still returned 22 raw-grid rows.

The fresh post-client accepted archive
`ad000a759486d7f1f21f02967988c64610b28342f1c01e736c68d86132fb21a9`
restored 315,248,640 SQLite bytes / 346,393,085 total bytes from a 109,123,214-byte
archive. Integrity, captures/registry, packs, both inventory generations, six
bindings, 84 workbook choices, three repaired WFS metadata scopes and 34
pre-existing HKMA variant hashes/schema fingerprints/counts passed. Restored
old/new HTTP/native MCP reads and the HKMA held-metadata check made zero provider
requests. All five original schedules were restored and independently read back;
final health passed and the owned slot was released. Receipts: `hkma-release/`.

After this release, the existing generic parameterized reader also passed actual
HTTP/MCP qualification for the airport's explicitly requested historical response:
two native date-group records containing 404 nested list observations. The second
returned source date was retained. This is raw response-group access, with no
unique-flight count, flattened flight-query capability or event-time binding claim.
That later read is separate from the release checkpoint's recovery evidence.

## Earlier WFS release

PR #144 is deployed at `ad69dc0324f4ac3f4c243e57d98e4eb7f6f8e143`, with all five
exact-main CI groups passed. Cloudflare version
`304883ef-737d-4dd3-aa96-8c6c81c771f7` adopted application version 74 and image
`sha256:6f315bda1f2dc42d506f8e0539e98c67b90c173881eb47591030edb681c3f90a`.
The first application observation described the old image; a later authoritative
read confirmed adoption. The rollout was not repeated to resolve the observation.

Actual HTTP and native MCP now accept three exact planning WFS selections: 16
current-amendment, 2,179 current-application and 1,324 historical-amendment features,
with native before/after counts and matching client data. Historical applications
remain limited by the existing paging window; the separate outline-plan view
remains limited by the existing individual-record bound. These are selected views,
not new distinct datasets, unique applications or an atomic publication snapshot.
The existing point/Census/RVD/bus regression cohort passed. E101e still returns 22
rows. KMB 11C's exact-name boarding pole is 44.55 m from TD stop 4001, outside the
unchanged 35 m gate; its mapping remains unverified rather than relaxing that gate.

The fresh immutable R2 checkpoint
`45ad2c6839db6c2bf8d507e5deb0b8d1fba7e8cc76c909afb7441f605e905d90`
restored 312,782,848 SQLite bytes / 343,927,293 total bytes from a 107,632,509-byte
archive. Full integrity, captures/registry, accepted packs, inventory generations,
six bindings, 84 workbook choices and all three repaired WFS selections' accepted
metadata/hashes passed. Old/new local HTTP and native MCP reads, including the
small repaired WFS view, made zero provider requests. Larger views still require
live providers for their records; metadata recovery is not an offline-data claim.
All five original schedules were restored and independently read back, final
controller/backend readiness passed, and the owned slot was released. Receipts
are in `wfs-release/`.

PR #145 subsequently merged an operator-only qualification ordering improvement.
Its five CI groups passed; it does not change the released Worker/container.
Queries now follow their accepted schema before sibling selections can evict it.
The regression crosses the 50-variant boundary and proves that a fully saved
resumed graph makes zero requests. Remaining qualification continues under the
existing bounds; this release does not complete the wider programme.

## Previous repair release

PRs #141–#143 are merged and deployed at
`ced4b819f2c534c8c6440bf3d328476184b5b681`. All five exact-main CI groups passed.
Cloudflare version `158cca65-ebb8-4397-8eaf-912ef2551c75` adopted immutable image
`sha256:beb98695ecd51f55b1591ebbacb9ff600ee14beb143bbe3da1415d46af705f52`.
Private controller diagnostics, the authoritative container application, actual
backend health/readiness and changed source/client behavior were verified. An
initial cached container-info response still described the previous image; a fresh
read of the same authoritative API confirmed application version 73 and the new
digest. No deployment was repeated to resolve that stale observation.

Actual HTTP and native FastMCP regressions passed the four new point bindings,
Census series, RVD028, Citybus and NLB cohorts. KMB route 103 now verifies using
the explicitly published same-stop operator label. Both clients checked all four
KMB candidates in 40 source lookups: routes 1, 103 and 11K passed, while route 11C
retained `TRANSPORT_MAPPING_UNVERIFIED`. Coverage remains partial and never claims
a globally earliest bus. The two formerly timed-out ArcGIS selections now reach
the unchanged 128 MB streamed representation ceiling and return
`SOURCE_TOO_LARGE`: these remain internal capacity holds, not accepted reads or
provider refusals. Exact receipts are in `repair-release/`.

The fresh post-client accepted checkpoint
`00ea623ecf9b153b6ccb852549e6535cd22aade6e197e09175b2d8aa0ed50454`
was retrieved by immutable R2 key and restored in isolation. Its 106,967,463-byte
archive restored 311,889,920 SQLite bytes and 343,034,365 total bytes. Integrity,
capture hashes, accepted packs, source registry, both inventory generations, six
point bindings and 84 workbook choices passed. Old/new local HTTP and native MCP
reads made zero provider requests. All five schedules were restored and
independently read back; the owned release slot was released. The broader frozen
programme remains open, including remaining selections, WFS parsing investigation
and the exact KMB 11C mapping hold.

## Earlier integration release

PRs #139 and #140 are merged and deployed at
`a687580e03977e7fab76a0306bdd83973d4b8300`. This is an implemented/released increment,
not completion of the wider frozen qualification programme. First unfinished work:
remaining exact ArcGIS/WFS/workbook/report selections and demonstrated shared gaps;
KMB mapping/request-bound partial coverage remains visible.

All five exact-main CI groups passed: Python 3.10/3.11/3.12 and distributables,
quality, Worker/types, real PostgreSQL and rendered-browser regressions. The final
mandatory local hook passed 856 Python tests (122 expected optional/integration
skips) and 173 Worker tests. The parent dirty checkout was preserved.

Actual production HTTP and native FastMCP passed all four new point bindings
(45 ambulance-depot, 95 fire-station, 184 library and 18 museum source features),
a 56-row issue-scoped Census series and 22 RVD028 count-reconciled WFS features.
Raw values, source context/CRS, source feature grain and missing semantic claims
remain explicit. All 83 remaining named historical workbook sheets were separately
accepted through the previously released reader as raw grids, with no invented
unit/period normalization and no extra distinct-dataset record-operation gain.
The original E101e baseline still returned 22 rows after this cohort.

Citybus and NLB completed both HTTP/MCP comparison cohorts: four Citybus references
in 12 source lookups; 11 expanded NLB candidates in seven lookups, including five
verified reverse-order exclusions. KMB verified a live choice, retained one mapping
failure and two unchecked references at the unchanged 64-lookup ceiling. Both
clients exposed the same coverage meanings. No partial result claimed a globally
earliest bus, current calendar, walking feasibility or fastest arrival.

Cloudflare version `10df27f6-43c1-4693-87e2-452ec85bb939` adopted immutable image
`sha256:2cf4287389e91b30113ee17507270bb0917890b83a00056d82a6a3f86b0d49cf`.
The private controller matched the source commit, source-review policy and credential
boundary. Actual backend health independently returned `resource-capabilities-3`
and the expected six-binding manifest; accepted packs were ready. Static headers
alone were not used as adoption proof.

A GitHub Actions startup incident initially deferred rollout: all five schedules
were restored and the owned slot released while the old backend stayed healthy.
The resumed rollout again paused only resource cron and respected 15-minute
propagation and actual maintenance/seed leases. Wrangler 4.143 uploaded Worker code
but failed registry authorization; authoritative checks exposed new controller/old
backend state. Isolated current Wrangler 4.158, using the same existing OAuth grant,
pushed the verified exact image. Pinned-image rollout and the documented fresh-
checkpoint restart completed adoption. No credential or project dependency changed.
Failed/uncertain receipts were retained; no lease was cleared to force progress.

The fresh accepted post-client archive was independently retrieved from immutable
R2 and restored with its producer checksum:
`5a022bf3c2df026da2c6d444bcf6ee3a035e8e5664642b12b6a3f680f9248b66`.
It restored 311,885,824 SQLite bytes / 343,030,269 total bytes from a 106,969,098-byte
archive. Full integrity, source captures/registry, both inventory generations,
all six point bindings, 84 workbook choices and 17,289 restaurant / 18 population /
62,147 transport rows passed. Old and new local HTTP/native MCP reads against that
actual isolated restore made zero provider requests. The 150/500/750 MB bounds,
4 MB row cache, 50 variants and existing source/scan budgets remain unchanged.

All five original schedules were restored and independently read back through
the Cloudflare API. Final controller/backend readiness passed and the owned slot
was released. Fresh SFC/full-HKEX activation, new services/schedules/credentials and
paid model evaluations were not introduced. Exact runtime, CI, source, restore,
schedule and slot receipts are in `released/`.
