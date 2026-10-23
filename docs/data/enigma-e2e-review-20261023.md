# Enigma archival company pack: review and release qualification

Review scope: audit PR #53 plus the normalizer, indexed backend and shared
REST/MCP gateway in PR #54. The original source remains the independently audited
Enigma archive. This is not current-government verification or a Renavon data copy.

## Consolidated findings

All four blocking P2 findings were corrected:

1. **Audit loader privileges survived retries.** `archive_restore.loader_setup`
   recreates the loader, escapes database GRANT patterns and validates the exact
   expected privileges, including after INSERT revocation. A fresh disconnected
   MySQL test began with global privileges and verified that retry removes them.
2. **A stalled pipe could bypass the import deadline.** `archive_restore.DeadlineWriter`
   uses nonblocking writes and selector deadlines; a real non-consuming subprocess
   regression now times out. The remaining subprocess wait also respects the total
   deadline. Failed attempts keep their receipts and partial database.
3. **The curated extra was absent from locks.** Both `uv.lock` and the all-extras
   `requirements.lock` were regenerated without unrelated package upgrades. A fresh
   `uv sync --locked --all-extras` succeeded. CI checks lock/export consistency.
4. **Serving-role checks missed replication and memberships.** The shared
   `curated.security.safe_reader_role` gate rejects elevated attributes and every
   membership path, including NOINHERIT/SET ROLE, at grant time and runtime. Real
   PostgreSQL regressions cover replication and three elevated predefined roles.

The final adapter also pins selection-to-detail/history versions, names the
referenced parties/roles, restricts organisation routes to organisations and serves
the retained attribution notice. Explicit source failures, malformed identities,
redirects, expired cursors, unsupported as-of dates, output limits and unavailable
configuration remain failures; none become successful empty datasets.

**No blocking code findings remain in this reviewed candidate.** Production gates
below are not claims of completed deployment.

## End-to-end evidence

[Full-model gateway receipt](enigma-gateway-e2e-20261023.json) records actual network
HTTP and remote MCP calls through the shared gateway, private backend and the
3,957,949-entity PostgreSQL model. All six operations returned HTTP 200, matched
MCP data/version/warnings, and retained named officer/staff parties. A REST cursor
continued in MCP on the same release. Bilingual search and detail/name/officer/
licence paths took 22.76–33.34 ms in this local run. This is a bounded probe, not a
production throughput/SLA result.

The gateway used a minimal isolated catalogue fixture; production source data was not altered.

[Packaged-container evidence](enigma-container-e2e-20261023.json) additionally verifies real REST/MCP search/detail and cross-transport pagination through the built gateway and backend. The gateway image has no PostgreSQL driver, and both images exclude the private cache and credentials. The production HTTPS proxy configuration also validates offline.

The original 399 MB backup checksum, fresh-database restore, 150 additional
source-record comparisons and all-table/FK/dictionary reconciliation remain valid;
these reader/adapter changes do not rebuild or alter source facts. The new
PostgreSQL contract tests use separate private databases and cannot replace the
full-model or caller publication pointer.

Final local checks: 322 Python tests passed with seven pre-existing optional
network skips; the real PostgreSQL contracts ran. Formatting/lint, generated Worker
types and all 94 Worker tests passed. The exact pushed commit must also pass its
pre-push hook and Python 3.10/3.11/3.12, PostgreSQL and Worker CI.

## Release state and remaining gates

Audit PR #53 merged after green CI. PR #54 targets main and contains the private
backend, shared public adapters, conditional discovery and optional Cloudflare
origin/secret wiring. Existing production `/healthz` and `/readyz` returned 200 on
the previous `4692f9a` release before these changes; its accepted checkpoint and
maintenance state were not changed during review.

A dedicated persistent host is still required for the measured 6.25 GB model.
The proposed 2-vCPU/4-GiB/80-GiB host costs US$24/month, with US$4.80/month weekly
backups, before tax and existing Cloudflare usage (official pricing checked on
23 October 2026). New recurring billing approval is pending; no host was created.
The repository includes a production Compose/HTTPS bundle with no published
PostgreSQL/backend ports and an immutable official proxy image reference.

Before claiming production completion: provision the approved host; create separate
owner/reader/backend/cursor credentials; restore and qualify the candidate; store
and restore-test an offsite logical backup; verify authenticated HTTPS; enable the
gateway origin/secret; perform the documented resource-cron pause/propagation,
lease/adoption and five-schedule restore procedure; then verify live REST/MCP and
legacy readiness against the exact released commit. Do not clear an interrupted
maintenance lease or mix this database with the legacy checkpoint.

Current-government updates, a richer explorer and racing remain later phases.
