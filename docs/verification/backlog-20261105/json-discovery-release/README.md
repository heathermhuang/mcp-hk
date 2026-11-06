# Streamed JSON discovery release — 6 November 2026

PR #152 is deployed at `d76b1d6a62e98dae01d29ce0f70bebdc2d9b71fc`.
All five exact-main CI workflow groups passed, as did 903 local Python tests
(122 expected skips), quality checks and 173 Worker tests. Worker version
`52d10b2c-4923-4ce7-950b-268d13e8de40` and container application version 77
adopted immutable image
`sha256:95aa019a66769eb2e6b3aaff4d29a44ab98675e8b5de192b018421b127ae64c3`.
The provider subsequently reported a running version-77 instance. Actual private
controller diagnostics identified the same source commit with clear leases.

The initial application/controller observations still described the previous
release. The Worker version binding was independently correct, and later reads
confirmed adoption. No additional deployment, forced restart or immediate-update
policy was used. The timing is consistent with Cloudflare's [documented default
300-second Durable Object update deferral](https://developers.cloudflare.com/changelog/post/2026-10-30-durable-objects-deferred-code-updates/); `controller-adoption.json` preserves
that interpretation separately from the actual observations.

All nine original JSON resources now advertise their explicit supported array
paths. Actual HTTP queried all 13 advertised arrays, with complete-source schema,
integer totals and bounded data. Native MCP queries pinned to those HTTP versions
matched all 13 totals and returned items. This includes source `Header` and
`Counts` metadata arrays. The 46,410/83,871/28,951/157,523 data-array row counts
are not unique datasets, workers, homes or transactions. Language representations
remain separate; no semantic normalization, equivalence approval or binding was
added. Record bodies are omitted from these durable summaries.

Four existing point bindings, the Census/RVD sources, Citybus/KMB/NLB comparisons,
and caller-scoped historical-date actions passed actual HTTP/native MCP
regressions. Missing caller parameters still return no borrowed choices or
implicit date. Nine earlier internal slot/recovery operations were rechecked
once under verified quiet capacity: five succeeded; four WFS selections returned
403 and remain exact access holds. Source denials were not retried.

The fresh post-client accepted archive
`cdfafed0cd1b403a3f0cc18cf145a3810f40ab8211afc02b6123a0d2918387a9`
restored 318,255,104 SQLite bytes / 349,399,549 total bytes from a
111,156,515-byte immutable R2 archive. Full integrity, capture hashes, registry,
accepted packs, both inventory generations, six bindings, 84 workbook choices,
three WFS metadata scopes and 34 pre-existing HKMA variant facts passed.
All 13 new JSON variant hash/count/selection facts and nine resources' explicit
choices survived. Restored HTTP/native MCP metadata, old/new reads and scoped
actions made zero provider requests. Large streamed JSON record bodies are not
claimed as offline cached.

All five original schedules were independently read back after restoration,
final health/readiness passed, and only the owned release slot was released.
The exact 02:00 restaurant event was preserved as pending at that observation
and subsequently settled as success through the native scheduler at 02:19:18 UTC.
No operator refresh or additional schedule was used; see `scheduled-job-followup.json`. The wider frozen programme
remains open: see the dated before/after selection graphs and the complete
execution plan. This release does not complete the remaining backlog.
