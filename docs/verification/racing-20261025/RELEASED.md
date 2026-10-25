# Released racing status gate and keyboard correction

25 October 2026. [PR #73](https://github.com/heathermhuang/mcp-hk/pull/73) released
independent disabled racing engineering and the bilingual public status gate.
[PR #80](https://github.com/heathermhuang/mcp-hk/pull/80) corrected the first-visit
keyboard focus failure discovered during live acceptance. Its push, merge and
release were explicitly approved by the user.

The released source is `9ed67301b3172b3d5d1a8df87726f976480d003d`, Worker version
`6577ea49-e74b-42b0-91ec-43a096b4f17c` at 100%. Actual controller adoption was
observed at that source, with matching backend `source-review-11` policy, healthy
readiness and no maintenance/seed lease at adoption. The provider deployment
reported the new container artifact; the backend does not independently expose
its exact image hash. See [runtime evidence](released/runtime.json).

## Acceptance evidence

- [Engineering](released/engineering.json): 488 Python tests passed, seven optional
  network tests skipped, 112 Worker tests passed, 69 real PostgreSQL contracts,
  all six source migration orders and the network-disabled Python 3.11.17 image
  smoke passed. Required candidate and merged-main CI passed, including rendered
  Chrome. No test or hook was bypassed.
- [Production browser](released/browser-live.json): both languages at 320, 390,
  768 and 1280 pixels; first Tab reaches the skip link, no horizontal overflow,
  no downloads, no page errors and no HKJC source requests. Real old/new Chrome
  evidence isolated the initial-body focus defect before the fix.
- [Live HTTP/MCP](released/live-acceptance.json): status equality, absent racing
  fact tools, typed 503 data/export routes, OpenAPI gating, ready base packs,
  archive company parity and preserved SFC status. [Five existing packs](released/base-pack-regressions.json)
  additionally passed real REST/MCP parity: restaurants, population, plates,
  property coverage and ALS addresses.
- [Native browser company download](released/legacy-download.json): exact 20 REST
  rows and 20 CSV rows, five matching manifest file hashes and explicit historical
  archive provenance. This does not imply current official company verification.
- [Post-deploy gateway recovery](released/fresh-gateway-restore.json): the current
  ordinary accepted 88,205,818-byte offsite checkpoint, created at 07:38:43 UTC,
  was downloaded using GET and restored into a temporary local SQLite file at
  07:56:11 UTC. Outer checksum, archive paths/types, capture hashes, SQLite integrity
  and required accepted packs passed (17,276 restaurants; 18 population rows).
  The exact backup pointer was stable around the check. No production backup or
  restore operation was invoked. There are no production racing facts to restore.
- [Five schedules](released/five-schedules.json): restored after actual adoption.
  The owned shared release slot was released. The resource cron alone was paused;
  the full fifteen-minute propagation window and existing lease completion were
  observed before rollout. No lease was cleared.

The first Documents-path local check encountered four read/certificate/subprocess
failures in unchanged code. The clean locked temporary environment passed all
checks without weakening tests; no filesystem root cause is asserted. An earlier
successful isolated restore overlapped a normal backup-pointer advance; the final
receipt records the exact downloaded checksum instead. Failed/uncertain private
receipts were retained.

## Remaining source gates

**No live HKJC dataset is published, and no full P8/P9/P10 milestone is complete.**
No HKJC source capture, racing production schema/data/writer, source schedule or
new infrastructure was installed; source growth reservation is zero. All source
collection/cache/history/REST/MCP/browser/link/export/scheduling modes remain
unqualified. The [prepared permission enquiry](permission-request-UNSENT.md) is
unsent. No provider contract, purchase, new terms or outreach was authorized by
the keyboard-fix approval.

An existing written route-specific grant or explicit authority to send the enquiry
is the next source-dependent step. Real captures/layout dictionaries, complete
meeting and finished-season reconciliation, bounded family/history inventory,
prospective ordinary occurrences and a coordinated source-specific offsite
backup/download/restore remain required. Synthetic fixtures, a working gate and
existing gateway backup recovery do not satisfy those requirements. Continue from
[STATUS.md](STATUS.md) without repeated provider polling while permission is unchanged.
