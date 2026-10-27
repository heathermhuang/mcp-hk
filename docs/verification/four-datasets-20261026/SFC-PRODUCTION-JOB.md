# SFC source-cycle implementation and activation boundary

The producer now has one deterministic cycle shared by local State tests and the
standard-library host adapter: bounded collection, actual offsite retrieval and
independent PostgreSQL restore, expected-old publication, and a separately restored
accepted backup. This is engineering evidence, **not** an activated fresh SFC feed.
No production role, password, token, policy, cohort or timer was created/enabled.

Migration 010 preserves applied migration 003 and records manual/timer provenance,
source release and separate collection/backup/publication/recovery outcomes. Timer
occurrences cannot relabel an existing manual run. Metadata serving keeps the
existing column-level reader grants and remains compatible with the base schema;
it does not expose private cohort/attempt fields through a whole-row conversion.
Transport uncertainty remains charged and unresolved, blocking another occurrence.

The cycle reuses a valid retained candidate before any new source read. It repairs
a failed accepted backup before collecting again. A candidate's original accepted
base is pinned, so resumption cannot automatically regress a newer pointer.
Restore success requires the actual retrieved artifact, different database identity,
all ten source-table fingerprints, manifest and facts. An accepted-backup success
also requires that the restored copy actually contains the published pointer; a
pre-publication candidate backup cannot satisfy that outcome.

The host coordinator uses a source-wide file lock and bounded 512 MiB/one-CPU,
read-only child containers. Only the scoped source-writer environment enters the
child. Database administrator credentials, uploader token and Docker socket do not.
The host creates an isolated restore database, gives the verifier SELECT on that
source copy and cluster-identity metadata, and removes only its generated restore
database afterward. Downloaded artifacts and receipts remain. No automatic cleanup
of production source versions or failed artifacts is introduced.

The optional `/__sfc-backup/` capability is closed unless its distinct token,
policy checksum and independently qualified storage-retention bound are configured.
It cannot reuse company/HKEX/operator/backend credentials or write their prefixes.
Actual streamed bytes are bounded against admission; dump checksums and immutable
objects are checked. Only a restore-verified accepted manifest with all ten table
fingerprints and a matching recovery predecessor can advance the SFC recovery
reference. Expired copies are not downloadable. Physical storage expiry/lifecycle
must still be independently qualified; response expiry is not a deletion proof.

The ordinary timer is proposed for 06:10 UTC, away from the existing source jobs.
It is a repository unit file only. The host requires an explicit `--manual` for an
operator qualification; the timer never supplies that flag. Automatic new growth
requires the existing company's `backfillRecoveryGateOpen` qualification, rather
than treating a manual restore as proof of ordinary daily RPO. Backup repairs reuse
retained data. Public SFC output modes remain independently checked by the source
policy and readers; no producer action grants them.

Activation requires these concrete items, none inferred from configuration flags:

- A reviewed exact corporate CE cohort and purpose, plus independently qualified
  access, retention, backup and each requested serving mode. The example CE is fake.
- Existing host administration was successfully read back on 27 October. The
  earlier access failure is historical; no password reset or reboot is needed.
- Approval for the source-only login credential and separate prefix-only uploader
  capability. `sfc-writer-review.sql` is review-only and defaults to NOLOGIN.
- Verified source/R2/local-copy retention and capacity. The host stops if copies
  could outlive existing facts or if expired versions require reconciliation; it
  does not delete them under the present no-destructive-cleanup boundary.
- Apply migrations/grants with existing administrator authority outside child
  images, install protected 0600 configuration in a pinned release, qualify a real
  bounded source cycle and accepted restore, and verify actual public modes before
  enabling the timer. History/export availability remains a separate serving gate.

The physical-restore tests exercise publication and both failure-resume paths,
false-success rejection, policy/recovery admission, timer provenance, stale-candidate
protection and uncertain transport. Host tests verify child credential isolation,
typed schedule parsing, retention admission and redacted failures. Worker tests
cover closed defaults, namespace/auth isolation, streamed-size limits, immutable
recovery manifests, predecessor conflicts and durable independent quotas.

Fresh SFC integration and the four-dataset programme remain incomplete.

## Current-main integration, 27 October

The source cycle and optional backup capability are integrated with current main
without activating them. The host copy deadline is the earlier of its configured
backup duration and the oldest included source expiry, measured before dumping.
Equal backup/source retention durations can qualify a candidate without resetting
its retention clock. Neither an HTTP expiry check nor this deadline proves physical
deletion; the separately approved storage-expiry procedure remains required.

The qualified reader also provides paginated observation-version history through
REST, MCP and the bilingual browser. History requires its own policy grant as well
as the caller's output mode. Cursors bind CE, policy, caller mode, page size and
accepted inventory anchor, and expire by the earliest retained version or policy
deadline. New publications cannot enter later pages. Unknown regulatory periods
are never reconstructed. The production history capability remains false.

Source-job, history and Form 3B PostgreSQL tests now run explicitly in the mandatory
database CI lane; general Python CI alone could previously skip the new files.
The exact source/credential/retention decisions are in
[the activation packet](SFC-ACTIVATION-APPROVAL-20261027.md).
