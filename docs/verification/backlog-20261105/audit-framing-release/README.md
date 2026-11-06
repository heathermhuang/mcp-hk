# Audit accounts framing — released 6 November 2026

PR [#163](https://github.com/heathermhuang/mcp-hk/pull/163) is deployed at
`531292c41469a454aa6e9146575b7e3bbe25dc42`. All five exact-main workflows passed. Worker
`eb94fa0a-fc96-4b34-aa84-7a686c9210cb`, immutable image, private controller and native
application/running-instance version 81 were independently verified.

The exact Audit accounts source emits comma-separated complete JSON objects
without an enclosing array. The reader now handles that framing at this URL only.
It requires every object, separator and byte; mixed/trailing/repeated separators,
duplicate keys, suffixes and malformed arrays remain errors. Ordinary valid JSON
arrays keep their normal reader. The source-byte hash, field names, values and
order remain authoritative; no fiscal-period normalization or semantic binding is added.

The actual hosted fresh query returned 1,337 raw objects and matched native
MCP at version `b93b1345d3bd9a1cac5d486a0dcabb0905247434f47ead08178afd7f5f56a51d`. Five representative shared-reader scopes and
the existing point, Census/RVD, CTB/KMB/NLB, published-interface, LocationSearch and
historical-action regressions passed. Unchanged malformed TID responses were not
retried; their held metadata was recovered and remains separate from this repaired
internal reader gap. No dataset/language/entity equivalence is inferred.

Fresh accepted archive `1f892d6d0301c6b6cde32911afd78dfd15df43544b8e69dc301d65cb3e6f770d` was independently
retrieved from immutable R2. Its 116,074,541 bytes restored 332,431,360
SQLite / 363,586,643 total bytes. Producer checksum, captures, SQLite
integrity, accepted packs, source registry, both inventory generations, six existing
point bindings, 84 workbook choices and JSON/WFS/HKMA metadata passed. The Audit
scope and five representative contexts matched HTTP/native MCP in that actual
isolated restore with zero provider refresh attempts. All fixed recovery/cache/
source/scan/variant limits remain unchanged.

The first accepted archive also passed checksum/SQLite restoration, but three
short-lived API contexts expired before the isolated reader check. The staging
helper had treated `requireFresh` as force-download; it can reuse a valid cache.
That archive and failed verification are preserved. After natural expiry, the
same exact contexts revalidated normally and the subsequent archive passed.
The corrected staging guard checks their real validation age before backup.
No clock, source timestamps, cache lifetimes, quotas or client identities changed.

Only resource cron was paused. Native five/four-schedule reads timed full 15-minute
propagation, native leases were respected and a checksum-verified pre-deploy restore
passed. Adoption was awaited without redeployment or lease clearing. All five
schedules were independently read back, final health/readiness passed, only the
owned slot was released and the same validated qualification processes were resumed.

The full frozen programme remains open. The separate Census file-selector work
is not in this image. Wider qualification graphs, exact schema/capacity/source
investigations and evidence-supported semantic tasks continue from saved receipts.
