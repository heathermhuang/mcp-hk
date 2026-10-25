# UX repair qualification — 25 October 2026

Implementation checkout: isolated from `main` at
`51dc631d7e6162c9ecc4c539d0c8b22810d017c0`. The primary checkout and its unrelated
untracked files were preserved. Production baseline advertised
`7ea79fa850dbd3d35d277853eb33bdea0d3a9a57`; it is an ancestor of main. The intervening
changes concern official-company maintenance, not a different frontend baseline.
The curated host's maintenance source already resolves to `51dc631`.

## Implemented scope

- UX-01/02: preserved catalogue scope, truthful previous/next ranges, navigable
  dataset links, focused detail/back action, schema-guided five-row scalar
  projections, explicit omitted columns, discoverable source choices, recoverable
  oversized/version/rate failures, cancellation and no post-preview inventory fan-out.
- UX-03: one search form/controller, independently completed official/archive
  groups, opt-in backend organisation grouping before pagination, bounded alias
  examples/counts, identity/version-bound cursors, further name evidence and honest
  displayed-page exports. Old archive and `official_*` bookmarks remain supported.
- UX-04: four primary destinations, company discovery from home, topic examples,
  outcome-oriented introductory steps and an initial consent notice in document
  flow. The wordmark, palette, themes and anonymous access remain intact.
- UX-05: public building/view/quality/sale-rent URLs, private search text in tab
  history state, candidate list, explicit returned-advert filter scope, obsolete
  request cancellation, plate modes with only honoured controls and restored state,
  plain-language historical-price percentiles. Neighbourhood district-wide and
  straight-line-distance qualifications remain visible.
- UX-06/07: complete bilingual HTTP walkthrough with real resource IDs and a dated
  successful weather capture, client prerequisites/status/success guidance and
  truthful pending qualification, shared API-reference entry and capability tags,
  readable source labels/status timestamps, legal contents and non-authoritative
  reading summaries. Substantive policy/effective dates remain unchanged.
- UX-08: deterministic contracts plus actual Chromium history, focus, race,
  source-failure, consent, responsive and bilingual page checks; fresh correctness
  review and corrections before release.

## Local verification

`bash scripts/check.sh all`: 336 Python tests passed, 30 skipped (23 separately
required PostgreSQL contracts and seven optional network tests); 111 Worker/UI tests
passed; Black, Flake8, generated Worker types and TypeScript checks passed.

Dedicated PostgreSQL 16: all 23 contracts passed with `CURATED_REQUIRE_DB=1`,
including physical backup/restore, optional-driver independence, old name-fact
callers, official/archive grouping, aliases spanning pages, duplicate display names,
leading-zero identities, signed cursor separation and actual HTTP/MCP parity.

Chrome `155.0.8059.85`: eight browser scenarios passed. These cover all 16 public
routes in English and Hong Kong Traditional Chinese at 320px, representative
390/768/1280px layouts, 320px reflow, keyboard skip/focus, back/refresh selection,
late-request invalidation, official legacy bookmarks, partial company-source
failure, plate mode restoration, private property input and analytics rejection.
There were no browser page exceptions. Fixtures prove deterministic behavior;
they are not production/provider success claims.

The preview browser receipt observes exactly one schema request and one record
request, with five rows and scalar projections. Refresh restores the selection
without replaying records. A synthetic single oversized geometry still fails the
unchanged item cap even at one row, while a valid scalar projection succeeds.

## Provider evidence and limitations

The attached baseline JSON files are actual MCP captures from 25 October 2026:

- Rainfall GeoJSON exposes large geometry plus district names and source links.
  Its explicit projection returns district links; it does not manufacture rainfall
  measurements from those links.
- HKO's existing English RSS bulletin returns meaningful report content, including
  bulletin time and weather observations. It is the explicit recommended
  alternative on the affected current-weather path.
- The HKO JSON representation returned `SCHEMA_DRIFT`. That failure was retained;
  no acceptance pointer, limit or schema safeguard was changed to hide it.

Client instructions were checked against current official documentation. This
task has exercised the configured remote MCP connector, but the clean installed
Codex/Claude Code/Cursor setup matrix remains pending and is labelled accordingly.
No independent unfamiliar-user or screen-reader certification is claimed.

## Consolidated correctness/UX review

No blocking findings in the reviewed final code. Corrections made during the review:

1. Prevent an old official restore from selecting its entity after a newer search;
   preserve independent official cursor state when updating shared URLs.
2. Require the grouped backend echo before a gateway/UI consumer can accept it;
   old callers continue returning name facts. Grouping is within source/version,
   with no name-based crosswalk.
3. Honour long `Retry-After` values instead of retrying early; preview performs no
   automatic retry loop and retains an explicitly labelled previous result.
4. Correct a plate-mode selector found by the expanded rendered test; hide only the
   filters that comparisons do not honour.
5. Keep sale/rent empty states and displayed counts distinct from the provider's
   recent-building qualification and whole-market inventory.
6. Keep the initial analytics notice in normal document flow so it cannot cover
   primary search at 320px; optional requests remain absent before consent.

The separate security-remediation branch remains outside this diff. Its documented
container-egress candidate gate is not represented as resolved or included in this
UX release. Current main's release/runbook gates govern this rollout.

## Release qualification

Planned, implemented, locally verified, CI verified, deployed and observed are
separate states. CI and deployment/live receipts are recorded in the release
continuation, not inferred from the local results above.

Release packaging keeps the backend-first compatibility stage. The completed
frontend packages travel together after final review rather than producing three
successive controller/container replacements; this reduces repeated cron/adoption
windows while retaining all eight packages and their acceptance obligations.
Backend rollback disables/reverts grouped consumers first; no database/schema
migration or accepted-fact mutation is required. Gateway rollback retains the
accepted checkpoint and prior application image/assets.

The resource cron pause preserves the other four configured schedules and must
remain in place until propagation, lease drain and actual backend/controller
adoption are verified. Completion additionally requires restoring all five
schedules, bounded live browser/HTTP/MCP journeys and an isolated restore of a fresh
accepted backup. Production success is not claimed by this pre-release report.
