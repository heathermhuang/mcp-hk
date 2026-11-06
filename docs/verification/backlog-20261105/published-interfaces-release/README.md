# Published request interfaces — released 6 November 2026

PR [#157](https://github.com/heathermhuang/mcp-hk/pull/157) is deployed at
`f45aa00d1ce48707a83b7455c44b32e678294f2b`. All five exact-main CI groups passed. Worker
`87e28278-bd9e-47dd-a7d6-130c1454f223`, native application and running-instance version
79, exact immutable image and private controller adoption were independently checked.

Four catalogue URLs advertised JSON/XML but pointed to publisher specification
pages. They now bind only to the documented request with explicit caller inputs.
Input requirements are available before fetching, including HK80 metre coordinates,
case-sensitive source codes and the LotIndex extent bound. Original catalogue and
response URLs remain distinct. The two vector-map specifications expose PBF/style
metadata and reject record queries without treating tiles as rows.

| Explicit publisher-example scope | HTTP/native MCP result |
|---|---|
| Identify, x=835665 / y=817198 / lang=en | parity; 2 top-level response rows |
| Nearby, same input | parity; 1,760 source response rows |
| LPPUN, gla / GLA-HK 836 | parity; 1 source response row |
| LotIndex, lot / published bounded HK80 extent | parity; 1 source response row |
| VectorMap and VectorMapLabel | metadata parity; record queries rejected |

The counts are raw scoped responses, not unique places, facilities or complete
inventories. Native coordinates remain unreviewed. No new geographic binding,
GeoAddress join, global nearest result or service/open-now claim is accepted.
Missing parameters do not borrow another caller's inputs or choices. Existing
LocationSearch, four point profiles, Census/RVD, CTB/KMB/NLB comparisons and scoped
historical actions passed actual public HTTP/native MCP regressions.

The fresh post-client archive `356d7c749a354a8106cb43f9b09d25b34c1a172f0c8dab906d64d5774268da22` was retrieved independently from immutable
R2. It restored 330,653,696 SQLite bytes / 361,808,979
total bytes from a 114,699,416-byte archive. Checksum, capture hashes,
SQLite integrity, accepted packs, both inventories, source registry, six point
bindings, 84 workbook choices, retained JSON options/variant facts and WFS/HKMA
metadata passed. Actual isolated HTTP/native MCP reads recovered all four new
explicit responses and prior client contexts with zero provider requests.
The 150/500/750 MB recovery limits and all source/cache/variant budgets are unchanged.

Only the resource cron was paused; native read-back confirmed four schedules and
the full 15-minute propagation window elapsed. The first backup wrapper referenced
the earlier script; ownership validation stopped it before any backup request.
The corrected pre-deploy backup restored successfully. A later naturally accepted
resource checkpoint superseded it, so the guard stopped deployment until that
newer immutable checkpoint was independently restored. Both receipts remain private;
`current-pre-restore-receipt.json` identifies the current verified baseline. Initial
old-controller/image observations were retained and adoption was awaited without
redeployment or lease clearing. All five schedules were independently read back,
final health/readiness passed and only the owned release slot was released.

The report/WFS process resumed at its saved operator gate. The ARC/workbook lane
had already stopped at an unavailable operator observation with its pending source
request unmade; its journal remains explicit. No source denial is retried through
another host, header or proxy. The wider frozen qualification graphs, demonstrated
reader/schema/capacity issues and evidence-supported semantic tasks remain open.
This release does not complete the entire remaining-backlog programme.
