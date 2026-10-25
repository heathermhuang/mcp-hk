# Webb directors’ disclosure archive

This product uses the actual SDI records from David Webb / Webb-site's original
released Enigma archive. The retained [original reuse notice](../../src/mcp_open_data_hk/webb-site-NOTICE.txt)
permits commercial/noncommercial reuse with attribution and notice retention. A
new licence is not a prerequisite for building with this already-released archive.
[Original repository](https://drive.google.com/drive/folders/13mzAvvufXC3QmH8OvMVx2juUi7qdnVLL).

The complete audited extraction contains 341,047 `sdi` disclosures, 426,219 `sdicap`
capacity rows, 345,355 `sdievent` rows, 84 reason codes, 33 capacity codes, 19
currencies and the 35,853 source issue mappings. The 3,064 referenced issuer
identities come from `issue.issuer`, never a stock-code identity merge. Numeric
stock codes are padded to five digits for searches/display; each record also
retains its original `source_stock_code`.

All released SDI rows have form code 3. The original `SDI.vb` collector explicitly
implements **Form 3A directors' disclosures**; this is not an archive of every HKEX
DI form. Relevant-event dates span 1994-09-19 through 2025-12-24. That range is an
observation of the released rows, not a claim of complete interval coverage.

## Field meanings

| Source | Public field | Qualification |
|---|---|---|
| `ID` | `id=webb:sdi:<ID>` | Stable only within this source identity |
| `serNo` / `filing` | `serial` / `legacy_filing_key` | Legacy numeric key is not a date; 206,950 records have a legacy key and 134,097 have a serial |
| `issueID` → `issue.issuer` | `security_id` / `issuer_id` | Original Webb mapping; not newly verified |
| `relDate` | `event_date` | Relevant event, not filing/publication |
| `awDate` | `awareness_date` | 292,589 source nulls remain unknown |
| `signDate` / `modified` | `signed_date` / `source_modified` | Signature / archived record edit |
| No source field | `filed_date`, `published_date` | Always null, never inferred from another date |
| `longShs1/2`, `shortShs1/2`, `longStk1/2`, `shortStk1/2` | `before` / `after` | Original collector's before/after relevant event rows |
| `sdicap.posType`, `sdievent.posType` | position | Collector mapping: 1 long, 2 short, 3 lending pool; other codes unknown |
| `serNoAmend`, `serNoSuper` | `revision_links` | Amends / superseded by; 145 referenced serials are absent from the release and remain unresolved |

Source FLOAT/DOUBLE numeric lexemes are strings. This preserves the dump's stored
representation, not exact original decimal input. Disclosures, including deemed
interests, do not establish executed trades, additive ownership or current holdings.
The original collector's heuristic director matching is not newly verified. The
private `ccc` and unselected issue fields are excluded from the public projection.

## Query contract

The browser at `/hkex`, REST and MCP read the same indexed PostgreSQL archive.
Fresh official HKEX collection remains a separate source and policy.

- `GET /api/v1/hkex/archive/status`: published version and exact source census.
- `GET /api/v1/hkex/archive/notice`: original attribution/reuse notice.
- `GET /api/v1/hkex/archive/issuers?stockCode=00005` or `?q=HSBC`: exact stock code
  or literal normalized issuer-name prefix, with distinct Webb issuer identities.
- `GET /api/v1/hkex/archive/disclosures?issuerId=webb:person:382`: dated records,
  default 20/max 100 per page. Optional event window is 1–31 days, end exclusive.
- `GET /api/v1/hkex/archive/disclosures/webb:sdi:331188?version=<returned-version>`:
  exact detail, positions, capacity/reason labels, source fields and revision links.

Pin the returned `meta.version`; pagination cursors are signed for the exact query,
source operation and version, expiring after 48 hours. Empty results do not disguise
source failures. SELECT-only reads share four query slots, two-second SQL bounds
and a 2 MiB response bound. Browser ZIPs contain the selected page only, JSON,
spreadsheet-safe CSV, schema, provenance, original notice and checksummed manifest.
The JSON preserves source values; CSV formula/leading-zero escapes are documented.

`hk_hkex_archive_status` is always discoverable. When explicitly enabled, MCP adds
`hk_hkex_archive_issuers`, `hk_hkex_archive_disclosures` and
`hk_hkex_archive_disclosure`. Data OpenAPI operations/tools require both the existing
private backend configuration and `MCP_HK_WEBB_SDI_ENABLED=true`. The Worker forwards
that flag only when `WEBB_SDI_ARCHIVE_ENABLED=true`. Enable only after backend/data
qualification; a sibling gateway deploy must preserve the accepted flag.

## Offline operations and recovery

Use `python -m mcp_open_data_hk.curated.webb_sdi_cli --help`. Owner and independent
restore DSNs come from `CURATED_DSN` / `CURATED_RESTORE_DSN`, never command arguments.

1. `extract --workspace <audited-source> --output <new-private-directory>` parses
   only allowlisted literal INSERT data, never executes original SQL or triggers.
   It verifies the complete source checksum and all seven source-table censuses.
2. `migrate`, then `stage --workspace <projection>` creates only `webb_sdi` state.
   Every projected byte/count/notice is verified before transactionally loading.
   Source-scoped PostgreSQL advisory lock serializes loading/publication.
3. Back up the whole `webb_sdi` schema with `pg_dump -Fc --no-owner --no-acl`,
   including versions, pointer, all data and dictionaries. Keep it outside Git and
   copy it to the existing private offsite store under a new immutable source prefix.
4. Download that object, verify its SHA256 and physically restore it into an
   independent empty database. `qualify-restore --version <version>
   --backup-sha256 <sha>` hashes **every row of all seven database tables** on both
   databases, not a sample. It rejects the same database or any changed table.
5. `grant-reader --role <dedicated-select-only-role>`, then `publish --version
   <version> [--expected-version <previous>]` atomically advances only this source's
   accepted pointer after restore qualification. No previous pointer is overwritten
   on a compare-and-swap conflict.

The static historical source needs no live HKEX requests or recurring collector.
The initial indexed model occupies about 578 MB, capped at 1 GiB. Reserve the
existing shared-host free-space floor before release; do not replace company
maintenance or its offsite runner. The gateway's SQLite backup does **not** cover
this PostgreSQL archive. Roll back consumer activation first; retain the immutable
source dump/proof and prior accepted pointer. Never restore over a live database.

Actual extraction/local complete-restore/query receipts are in
[the verification directory](../verification/webb-sdi-20261025/). Local evidence
alone does not establish production activation or offsite recovery.
