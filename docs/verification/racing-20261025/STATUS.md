# Racing execution state — 25 October 2026

**Engineering in progress; no source-qualified or deployed racing facts.**
Branch `codex/racing-onboarding-20261025` uses a fresh clone from main
`9521ef6857e92250d35b45dca09337eb328ed3d2`. No source capture, production database,
source schedule, external contract or provider outreach has been created.

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
- [ ] Complete fresh review/corrections, mandatory exact-HEAD checks and CI.
- [ ] Acquire shared release slot, reconcile current main, PR/merge/gate-only deploy.
- [ ] Verify live gate/legacy regressions, actual runtime adoption and recovery.

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
| R09 | Review/checks underway | Final pushed HEAD/CI receipts |
| R10 | No production mutation yet | Gate-only release may proceed; full data activation remains source/recovery dependent |

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
checksum and expiry; replay rechecks current policy and expiry. No actual HKJC
bytes have been collected or persisted by this engineering release.

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

Do not poll providers or rerun full audits while permission is unchanged. The next
source-dependent step is an existing written grant or explicit authority to send
the prepared enquiry. When a grant arrives, hash/qualify each route/field/mode,
implement/review permitted real-capture parsers, then run the
complete meeting -> season -> bounded family/history -> prospective sequence.
Recheck current main, host recovery/combined capacity and the shared slot before
integration/release. Live activation needs backend/schema-first rollout, complete
source backup/offsite download/restore, actual runtime adoption, restored five
schedules and an ordinary permitted occurrence. Manual tests do not prove daily RPO.
