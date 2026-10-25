# HKEX DI engineering and activation boundary

All notices in tests are invented normalized JSON, not retained provider pages.
No official HTML/PDF response parser, DI collection route, code meaning, issuer or
filing inventory is represented as qualified. `qualified_fixtures.py` remains a
separate legacy synthetic contract.

## Implemented contracts

`curated/hkex/contracts.py` strictly validates normalized issuer/security identity,
six proposed form families, filing-scoped parties, associated/debenture interests,
long/short/lending positions, before/after phases, original unrounded decimal
strings, unknown dates, source channels and correction state. Extra fields fail
closed, including contacts, addresses, signatures, source URLs and attachments.
Unknown code/form values fail qualification instead of acquiring guessed meanings.
The exact provider parser and dictionaries await an approved observed format.

`004_hkex.sql` owns a separate `hkex` schema, with no dependencies on sibling
migrations or changes to existing schemas. It includes policies, control/holds,
durable runs and requests, captures, versions/pointer, issuers/securities, immutable
versioned filings, revision links, typed NUMERIC plus original numeric text,
particulars, filing-scoped parties and versioned code dictionaries. The serving
role receives direct SELECT and a metadata-only capture view, never raw bytes or
request journals. Source writer tests demonstrate denial against `curated` state.
No production role/schema has been created by this engineering work.

The policy binds exact route/modes/fields/forms/codes, evidence reference/hash,
purpose, limits/cadence, retention, cursor expiry, inventory method, qualification,
expiry/revocation and recheck rule. Operator activation requires a separately
reviewed policy checksum. Unknown/denied are never allowed; flags cannot override
the backend's currently pinned policy. Policy changes hold older versions for
requalification, rather than retroactively granting broader rights.

The collection engine takes an injected qualified adapter; **there is no default
network adapter**. It persists reservations before dispatch, counts failures/unknown
requests and bytes, serializes the source session, retains holds and checkpoints,
refuses blind uncertain retries, and enforces caps and a ten-minute deadline.
The operator must configure `HKEX_STORAGE_ROOT` to the actual mounted host storage
before any reads; the 20 GiB reserve and 1 GiB source-growth ceiling are checked.
The initial normalized inventory requires independent serial/detail hashes and
snapshot/page closure. Event inventory cannot validate a filing window. Revision
closure includes notices outside the nominal window, detects cycles/conflicts and
never invents missing notices. Known cap/cadence partial work resumes under the next
occurrence's budget; original capture lineage remains pinned. An unchanged accepted
inventory exits after its bounded check, before page/detail/backup work.

REST, MCP and browser consumers share `hkex.py`; private paths are authenticated.
They share existing four-slot gateway/backend budgets, statement/lock timeouts,
2 MiB output bounds and signed version/filter/expiry-bound cursors. The backend
rechecks current rights before returning. Default public discovery advertises only
source status; unavailable data routes return `HKEX_SOURCE_UNQUALIFIED` and are
absent from OpenAPI/MCP discovery. Browser mode uses separate fixed routes so REST
permission cannot substitute for browser permission. Status redacts filing inventory
and any issuer identity whose consumer mode is not qualified.

`/hkex` preserves the existing bilingual forest-green design. It shows a gate with
no synthetic records by default, and has tested issuer → bounded window → notice
→ supersession/withdrawal trails once browser output is allowed. It shows unknown
source dates, observation UTC, lossless interests and source version. Unqualified
links/attachments/download controls are absent. It is noindex while source-gated.

Offline immutable ZIP construction includes all accepted serials (including revision
closure), nested JSON, spreadsheet-safe CSV summary, schema, dictionaries, coverage,
notice and per-file SHA-256 manifest. It checks export rights at each page and before
materialisation and cannot run through a public request. **No live export publication
or download URL is configured**; its route/retention depend on the actual grant.

Source backup covers all 15 source tables, raw bytes only where permitted, policies,
lineage, journals, accepted pointer and dependencies. It serializes source writes,
checks capacity, uses exclusive private dump files, independently verifies downloaded
archive checksums, restores only into an empty database, and compares every table's
canonical logical fingerprint. Serving remains SELECT-only after explicit regrant.
No new source offsite prefix/credential/job is installed before backup rights and
shared recovery/capacity coverage are qualified. The official maintenance runner,
its timers, accepted pointers and existing offsite capability remain separately owned.

## Remaining activation sequence

1. Resolve [the exact unsent request](REQUEST-UNSENT.md) or locate an applicable grant.
   Qualify all modes separately. Select one exact issuer/closed seven-day filing
   window from an authorised deterministic inventory; do not sweep for examples.
2. Inspect that approved route's real formats/dictionaries. Implement its fixed-origin,
   bounded, no-redirect transport/parser and independent filing inventory/hash contract.
   If that inventory cannot be proven, retain the filing-window gate; any useful
   authorised event-window subset must be explicitly labelled as such.
3. Recheck current shared host recovery, actual capacity/costs and source growth
   allocation. Coordinate complete new-schema offsite backup coverage without copying
   broad credentials or installing overlapping full-database backup timers.
4. Run the full source-qualified pilot, reconcile every page/serial/detail/revision,
   independently download/restore its complete offsite backup, then qualify publication.
5. Claim the shared slot and real leases; reconcile latest main and migration order;
   deploy source writer/schema/reader before data consumers. Verify actual backend,
   Worker and DO adoption, all-five schedule restoration and fresh gateway recovery.
6. Check real REST/MCP values, coverage/version parity, both language journeys,
   permitted actual archive downloads and denied modes, source failure and rollback.
7. Only after cadence/calendar/rights/headroom qualification, configure the deterministic
   source job. Record one ordinary permitted update plus offsite download/restore.
   Operator runs do not establish unattended operation or daily RPO.

The FAQ checked on 25 October (updated 14 February 2026) describes 17:00 HKT normal
business-day and 13:00 half-day publication. The proposed 18:30 check remains disabled;
calendar handling and actual completeness/lag require source-qualified evidence.
