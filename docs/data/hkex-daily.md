# HKEX published daily-summary observations

The latest-summary feed reads HKEX's four public daily-summary categories:
substantial shareholders (Forms 1/2), directors' listed-corporation shares (3A),
associated-corporation shares (3B), and debentures (3C/3D). It is separate from the
historical Webb archive and from the older qualified full-filing-window framework.
Full documents, capacity/indirect-interest structures, Form 4 and s.309 notices are
not supplied by this feed. No current holdings or executed-trade inference is made.

Source: [official daily summary menu](https://di.hkex.com.hk/di/summary/NSMSumMenu.htm).
The menu's latest published report date selects the four pages. The pipeline never
uses event date as a publication watermark; notices can report much older events.
The daily summary date is a day-level report date, not a known exact filing or
publication timestamp. Those unknown timestamps remain null. Numbers in source
balance cells remain decimal strings; L/S/P and before/after remain separate.
Reason, involved amount and average price are retained as disclosed, not guessed.
Amendment/withdrawal remarks are preserved; complete full-form revision closure is
not asserted. Stock codes are not permanent issuer IDs. Raw link `sid` values are
exposed as unverified `source_search_ref`, never as verified issuer/security IDs or
joined to Webb identities.

## Source-use basis

The operator requested current public disclosures and automatic updates on
26 October 2026. This is an operator-built public-summary integration; it does not
claim a provider licence, permission grant, supported API contract or licensed-feed
status. HKEX's [terms of use](https://www.hkex.com.hk/global/exchange/terms-of-use?sc_lang=en)
include restrictions on automation and redistribution; technical availability and
this engineering implementation do not establish provider approval. The original
Webb reuse notice applies to the historical archive, not newly collected HKEX data.
Attribution and an explicit no-licence-claim notice accompany this feed and exports.
No provider outreach, purchase, new agreement or account access is performed.

## Bounded automatic collection

The owned systemd timer checks at **09:20, 13:20, 17:20, 18:20 and 22:20 HKT**,
including weekends. HKEX's published DION FAQ describes normal 17:00 and half-day
13:00 publication. These are checks, not guaranteed publication deadlines.

Each occurrence checks the menu and all four current pages; subsequent unchanged
checks can use validated ETags. The first successful occurrence of each UTC day
fully rechecks seven calendar report dates, including the current date. Normal
maximum is 49 requests/day; hard limits are 40/run, 100/day, 16 MiB/run, 32 MiB/day,
one concurrent source request, at least three seconds between starts, a two-MiB
response and a ten-minute collection bound. Failed/unknown dispatches are charged
before network I/O. An actual process crash leaves an unknown reservation requiring
review; caught GET transport failures retain their full charge and back off.

Only fixed HTTPS menu/report paths on `di.hkex.com.hk` are allowed. Redirects are
not followed. Access denial/challenge and parser drift cause durable holds;
429/503 Retry-After is respected without shortening it. No browser/proxy/IP bypass
is used. Public REST/MCP/browser requests only read PostgreSQL and never collect.

A partial current date cannot advance the pointer: all four current reports must
validate. Older unavailable/unqualified pages become explicit coverage gaps rather
than empty days. Error/login HTML cannot become a successful empty report. Even
empty valid reports require the known date/header structure and a complete body.
Default queries cover seven calendar summary days; all unobserved date/categories
are reported in `queryCoverage` and warnings, including empty queries. The current
version references up to 31 days of observed reports. Old public versions are kept
for at least the 48-hour cursor lifetime; queries can pin them for seven days.

## State and recovery

`hkex_daily` is its own schema and writer lock, with an independent non-login or
source-only login owner/writer. The existing public backend receives SELECT only.
Immutable reports are identified by both source-body SHA256 and parser transform
SHA256. Report rows and version/report maps are immutable; source reversion creates
another chronological release rather than overwriting an old snapshot. Publication
uses a base-version compare-and-swap and monotonic publication revision.

A candidate cannot publish before a whole-schema dump has been copied offsite,
downloaded, checksum-verified and physically restored into a separate database.
Every row of all seven tables and the request sequence must match. After publication
a fresh accepted offsite copy/restore includes its accepted pointer and proof.
Unchanged/failed source occurrences also refresh the accepted recovery copy daily.
A failed source/backup phase retains the accepted facts and all uncertain receipts.

The host has a dedicated prefix-only upload capability, never the gateway OPS,
company uploader, backend token or account-wide Cloudflare credential. The Worker
allows only `summary.dump`/`manifest.json` under the HKEX prefix, immutable checksum
puts, bounded durable budgets and an accepted recovery pointer guarded against older
publication revisions. Only a verified accepted manifest advances that pointer.
The private bucket's source-specific immutable copies are retained 30 days; its
latest recovery reference is outside that expiry prefix. Local completed backup
sets are bounded; partial directories are preserved for review within a 512 MiB
reserve. Publication is held at the one-GiB source ceiling and the host's existing
20-GiB free-space floor. Temporary restores never overwrite shared/live databases.

This source uses ordinary scheduled code, without model calls. Its timer/current
symlink, environment and lock are separate from company-maintenance ownership.

## Public contracts

- `/api/v1/hkex/latest/status`: accepted version, latest summary date, last check,
  source holds, pending publication and configured cadence.
- `/api/v1/hkex/latest/disclosures`: optional exact stock code and 1–31 day summary
  interval (end exclusive), default/max page sizes 20/100, signed pinned cursors.
- `/api/v1/hkex/latest/disclosures/{record_id}?version=<returned>`: exact source
  summary-row facts. Multiple observations/classes are not collapsed into holdings.
- `/api/v1/hkex/latest/notice`: source attribution and explicit scope/use notice.
- MCP: `hk_hkex_latest_status`, `hk_hkex_latest_disclosures`,
  `hk_hkex_latest_disclosure`; every tool is read-only.

Data tools/routes require the existing private backend plus
`MCP_HK_HKEX_DAILY_ENABLED=true`; Worker activation is `HKEX_DAILY_ENABLED=true`.
This remains independent of `WEBB_SDI_ARCHIVE_ENABLED` and full-filing policy modes.
The bilingual `/hkex` browser shows date/gap/check status and selected-page ZIPs
with JSON, spreadsheet-safe CSV, schema, notice, provenance and per-file hashes.
