# Working SFC archive build released — 26 October 2026

The bilingual [SFC archive lookup](https://mcp.hk/sfc) is live. Exact CE `AAB241`
returns the five expected Webb corporate licence intervals in archive version
`enigma251227-hk-v1`, including the original `2020-06-15` end date. English and
Traditional Chinese both passed at 320, 390, 768 and 1280 pixels without page
overflow or JavaScript errors. Failed replacement requests preserve labelled
prior results. A continuation cursor produces an explicit first-page notice and
a version-pinned link to the existing paginated licence history.

## Released candidate and verification

- [Implementation PR #78](https://github.com/heathermhuang/mcp-hk/pull/78),
  checked head `31a30bff7d6963c97003fc0fabd1db9aaaeeb508`, merged source
  `afb79374398f9a26c2ba984bbce50c9fe21065b3`. The merge tree exactly matched the
  checked head and incorporates the released racing and Webb disclosure work.
- Worker `3ac4d2d6-f2ed-4ebb-ac77-3d4ddc8ac8e8` at 100%; private controller
  diagnostics report the merged source, `source-aware-ux-1` and `source-review-11`.
  Actual backend health/readiness passed, including `results-r2-v1`.
- The container application reports active version 51 and image
  `sha256:2fcd358893584694ce76b764e7122c0815b56530bd0ce5d4d0b945e0668fb2d5`.
  The actual `production` instance independently reports running version 51.
  Public headers alone were not used as adoption evidence.
- Final mandatory checks: **569 Python passed**, including isolated real
  PostgreSQL; seven optional network tests skipped; **123 Worker passed**;
  formatting, lint, types and deployment dry run passed. All five CI workflows
  succeeded. Twelve rendered browser journeys cover controlled edge cases,
  including bilingual continuation-cursor disclosure.

The existing exact-CE archive read and the real operator collector are built.
The [private source pipeline proof](real-pipeline.json) fetched, parsed and staged
five actual intervals with one source request, then physically backed up and
independently restored all ten SFC tables. This release needed no paid feed or
provider enquiry; none was sent or purchased.

## Production acceptance and recovery

Only the resource cron was paused. The full 15-minute propagation window elapsed
and real maintenance/seed leases were clear before upload. The other four
schedules, existing bindings and all three secret names were preserved.

Initial fresh diagnostics still reported the preceding controller environment
after upload. The already-uploaded version was activated in the paused,
lease-free window; subsequent direct, nonce-qualified diagnostics established
adoption. No lease was cleared, application code patched, or diagnostic tail
opened to force this. This observation is consistent with Cloudflare's documented
[eventual code propagation](https://developers.cloudflare.com/durable-objects/platform/known-issues/#code-updates).

Both public origins passed SFC status parity, exact-CE archive reads, readiness,
OpenAPI contracts and unchanged pinned company archive/official observations.
The Webb disclosure archive stayed available at `webb-sdi-enigma251227-v1`.
Racing remained available with nine accepted meetings. MCP retained the company,
Webb, racing and SFC status tools (46 tools total).

All five checked-in schedules were restored and independently read back. A fresh
accepted backup created at `2026-10-26T00:57:55.738Z` was retrieved and restored
in a temporary directory: **76,767,921 bytes**, SHA-256
`69d6361fa8e6ac2e4fbf1d4cb7ce2f98dff9be5c472abacd78b570a4246068ae`.
The accepted receipt, transfer checksum, retained capture checksums, SQLite
integrity and required-pack readiness passed. All prior racing versions were
readable; the restored state contained nine accepted meetings / 1,175 result
rows. The shared release slot was released after this proof.

This is a gateway SQLite/capture restore. No fresh SFC PostgreSQL publication,
source timer, production schema or public official-source feed was activated;
the engineering build and historical archive do not claim current SFC status or
unattended source recovery objectives.

## Inspectable receipts

- [Engineering and exact-head CI](released/engineering.json)
- [Runtime adoption](released/runtime.json)
- [HTTP and MCP acceptance](released/live-acceptance.json)
- [Real archive browser scenarios](released/browser-live.json)
- [Five schedules](released/five-schedules.json)
- [Fresh independent restore](released/fresh-restore.json)
