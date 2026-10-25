# Fresh candidate review and corrections

Scope: actual racing source modules, additive migration, public gate, shared
registration, discovery, tests and reviewed execution contract. The release scope
is gate-only public integration plus disabled offline engineering. It is not
approval of a live collector/parser, retained-source licence or production export.

Correctness/security/data-semantics review fixed these actionable issues:

1. **P1, checkpoint integrity:** incremental checkpoint writes replaced the initial
   request-inventory hash. Writes now merge the checkpoint, resume requires that
   hash, and a new run continues from its declared next item within fresh run caps.
   Failed/unknown admissions remain reserved and block automatic reattempts.
2. **P1, durable source holds:** a daily-row-only hold could disappear at UTC
   rollover. A singleton source hold now survives rollover, and uncertain requests
   independently block new jobs. Tests cover 304/403/429/503 and interrupted reads.
3. **P1, immutable snapshots:** an UPDATE moving a row from an accepted version to
   a staging version could bypass a NEW-only trigger. Both OLD and NEW version
   states are checked; all fact inserts/updates/deletes after validation fail.
4. **P1, scope qualification:** the observation reader could select pool/change
   rows under odds permission. The requested kind now selects its own family
   policy and is a fixed SQL filter. Public data endpoints remain unconditionally
   gated; no current route/tool can expose facts, including a permissive fixture.
5. **P1, complete recovery:** initial restore proof covered fact tables only.
   Full source-state comparison now includes policy, migration, jobs, attempts,
   budgets, holds, accepted pointer and permitted buffered bytes, in addition to
   every fact/coverage row and version metadata, using bounded server cursors.
6. **P2, season scope:** race coverage previously compared a meeting against all
   races in a version. It now distinguishes season meeting inventory and individual
   meeting/race inventories; two-meeting tests include all declared/withdrawn facts.
7. **P2, mode/field semantics:** history, export and public output rights must not
   imply each other. Staging requires history only for an explicitly historical
   bundle; operator publication checks its selected modes; exports check their
   own mode, and historical exports additionally check history. Reader output
   fields are explicitly checked and Decimal/date scalars remain strings.
8. **P2, migration safety:** reserved PostgreSQL `placing` needed quoting; migration
   source checksum now prevents silently changing an applied source migration.
9. **P2, retained replay:** source bytes require explicit bounded raw-retention
   permission, a checksum and expiry; each replay rechecks the current policy.
   Reordered/unknown source fields and unknown result codes fail closed.

The added status tool changes unconfigured tool discovery from 28 to 29, so the
two exact-count assertions changed with it; no gate was relaxed. Optional-driver
startup and isolated PDF extraction both passed in the normal test environment.
Their restricted-sandbox failures were not fixed by altering application behavior.

**No blocking findings for the gate-only release after these corrections.**
Actual HKJC parser/layout/dictionaries, source permission, complete real coverage,
production source writer, capacity reservation, backup/offsite retention coverage,
mode-specific public adapters/downloads and ordinary operation remain explicit
activation gates. Synthetic contracts and local restore do not close them.
