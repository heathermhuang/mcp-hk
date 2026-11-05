# Transport search and shared dataset access, 5 November 2026

This candidate adds bus stop/name/radius search, directional route memberships,
direct route queries and verified Citybus ETA joins. Transport and the shared
catalogue/resource interface are discoverable packs. Other datasets gain Unicode
case-insensitive `contains` filters, including nested scalar fields, with the
existing typed exact filters, scan bounds, totals and pinned paging preserved.
Plain UTF-8 GTFS tables and recognised GTFS TXT archive members are readable;
published schedules remain explicitly separate from live arrivals.

## Evidence and its limits

The official downloaded files joined to **4,479 bus stops, 1,611 route records and
2,358 directional paths**. They contain both regular and special-service variants;
these counts do not establish current service or all transport-mode coverage.
The source files were downloaded over the environment's HTTPS proxy, then replayed
through the candidate index parser. Operator route/stop/ETA reads used the existing
public mcp.hk resource gateway. Candidate HTTP and in-process MCP returned matching
bilingual stops and reference-route identities.

The real-source rehearsal verified Citybus 12 from `001042` (Lan Kwai Fong,
D'Aguilar Street) to `001021` (Seymour Road, Caine Road), seven operator stops, and
to `001156` (Robinson Road, Seymour Road), sixteen operator stops. Citybus 13 was
also returned and verified for the lower stop. These are dated source observations,
not promises about the next bus when this document is read. The accompanying
[receipt](transport-search-20261105.json) retains source hashes, timestamps,
attribution and the exact verification scope.

The unmodified direct-fetch rehearsal was attempted and rejected with
`UNSAFE_SOURCE: Source resolves to a non-public network` because local provider DNS
resolves to the Mac's proxy network. Production DNS-pinning/address guards were
preserved. Thus the rehearsal does **not** qualify a new deployed container's direct
source path. Run `scripts/verify_transport_search.py` after release for actual
public HTTP/MCP adoption and source-path verification; follow the existing
production backup/isolated-restore runbook separately.

Deterministic tests cover bilingual/radius search, actual operator order independent
of TD sequence hints, mismatched locations/directions/IDs, empty/malformed stop
responses, failed ETAs, stale-index retention/cooldown, physical SQLite backup and
restore, HTTP/MCP parity, nested text filters without numeric coercion, and GTFS
encoding/member/schedule semantics. Required checks are recorded in the PR and CI.

## Other dataset gaps

The production inventory read during this audit contained 5,048 dataset entries
and 64,012 canonical resource URLs. Status counts were: 41,170 queryable; 10,442
unsupported; 4,257 restricted; 3,585 needing an adapter; 3,629 needing a selection;
397 capacity-limited; 451 unavailable; 71 schema-drifted; nine stale arrival checks;
one pending. These are resource receipts, not counts of distinct real-world
entities. A successful parser/read alone is not semantic qualification, and an
expired arrival check needs a new source read rather than a whole-network outage
label. Counts are dated and will change after new reads or releases.

| Area | Result / remaining boundary |
|---|---|
| Other queryable datasets | Shared `contains` filters improve partial names without adding a domain-specific tool per dataset. Original schemas/types/units remain authoritative. |
| GTFS | Fixed the plain-table and recognised TXT-member reader gap. Size-limited archives and old unsupported receipts are not automatically declared qualified. |
| KMB/LWB, NLB and other buses | Bus stop/direct-route references are searchable. Existing generic arrival feeds remain usable; joined operator-ID/ETA adapters beyond Citybus are follow-up work. |
| Rail and ferries | Existing generic source-parameter queries remain. These new joined bus tools do not claim rail/ferry journey planning. Fortune Ferry/Water Taxi ETA resources were reported unavailable. |
| Government Citybus/NLB batch APIs | Both stop-route and stop-ETA resources had unavailable/source-HTTP-error receipts. No batch adapter restoration is claimed. |
| SFC | Fresh register status was `not_activated`, with no accepted live version. The historical Webb archive is separate. |
| HKEX | Full-filings status was `source_unqualified`, with no accepted version. Published daily summaries and the Webb disclosure archive are separate. |
| Restricted, unsupported and changed sources | Keep exact holds and failures. Neither pack discovery nor partial-text matching changes access permission or qualifies missing semantics. |

No SFC/full-filing source collection, credential, schedule, access policy or
provider fallback was activated by this change. Government coverage remains
explicitly incomplete.
