# Racing execution state — 25 October 2026

**Gate-only engineering released; no source-qualified racing facts.**
[PR #73](https://github.com/heathermhuang/mcp-hk/pull/73) shipped the disabled racing
engineering and public status gate. Its actual controller adoption was observed
at source `cfb45e70cffdf18525a0c3b4d0a7a30e853f7de5`, Worker version
`6999daed-6754-4496-898c-e9be5878589a`. The live browser check found a passive
analytics notice focus defect; the explicitly approved correction is merged in
[PR #80](https://github.com/heathermhuang/mcp-hk/pull/80). Final release receipts
are recorded in [RELEASED.md](RELEASED.md).

That initial gate-only release created no HKJC capture, production racing
schema/data/writer, source schedule, provider contract or outreach. Production
collection/retention/public-output modes remain unqualified. The prepared permission enquiry remains **unsent**.

## Current development stage

The user subsequently clarified that the working product should be built before
licensing is resolved. A [working private real-data prototype](DEVELOPMENT.md) now
exists: 9/9 Happy Valley result races on 21 October, 104 rows, bilingual factual
reconciliation, explorer/REST/MCP/downloads and isolated local restore. Its source
licence remains unverified. It is a separate loopback process; production data
modes remain unchanged. Do not treat the unsent enquiry as a development blocker.

## Execution checklist

- [x] Read/copy reviewed source/shared/review contracts; preserve other checkouts.
- [x] Search project-owned rights evidence and current primary service notices.
- [x] Prepare a precise [unsent permission enquiry](permission-request-UNSENT.md).
- [x] Add independent additive racing schema, namespaced IDs, typed units,
  source policy/capture/version/coverage/jobs/budget relations and immutable facts.
- [x] Add offline bilingual synthetic table and data-semantics contracts.
- [x] Add bounded single-session capture engine, durable attempts/unknown holds,
  checkpoint/idempotency and policy checks before/after retrieval.
- [x] Add gated public REST/MCP status and bilingual source-status page;
  data routes return typed 503 and data tools/downloads remain unavailable.
- [x] Add source-specific offline immutable export and prospective gap/capacity
  contracts; exports remain denied in the public product.
- [x] Run real PostgreSQL tests including independent full-source-version restore.
- [x] Complete fresh review/corrections, mandatory exact-HEAD checks and CI.
- [x] Acquire shared release slot, reconcile current main, PR/merge/gate-only deploy.
- [x] Verify live gate/legacy regressions, actual runtime adoption and fresh gateway recovery.

## Milestone boundaries

| Work | Implemented/tested state | Held evidence/action |
| --- | --- | --- |
| R01 | Bounded rights/family inventory; no grant found | Provider-qualified routes, completed official meeting/season inventory |
| R02 | Independent schema/policy/identity/units/lineage/version/CAS/restore core | Production source-scoped writer provisioning and measured live grants when activation justified |
| R03 | Synthetic bilingual parser/collector/failure tests | Actual HKJC layout parser and dictionaries require permitted real captures; fixtures do not qualify routes |
| R04 | Independent declared/result set reconciliation | Every real race/runner/profile in one complete meeting |
| R05 | Gated status REST/MCP/browser, disabled data routes; bounded reader/export contracts | Version-pinned real fact parity and allowed actual downloads |
| R06 | Resumable checkpoint and coverage tables | Complete 2025/26 official season inventory and reconciled facts |
| R07 | Every mapped family accounted for; strict sectional/dividend units | Permitted real backfill, earliest/latest range, all gaps/amendments |
| R08 | Prospective observation/gap/capacity contracts | Actual authorised start/cadence/retention and permitted ordinary occurrence |
| R09 | Fresh review/corrections, 488 Python/112 Worker checks and required CI passed | Real source acceptance remains independent of engineering checks |
| R10 | Public gate deployed and actual adoption observed; existing packs preserved | Full data activation remains source/coverage/recovery dependent; see release receipts |

No full racing milestone (P8/P9/P10) is claimed complete. There is no betting,
football, Mark Six, media replication, predicted outcome or vendor-history parity.

## Data and recovery contracts

The additive `002_racing.sql` lives in an independent `racing` schema; no sibling
migration/order dependency or accepted CR/Enigma pointer mutation is introduced.
Migration digest is recorded and an applied SQL file cannot silently change.
Published snapshots remain immutable, amendments use new selected revisions and
retain prior versions; compare-and-swap changes only `hkjc_racing`.

All identifiers are strings. Horse number and draw are separate. Times/weights and
money/odds are Decimal text/NUMERIC with explicit units; unknown outcome codes fail
closed. Each fact references capture checksum/transform/run/policy/time precision.
Current profiles do not imply past effective values. Private source bytes can be buffered only with explicit raw-retention permission,
checksum and expiry; replay rechecks current policy and expiry. The initial gate-only release collected no actual HKJC bytes. The subsequent
private prototype transiently parses public results pages, retaining normalized
factual fields and checksums, not page bodies; see DEVELOPMENT.md.

The full-version restore hashes every row of each racing fact/coverage/capture
relation using a bounded server cursor, and compares policy/version metadata in a
different database. Tests dump and restore the complete racing schema. They are
local synthetic recovery evidence, **not independent offsite production recovery**.
The current source migration is not part of the existing official-only offsite
backup job. Do not activate racing growth until one coordinated backup covers it
and a real downloaded copy restores all racing facts under the shared runbook.

The collector reserves attempts/maximum bytes before network work. Ambiguous
requests survive a crash and block fresh jobs until operator reconciliation.
Provider holds survive UTC rollover in singleton source state. One session lock,
no redirects, fixed qualified origins/routes, 400 KiB decompressed response,
40 attempts/16 MiB per run, 200 attempts/64 MiB daily and ten minutes are engineering
ceilings, not provider-approved quotas. No collection is public-request triggered.

Reader uses four shared slots, SELECT-only role checks, 2 s statement and 250 ms
lock bounds, 2 MiB output and signed release/filter/mode cursors capped by qualified
retention. Synthetic bundles are rejected by reader as public facts. The gateway
has a code-level source qualification gate; environment/caller flags cannot expose
data. Source status is truthful and independent of base readiness.

## Deterministic continuation

Continue the working private prototype with independently reconciled declarations,
additional meetings/venues and bounded finished-season coverage. Source and mode
assessment for an intended public launch can proceed independently; the unsent
permission enquiry is not a blanket development prerequisite. Preserve its honest
unverified licence status and do not infer terms acceptance, outreach, paid access,
access-control bypass or production publication from private build authorization.

Recheck current main, host recovery/combined capacity and the shared slot before
any production integration/release. Source activation still needs a deliberate
backend/schema-first rollout, source-specific backup/restore, actual runtime
adoption and measured ordinary operation. Local pilot results are not a claim of
finished-season/history/series completion or daily production RPO.
