# HKO provisional wind columns — released 7 November 2026

PR [#176](https://github.com/heathermhuang/mcp-hk/pull/176) is deployed at
`2ac73249b2427849f6afb178baf04685b2b88b75`. All five exact-main workflows passed. Actual Worker
`8d9cf720-ed5d-44ab-8710-cde39707f63b`, controller, immutable image and native application /
running instance version 86 were verified with readiness.

All three original language URLs matched actual HTTP/native MCP for their raw
provisional wind rows. Observed row counts: [30, 30, 30]. The official
[dictionary](https://data.weather.gov.hk/weatherAPI/hko_data/regional-weather/HKO_open_data_10min_wind_Documentation.pdf)
specifies five fields, a native calendar timestamp and ten-minute updates. Values,
N/A and calm-space markers remain native strings. The exact historical generated
sixth field is excluded only from compatibility comparison; its retained metadata
and source-declared fields remain intact. Current overflow, renamed fields, malformed
rows and unsupported shapes stay held. New variant keys revalidate the contract;
600-second caching follows the published update interval. Timezone, unique station
identity, geographic binding and current-observation freshness remain unqualified.

The recovery pipeline waited for natural 601-second expiry before context refresh;
no clock, validation timestamp or TTL was modified. Refreshed staged versions can
differ from earlier live versions. Fresh accepted archive
`3982d377b35c9998736a361fa1bbfcfd9038f8bdb37b19947c20362791333a84` was independently retrieved from immutable R2:
121,508,046 archive / 362,704,896 SQLite / 393,860,179
total restored bytes. Checksums, integrity, captures, accepted packs, registry,
inventories and retained bindings/facts passed. All three staged wind scopes matched
isolated HTTP/native MCP with zero provider attempts. Required legacy and Hydro-held
recovery checks also passed; expired transport arrivals are not called current service.

The original historical airport canary for `2026-11-05` returned HTTP 409 and
stored metadata confirmed its exact schema-drift hold. The first helper retained
the status/trace but not its response body; that limitation remains recorded. The
[provider specification](https://www.hongkongairport.com/iwov-resources/misc/opendata/Flight_Information_DataSpec_en.pdf)
supports previous-calendar-day data. The distinct explicit `2026-11-06` scope passed
HTTP/native action/context checks and staged recovery. Older-date drift was not
cleared or reinterpreted as empty data; no cause or retention guarantee is inferred.
Previously passed live steps were reused, and only unrun steps continued.

Hydro metadata still exposes the reuse review and denies public records. No source
permission or Hydro data access was activated; owner clarification remains pending.
The source/row/field/cache/variant and 150/500/750 MB recovery bounds are unchanged.
Only resource cron was paused; native five/four reads timed full propagation and
natural lease clearance. Pre-backup restored before deployment. All five schedules
were restored/read back, final health passed and only the owned release slot closed.
Same source processes resumed or retained exact terminal reasons.

The full programme stays open: wider frozen graphs, source-native builder/format
and capacity work, exact access/reuse holds, and supported semantic tasks remain.
The operator-only response-context recorder preserves bounded correlation headers
without credentials or retries; it does not establish a cause for prior internal
failures. Dated raw operations do not establish source-wide or semantic acceptance.
