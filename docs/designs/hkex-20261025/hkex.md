# HKEX Part XV disclosures: implementation and live acceptance plan

Date: 25 October 2026. Owner: the separate HKEX execution chat. Read
[shared.md](shared.md) first. This owns P7-03/04 and its own P7-05 acceptance.
Scope is disclosure-of-interests filings, not market prices, CCASS, order books,
trades, portfolio recommendations or a reconstructed current beneficial-owner graph.

## 1. Outcome and source qualification

Deliver a source-qualified issuer/filing explorer with original filing identity,
typed interests, amendment/withdrawal history, explicit date semantics, bounded
coverage, REST/MCP parity and permitted bilingual browser/download surfaces.
No live HKEX DI connector exists at this planning baseline. Synthetic fixtures and
an unsent source brief do not establish collection or redistribution permission.

Official sources checked on 25 October:

- [HKEX terms](https://www.hkex.com.hk/global/exchange/terms-of-use?sc_lang=en)
  restrict programmatic access and redistribution/compilation absent permission,
  and also address linking. Determine applicable DI-specific terms or express
  authorisation; general website availability does not authorise this connector.
- [DI entry point](https://di.hkex.com.hk/): separates DION notices since 3 July
  2017 from the older channel covering 1 April 2003–2 October 2017, including a
  transition overlap. Do not merge those ranges or claim older history by default.
- [Official notice-list guide](https://di.hkex.com.hk/di/notes/NSAllFormList.htm):
  explains paginated lists, form serial identity and amendments/supersession/
  withdrawals. Search ordering uses relevant-event date; this is not necessarily
  filing or publication order. Use the guide to design reconciliation, not to
  infer an approved automated route.
- [DION FAQ](https://www2.hkexnews.hk/-/media/HKEXnews/Homepage/Shareholding-Disclosures/Disclosure-of-Interests-Online-DION-System/dion-faq.pdf)
  is a service reference for publication timing; verify current normal/half-day
  rules before scheduler activation rather than hard-coding a calendar assumption.

First inspect existing project-owned permission records and the unsent brief in
`docs/data/qualification/company-permission-briefs.md`. Qualify exact listing and
detail routes, session/automation, all needed form types, pagination, incremental
listing/date semantics, permitted fields, retention, history, backups, derived
normalisation, public REST/MCP/browser, source hyperlinks and exports separately.
Even a source-link-only fallback needs its own supported basis. Do not scrape the
restricted service to prove a pilot while qualification is pending; no browser,
proxy or undocumented endpoint bypass. Continue offline schema/parser/API/test work.

If a licensed feed is required, prepare the exact supported route, capabilities,
price/limits/contract and missing rights for a human decision. Do not purchase,
accept new terms or send the prepared permission request without explicit authority.
If an existing licence permits only a subset, implement and label that subset;
do not assert full DI or filing-history coverage from it.

## 2. Pilot and date/completeness rules

Start with **one exact issuer and one declared seven-calendar-day window**. Record
issuer source ID, stock-code string/share classes, exact local interval endpoints,
window basis (filing/submission/publication/event), timezone and source filter
semantics before fetching. Preserve leading-zero stock codes and distinguish issuer
identity from a listed security/share class and from an SFC CE or registry BRN.
Choose a recent closed window with genuine notices after permission, using a
deterministic approved inventory; do not enumerate unrelated issuers to find it.

The intended first pilot is a seven-day **filing** window. A source search filtered
or sorted by relevant-event date cannot prove complete filing-window coverage:
late filings may have older events. Obtain a qualified filing/publication inventory
or authorised bounding method that covers all possible relevant-event dates and
reconcile the exact filing set. If that is unavailable within budget/rights, the
filing-window gate fails. Deliver an explicitly event-window pilot as a separately
labelled subset only if useful and qualified; do not silently rename it complete
filing coverage. Source fields that do not expose filing/publication timestamps stay
unknown; retrieval time never fills them.

Complete all listing pages, form families/share classes/subordinate lists in the
declared scope and their detail pages. Follow superseded/amending links within
approved budgets even when the linked filing lies outside the nominal window;
record why it was included and the closure limit. A missing linked notice is an
explicit unresolved relation, not a fabricated record. If recursion/caps prevent
closure, mark the pilot incomplete and resume. List/result totals alone are not
proof: reconcile unique serials, pages, boundaries, detail hashes and revision links.

## 3. Schema and interpretation

| Relation | Key and contract |
|---|---|
| issuers/securities | `hkex:issuer:<source-id>`; source stock code/share class with dated names; no name-only merge or permanent code-to-issuer assumption |
| filings | `hkex:di:<form-serial>`; source form type, issuer, subject as disclosed, reason codes, event date, filed/submitted date, published date, observed UTC, precision/timezone |
| filing revisions | Parent/amending serial links, superseded/withdrawn state and source withdrawal date; preserve all versions and unresolved referenced IDs |
| interest groups/lines | Filing + source section/line key; capacity, direct/deemed nature, long/short/lending-pool position, security class, shares/percentage, before/after where explicitly declared |
| transaction particulars | Only declared fields, decimal shares/price/currency/units and reason-code meaning; not an exchange-executed trade feed |
| parties/associations | Filing-scoped disclosed identities and explicit links; source global party ID only where actually supplied; associated-corporation/debenture form links kept typed |
| code dictionaries | Source family/code/label/version and qualification reference; unknown codes retained/rejected explicitly, not guessed |
| captures/jobs/coverage | Raw/transform hashes where permitted, source policy, page/checkpoint inventory, window basis/range, expected/accepted serials, missing details/links, budgets/holds |

Store numeric strings losslessly with Decimal/NUMERIC and explicit units/rounding.
Unknown shares/percentage are not zero. Same-serial changed content is a new capture
revision, not an overwrite. Reject self-replacement; detect cycles and inconsistent
supersession chains. Distinguish both “latest capture of this notice” and “currently
effective notice in an amendment chain”. Do not erase withdrawn notices or continue
presenting their interests as current without the required label.

Do not sum interests across parties/filings to infer total ownership: deemed/indirect
positions can overlap. Disclosures are not a current holdings register, and amounts
in a notice are not proof of executed trades. Avoid unrelated personal addresses,
contact details, signatures or identity-document fields. Raw PDFs/HTML/attachments
are private or unretained according to qualification; derived normalisation does
not by itself grant public reuse rights. No arbitrary public filer-name harvesting.

## 4. Work packages

| ID | Depends on | Implementation | Acceptance |
|---|---|---|---|
| H01 | Baseline | Per-route/mode qualification, intended use, exact issuer/window/date basis, form/code dictionaries and approved page discovery | Explicit evidence matrix; no inferred permission or filing-date completeness |
| H02 | H01 contract | Add source schema, immutable filing/capture/revision/interests/coverage contracts, source policy and read grants | Fresh/mixed migration order, exact IDs/decimals/date/revision tests |
| H03 | H02 | Synthetic parsers for qualified response contract and all in-scope form types, bounded listing/detail collector, checkpoint/holds/idempotency | Page-boundary, amendment closure, source denial/drift/crash/cap tests; zero network when disabled |
| H04 | H01 route rights, H03 | One issuer/seven-day pilot with complete approved inventory/detail/revision closure | Every unique expected serial/page/detail reconciles, missing/overlap boundaries explicit, filing-window gate enforced |
| H05 | H02–04 | Private versioned reader, shared REST/MCP adapter, status and enabled-mode discovery; immutable permitted export builder | Version/filter/cursor parity, no forbidden fields/raw documents or runtime export |
| H06 | H05 | EN/繁中 issuer -> notices -> detail/revision journey with source/date/coverage explanations | Rendered desktop/mobile/keyboard flows, amendments/withdrawals and correct empty/incomplete states |
| H07 | H04–06 | Bounded incremental refresh, late-notice/correction lookback policy, source-mode retention, backup/recovery integration | No false watermark from event ordering; proven refresh window and explicit lag/gaps |
| H08 | Candidate complete | Fresh code/security/data review and fixes; real PostgreSQL, mandatory exact-HEAD checks and CI | No unresolved blocker; full pilot restore and failure/privacy/identity tests pass |
| H09 | H08 + rights + shared release slot | Merge, backend-first deploy, publish qualified pilot and activate allowed surfaces/jobs | Actual adoption, HTTP/MCP/bilingual browser/download matrix, schedules restored, accepted recovery and rollback proof |
| H10 | H09 | Observe an ordinary qualified update and independent backup/offsite restore under deterministic scheduling | Actual occurrence and source date evidence, measured caps/costs, retained prior data on source failure |

Separate PRs at schema/parser, reader/surfaces and qualified activation boundaries
when useful; don't merge unreviewed wide schema/infrastructure rewrites. H02/H03 and
disabled H05/H06 can proceed before provider permission. All reachable authorised
work should finish; synthetic/deactivated deployment alone does not satisfy H09.

Initial caps are 40 reads/run, 100/day, one concurrent source request, ten-minute
run, 16 MiB/run and 32 MiB/day, subject to stricter provider limits. All session,
listing/detail/amendment reads and failures count. A pilot larger than caps resumes
across occurrences; never use the public guide's page size as a completeness shortcut.
Historical pre-DION retrieval is a separately qualified later extension; account for
the transition overlap with exact serial/source identities instead of date-only dedup.

For incremental updates, use a true qualified filing/publication cursor if available.
Otherwise specify a measured overlap/reconciliation strategy with an honest bounded
coverage guarantee; event-date watermarking alone is unsafe. Do not invent a finite
late-filing bound. If no bounded strategy can prove complete refresh, expose the
limitation and keep comprehensive freshness claims disabled. Proposed daily check
18:30 Asia/Hong_Kong (10:30 UTC) must be validated against current normal/half-day
publication rules and other jobs. It is a check, not a guarantee that all filings
for the day have appeared. Weekend/holiday handling follows a qualified source
calendar or explicit no-new-publication states.

## 5. Public surfaces

| REST | MCP | Contract |
|---|---|---|
| `GET /api/v1/hkex/issuers` | `hk_hkex_issuers` | Exact stock code or allowed bounded issuer prefix, issuer/security distinction and partial coverage |
| `GET /api/v1/hkex/disclosures` | `hk_hkex_disclosures` | Required issuer + date range/basis, optional qualified form filter, stable serial tie-breaker and pinned version |
| `GET /api/v1/hkex/disclosures/{filing_id}` | `hk_hkex_disclosure` | Typed particulars/interests, original/changed/withdrawn state, related IDs and source dates |
| `GET /api/v1/hkex/status` | `hk_hkex_status` | Source/mode rights, accepted window basis/ranges, page/detail/link completeness, last successful observation/hold |

Validate date spans (initially no wider than 31 days), source IDs and bounded limits
before querying; a wider inventory requires separately reviewed ranges. Backend
paths mirror source namespace under `/v1/hkex`; user URLs/SQL never reach the source
adapter. Optional allowed revision subresources reuse pinned version/cursor rules.
List responses must not silently drop amendments/withdrawals. Keep originals visible
with current interpretation clearly labelled; do not mix superseded interest values
into a current summary. Long/short/lending positions remain separate.

Add `/hkex` using current UI conventions: issuer selection -> bounded filing list
with date-basis label -> notice -> amendment/withdrawal trail and source notice.
Show source-event versus submitted/published/observed dates where available; unknown
dates remain unknown. Empty completed window differs from incomplete inventory or
source failure. Source links, raw attachments and exports are independently gated.
Permitted downloads include fields/dictionaries/coverage/attribution/manifest and
checksums, not automatically every source document. Do not expose synthetic filings
or disabled capability examples as real live results.

## 6. Verification matrix

| Layer | Required cases |
|---|---|
| Identity/fields | Leading-zero codes, issuer versus security class, duplicate party names without global merging, serial grammar, all qualified form types, long/short/lending/associated/debenture structures, decimal/currency/percent precision |
| Dates/completeness | Event before filing, late filing outside event window, event-order not filing-order, equal-date pagination, inclusive/exclusive endpoints/HKT midnight, half-day/holiday publication, unknown timestamps, overlapping channel ranges |
| Revisions | Amendment in/out of pilot range, original outside range, duplicate serial with changed hash, missing parent, self-edge/cycle, withdrawal preserved, contradictory chain quarantined |
| Collector | Multi-page duplicate/omission detection, source totals versus unique detail set, changed page during fetch, oversize/login HTML/403/429/503, cap/resume/crash, persistent holds and complete-versus-partial publication |
| Policy/privacy | Each output mode exercised through writer/read/API/MCP/UI/export; no source raw documents/contacts/signatures or denied links; no scrape enabled by an unrestricted public request |
| Real pilot | Independent approved listing inventory and every serial/detail/revision checked for one issuer/exact seven-day basis; missing filing-time fields prevent false filing-window acceptance |
| Database/recovery | Grants/source isolation, mixed migration order, indexed bounded reads, signed versioned cursors across publications/expiry, compare-and-swap conflict, full-pilot offsite download/restore hash/relation equality |
| Live product/operations | REST/MCP/EN/繁中/browser same pinned facts and amendment labels; actual allowed downloads and denied modes; ordinary refresh receipt, backup/growth failure, rollback and existing-pack regressions |

Use synthetic cases for missing exotic real forms without falsely expanding real
pilot coverage. Review unknown form/code handling and source parser drift before
activation. Mandatory project/CI and shared release checks remain required.

## 7. Rollback and final evidence

Rollback only HKEX activation/jobs/pointer to a previous schema-compatible accepted
version, respecting any subsequently revoked output right. Keep captured evidence,
failed/unknown receipts, source gaps and older accepted artifacts according to policy.
No destructive schema reversal or replacement of unrelated CR/Enigma data.

Commit `docs/verification/hkex-<date>/` containing qualification and date-basis
decisions, schema/field/code contracts, full issuer/window/page/serial reconciliation,
revision closure, observed incremental limits, code/data/security review dispositions,
tests/CI, PRs/merge/adoption, live journeys/downloads, ordinary source occurrence,
offsite restore, capacity and rollback proof. Report partial/event-window coverage
as such. Finish all authorised unblocked engineering and present an exact reviewable
provider/access/commercial decision if public live activation remains blocked.
