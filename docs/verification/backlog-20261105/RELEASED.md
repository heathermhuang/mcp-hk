# Remaining-backlog implementation release — 6 November 2026

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
