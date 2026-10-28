# SFC activation decision and protected runtime packet

27 October 2026. **Production activation not approved or activated.** Existing production inspection
found zero SFC policies, versions and requests, no `sfc_writer` role, and no SFC
timer. Existing SSH administration works. The development CE example is not a
production cohort. This packet creates no credential and grants no source rights.

## Required cohort and source decision

The initial ten corporate targets are now selected in
[the selected-cohort packet](../sfc-selected-cohort-20261028/cohort.json).
No user-supplied firm names are needed. The immediate purpose is connector
qualification; the product purpose is public factual reference. No actual
financial dealing is asserted. The disabled technical policy uses
`connector_development`, and the [refreshed independent mode assessment](../sfc-selected-cohort-20261028/MODE-QUALIFICATION.md)
grants no collection, cache, retention, backup or public output mode.

Before activation, record the qualified purpose, evidence reference/hash, exact
route/fields, dates and each allowed duration. Each REST/MCP/browser/search/history/
export/raw decision remains independent. Unknown modes stay closed. Retained
observation history cannot establish complete regulatory history.

The policy route is the qualified corporate licence-interval route only. Do not
expand to people, contacts, AML institutions, arbitrary URLs or name matching.
The checked `Policy` model enforces exact identities, field scope, recheck expiry,
25 reads/run, 100/day, 8 MiB/run and 16 MiB/day maximum. Every session/detail/retry
must fit those existing ceilings; a 25-CE cohort may require multiple occurrences.

## Separate credential approval

The review-only SQL is [sfc-writer-review.sql](../../../deploy/curated/sfc-writer-review.sql).
It defaults to `sfc_writer NOLOGIN`, no role memberships or elevated attributes,
and only `curated_sfc` table/sequence privileges plus the cluster-identity function
needed to verify independent restores. Run the source migrations with the existing
administrator first. LOGIN/password provisioning is a separately approved protected
step; no password is included in this packet.

The writer environment is `/etc/mcp-hk-curated/sfc.env`, mode 0600, containing only
the SFC writer DSN. The host's separate `/etc/mcp-hk-curated/sfc-job.json`, mode 0600,
contains the reviewed image tag plus required immutable imageId, policy hash, exact cohort, a new independent
uploader token and qualified storage-duration/evidence hashes. Templates are
[sfc.env.example](../../../deploy/curated/sfc.env.example) and
[sfc-job.example.json](../../../deploy/curated/sfc-job.example.json).
The example CE and placeholder token are invalid for activation.

The uploader capability is restricted to `https://mcp.hk/__sfc-backup/`, immutable
`curated/sfc/source/<stamp>/{source.dump,manifest.json}` objects and the compare-and-swap
`curated/sfc/latest.json` reference. It cannot address company/HKEX/gateway backups
or arbitrary keys. New bindings are `SFC_BACKUP_TOKEN`,
`SFC_BACKUP_POLICY_SHA256` and `SFC_BACKUP_RETENTION_SECONDS`; absent bindings keep
the route closed. Existing OPS/company/HKEX/backend credentials must not be reused.
The child image receives neither uploader/admin credentials nor a Docker socket.

## Retention and capacity evidence required before real collection

Existing host free space was 43,939,008,512 bytes at the initial readback, with
3,039 MiB available memory. These are observations, not retention qualification.
The runner retains the 20 GiB disk/1 GiB memory reserves, 64 MiB/dump bound and
512 MiB source-local reserve. Reserve measured source growth, index/WAL space,
two dump copies and an isolated restore against the shared host allocation.

Review the exact physical-expiry mechanism for database facts/captures, source-local
and independently downloaded dumps, receipts containing facts, R2 immutable copies,
latest references, and failed/interrupted copies. Response expiry only denies reads;
it does not delete bytes. R2 lifecycle timing must be measured against the actual
allowed duration, including delayed deletion and any retention locks. Do not assume
a bucket-wide gateway retention rule qualifies a source-specific policy.

Prepare a uniquely named **fabricated-data canary** under the approved SFC prefix
and an exact local/database/object inventory before requesting any destructive
expiry test. Approval must name those canary objects and targets. Do not delete
existing source data, dumps or another source's objects. Until that evidence and
any needed deletion approval exist, storage retention remains unqualified and
the real source cycle must remain disabled. The code stops on expired facts or
exhausted capacity; it does not silently remove uncertain evidence.

## Ordered activation and recovery verification

1. Pin the actual policy/cohort and independently approved writer/uploader scope.
2. Apply additive migration 010 and SELECT-only status/history grants using existing
   admin access. Install protected config against the verified immutable image.
   Read back runtime policy identity and negative cross-source grants.
3. Run one explicitly manual, bounded corporate source cycle. Preserve the provider
   ledger and all failed/unknown reservations. Restore a newly retrieved candidate
   dump into an independent database and compare every source table/fact/hash.
4. Publish using the exact expected-old pointer. Independently upload/retrieve/
   restore a **second dump containing that accepted pointer**. A candidate dump
   alone cannot qualify accepted recovery. Rehearse expected-old conflict and
   rollback without replacing good source pointers.
5. Verify only qualified public modes through same-version REST/MCP, both real
   browser languages and actual allowed prebuilt exports. Export remains a separate
   artifact-delivery gate; no download is advertised or inferred from history.
6. Enable the proposed 06:10 UTC timer only after source, capacity, retention,
   recovery, runtime and public-mode gates pass. Observe its true systemd occurrence
   and candidate/accepted recovery. Manual qualification is not ordinary cadence.

Keep archive-first CE lookup independent throughout. New credentials, real source
activation and destructive canary actions require their stated separate decisions;
ordinary authorized integration/tests/release do not require another approval.
