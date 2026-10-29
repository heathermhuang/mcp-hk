# Directory homepage verification — 29 October 2026

The approved Directory layout is implemented against the existing site shell,
bilingual family registry and catalogue API. This change is prepared for review;
no merge, deployment, source activation or new ingestion is included.

## Behavior

- Universal hero, prominent search, twelve alphabetical subject links, secondary
  MCP/HTTP connection links and the existing four-part navigation.
- Real paginated catalogue results with provider/access controls and the same
  English-title ordering for every provider. Conservative provider types and
  overlapping catalogue/connected denominators stay explicit.
- Native expandable source/scope details, available dates, terms, resource states
  and operations. Connected details reuse all thirteen shared family descriptions.
- Query/filter/page URLs, locale switching, history, keyboard expansion,
  empty/error/retry states and a complete server-rendered family fallback.
- Existing company, SFC and HKEX interfaces keep related historical and dated
  observations under the same subject, preserving their original identities,
  dates, missingness and activation/qualification boundaries.

## Validation

- Repository checks: formatting/lint, **708 Python tests passed, 122 skipped**,
  discovery generation, Worker types/TypeScript and **158 Worker tests passed**.
  The skips are the existing optional upstream and separately configured
  PostgreSQL qualification tests; CI remains authoritative for its full matrix.
- Directory browser regression: **8 cases**, English/Traditional Chinese ×
  320/390/768/1280 pixels. Search, all subject links, provider/access filters,
  pagination, disclosure keyboard use, source dates, locale persistence, history,
  empty states, errors/retry, delayed obsolete-response rejection and overflow.
  The suite uses explicit deterministic UI fixtures and is included in browser CI.
- Existing content/layout matrix: **160 surfaces, no browser errors**.
- Existing **13 discovery, source-record, privacy and locale journeys** pass.
- The local candidate uses a bounded public metadata sample for the screenshots
  below. It establishes layout and catalogue integration, not production source
  coverage, resource validation or record accuracy.

## Screenshots

| English | Traditional Chinese |
|---|---|
| [Desktop](desktop-en.png) | [Desktop](desktop-zh-Hant.png) |
| [Mobile](mobile-en.png) | [Mobile](mobile-zh-Hant.png) |

These are local candidate captures. Native source titles retain their original
language; interface copy is localized. The screenshots use 100 public source
metadata descriptors with no imported resource records, plus the locally
configured connected registry. Their counts are not production coverage claims.

## Current source boundaries

Read-only public status checks still report SFC `not_activated` with no accepted
fresh version, and retained HKEX summaries with `SOURCE_ACCESS_HOLD`, no hold
deadline and last successful source read on 27 October. Neither hold was changed.
The shared family descriptions retain the corresponding limits. A dated,
minimized receipt is in [source-boundaries.json](source-boundaries.json).

Production release remains subject to the repository's controller/container
release procedure, approval, CI and live verification. No dataset acceptance,
licensing, backfill completeness or universal queryability claim is added.
