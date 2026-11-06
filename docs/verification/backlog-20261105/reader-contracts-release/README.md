# Reader request/serialization contracts — released 6 November 2026

PRs [#159](https://github.com/heathermhuang/mcp-hk/pull/159),
[#160](https://github.com/heathermhuang/mcp-hk/pull/160) and
[#161](https://github.com/heathermhuang/mcp-hk/pull/161) are deployed at
`ffe09b2b6ac33390d2355e8626cc2b7db396baac`. All five exact-final-main workflows passed. Worker
`6e321df3-9d57-4002-b2ff-8ef5a5ca4da0`, immutable image, private controller and native
application/running-instance version 80 were independently verified.

The coordinate API now exposes five conditional input modes and preserves raw
coordinates/reference digits. Exact source readers handle Fire Services flat CSV
at XLSX URLs, Audit Commission JSON object sequences, fixed notification JSONP and
the TID XML declaration prefix. Other URLs keep their ordinary parsers. Partial
framing, arbitrary JavaScript, duplicate keys, forbidden entities and malformed
markup remain rejected. Original source-byte hashes and fields are preserved.
Notification rows carry no active-notice claim; no new geographic binding is added.

Actual hosted HTTP/native MCP checked nine transformation input scopes at one
resource and twenty serialization resources individually. 26 scopes passed parity
(9 transformation scopes / 17 serialization resources); 3 remain explicit
unresolved cases below. These are raw source scopes, not distinct dataset/entity
gains or language/period equivalence. Old four published interfaces, vector-map
metadata, four point profiles, Census/RVD, CTB/KMB/NLB, LocationSearch and scoped
historical actions also passed their actual client regressions.

| Original resource | Scoped input | HTTP / exact unresolved reason |
|---|---|---|
| `656fde3a4a402d2e33d856f2619a9ec3` | `{}` | 422 / SOURCE_PARSE_ERROR |
| `3b66489e3a40df4b50d0dcf76b31950c` | `{}` | 422 / SOURCE_PARSE_ERROR |
| `f101df40374314150d641d26f4cdb625` | `{}` | 422 / SOURCE_PARSE_ERROR |

A fresh accepted post-client archive `4341b890a2deebfec57d05d500dc946289c03578852add79468a7ba1536fed90`
was retrieved independently from immutable R2. Its 115,839,841 bytes restored
332,058,624 SQLite / 363,213,907 total bytes. Producer checksum,
capture hashes, SQLite integrity, accepted packs, both inventory generations,
source registry, six existing point bindings, 84 workbook choices and retained
JSON/WFS/HKMA facts passed. All 26 refreshed accepted new scopes and the prior
client contexts passed local HTTP/native MCP against that actual restored database,
with zero provider requests. Unresolved scopes are retained separately and are not
claimed as recovered records. Recovery/cache/source/scan/variant limits are unchanged.

Only resource cron was paused; the other four schedules were preserved. Native
five/four-schedule reads timed the full propagation window. Both qualification
processes paused at the owned gate. The verified pre-deploy archive was taken
after propagation and native lease release. The additional TID repair was discovered
in the wait window, checked/merged and included in the final image; the earlier
two-PR image was never activated. Controller/image/instance adoption was awaited
without redeployment or lease clearing. All five schedules were independently
read back, final health/readiness passed, only the owned slot was released and
source processes were resumed according to their observed state.

The per-resource original-body diagnostic covered all 24 remaining parse cases
using six saved captures and eighteen guarded requests. Eleven are HTML; ten have
malformed JSON; one TID feed is now handled and two siblings remain malformed.
Census HTML pages publish fourteen distinct unfetched files. Their native-link/task
adapter work is unfinished: HTML does not prove absent data, and discovered links
do not prove file availability, record acceptance or representation equivalence.
The hosted Audit accounts failure is separately reproduced as an internal reader
gap: its 1,337 strict top-level objects use comma separators without an enclosing
array. It is not classified as an upstream denial or repaired by guessing fields.
The first gateway client-minute 429 remains in the canary history; after the
original window elapsed, the same client succeeded under the unchanged 60/minute
limit. These internal events are distinct from the two malformed TID source holds.
The wider frozen qualification graphs, exact schema/capacity/task investigations
and evidence-supported semantic work remain open. This release does not finish
the complete backlog programme.
