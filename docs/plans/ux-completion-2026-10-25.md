# mcp.hk UX completion plan

Date: 25 October 2026. Status: planned and reviewed; implementation has not started.

The outcome is a complete path from a person's question to useful Hong Kong data, with readable sources, dates and limitations. People should be able to find an available task, obtain a result, understand its scope and continue in an app or AI client without first learning resource formats or ingestion terminology.

This plan addresses the 16 public pages reviewed on 25 October, including the three guide articles and API reference. It covers the shared shell, search and detail states, company discovery, existing guided searches, connection instructions, status reporting, documentation and bilingual accessibility. It does not authorize implementation, deployment or external account changes.

## 1. Baseline and constraints

- Live review: desktop page inspection, representative mobile and Traditional Chinese checks, weather resource preview, neighbourhood lookup, property search, plate history/comparisons and company archive search/detail.
- Reproduced failures: a submitted catalogue search changes the selected access filter to `all`; the first rainfall GeoJSON under “Current weather report” fails with `RESPONSE_TOO_LARGE`; company results repeat matching name facts; property selection is absent from the URL; source status exposes internal keys and a contradictory success/check timestamp.
- Useful working paths: the default neighbourhood, property, plate and archive-company examples returned real records. Preserve their working contracts and provenance.
- GitHub main inspected for planning: `51dc631d7e6162c9ecc4c539d0c8b22810d017c0`, dated 24 October 2026. This identifies the inspected repository baseline, not the deployed version.
- The primary local checkout is older (`6ff9a7a`) and contains unrelated untracked files. Implementation must begin in a fresh isolated checkout of then-current main. Reconcile the live deployment with that checkout before changing files. Do not build from the older checkout or reuse the separate security-remediation branch as the UX base.
- Preserve the mcp.hk wordmark, existing green/mint palette, current light/dark behavior and source-aware tone. The current live light theme governs light-theme work; the older design brief's dark-theme wording is not a mandate to force dark mode.
- Keep anonymous read-only access. Do not add registration, analytics consent or a paid integration as a prerequisite to viewing public data.
- Preserve HTTP/MCP names, source identities, temporal semantics, request budgets, response limits, exports and recovery protections. Frontend improvements must not imply that metadata discovery equals record access or current verification.
- No new mapping provider, framework migration, fuzzy company matching, data acquisition programme, identity-linking engine or agent-account redesign belongs in this scope. Existing map-free geographic context is sufficient for this release.

## 2. Product decisions

### Navigation and page responsibilities

Use four primary destinations: **Find data**, **Connect AI**, **Guides**, **Data status**. The logo returns home. Preserve `/coverage`, `/connect`, `/guides` and `/sources` as their URLs; this is a label/structure change, not an endpoint migration. On mobile, retain these visible destinations in a wrapping navigation row with adequate targets.

Guided capabilities remain discoverable within Find data and relevant homepage topics. Do not add a separate primary “Demos” destination. Retain `/demo` as a supported URL and call the capability “Neighbourhoods” or “Explore a neighbourhood” in the interface.

Every result page follows this order:

1. User task and input.
2. Result or useful next action.
3. Source, observation/reference date and material limitation beside the result.
4. Other sources, technical fields, API/MCP examples and diagnostic detail through disclosure.

### Search terminology

Use **All data**, **Search tools**, and **Dataset catalogue** for the current `all`, `connected` and `sources` scopes. Keep those machine values unchanged. Explain the distinction once: “Search tools have forms you can use here. Dataset entries describe available source data and whether it can be previewed.”

Default an unfiltered Find data visit to Search tools, as today. Homepage free-text/topic searches explicitly use All data. User submissions preserve an explicitly chosen scope; zero results offer “Search all data” as an explicit action.

### Shared result evidence

Show three different concepts separately:

| Concept | Example public wording | Rules |
|---|---|---|
| Access | Preview available / Settings needed / Source link only / Temporarily unavailable | Derived from actual capability and last outcome; never equate a previous read with current availability. |
| Observation or reference time | Weather issued 10:00 HKT / Population reference year 2024 / Historical archive | Keep source date precision, unknown values and scope. |
| Service check | Last successful read 25 Oct, 10:20 HKT / No successful read recorded | A retrieval/check time does not make the underlying observations current. |

Always expose the provider, original link and relevant terms. Material warnings stay visible. Raw status codes, cursor values, schema and ingestion receipts belong in expandable details.

### State and URL policy

- Define page states as idle, loading, success, valid-empty, partial, failed and expired-version where applicable. Retain input and recoverable last-successful data, labelled as the previous result, when a new request fails. Never show old results as the result of a new query.
- Deliberate search, selection, tab and pagination actions create history entries. Automatic normalization uses replaceState. Back/Forward, direct links and refresh restore the same selection and source/version context.
- Existing public discovery/company query URLs remain supported. New property URLs store building ID, view, quality filter and language; free-text address/property input stays in current-tab state rather than being automatically added to a URL. Sharing a selected building requires no free-text query.
- Never put precise neighbourhood coordinates, raw resource parameters, recovery credentials or returned records into URLs, analytics, document titles or local storage. A deliberate future “share search text” feature would require its own privacy design and is outside this release.
- Direct links may load bounded public building/company details. Generic resource parameters and record-query POSTs are never silently replayed on refresh, language change or history restoration. Restore the selection and offer Preview records.
- Use independent request generations and cancellation for search/detail/preview/export operations. Changing upstream input invalidates incompatible downstream state and prevents late responses from overwriting the latest selection.

## 3. Delivery order and work packages

Effort bands are relative: S is localized, M crosses several UI modules, L changes a shared interaction or service contract. They are not calendar promises. Each package is reviewable and independently revertible. Do not claim the overall UX work complete after the first release.

| Package | Priority / effort | Dependency | Deliverable |
|---|---|---|---|
| UX-01 | P1 / M | Baseline | Regression fixtures, URL/state contracts and targeted fixes for scope/pagination/status contradictions. |
| UX-02 | P1 / L | UX-01 | Focused dataset detail and bounded, recoverable record preview. |
| UX-03 | P1 / L | UX-01 | One company search entry, separate source groups, organisation results, readable detail and exports. |
| UX-04 | P1 / M | UX-02, UX-03 | Homepage, navigation, catalogue labels and curated task/topic entry points. |
| UX-05 | P2 / M | UX-01 | Property, plate and neighbourhood completion, including durable selections. |
| UX-06 | P1 / M | UX-02, UX-04 | Client setup, complete API walkthrough, guide index and API reference organization. |
| UX-07 | P2 / M | UX-01, UX-03 | User-facing data status and plain-language About, Terms and Privacy. |
| UX-08 | P1 / M | All packages | Final bilingual, accessibility, responsive, journey and release qualification. |

Work on shared styles and translations starts with UX-01 and accompanies each package. UX-08 is verification and correction, not the first accessibility/localization pass.

### UX-01: shared behavior and immediate defects

1. Capture deterministic response fixtures for the reviewed weather failure, filter switching, stale result races, company repeated name facts, empty official subset and contradictory status. Record source/version context without snapshotting production secrets or entire databases.
2. Preserve access scope on search. A scope change deliberately resets result pagination, dataset/resource selection and preview. Searching a new phrase resets pagination and downstream state while preserving scope.
3. Add Previous/Next plus a truthful range/page indicator to catalogue and resource lists. Store offsets in the URL. For cursor-based lists, keep signed cursor history and versions; never synthesize cursors from page numbers. A direct link without a previous cursor offers Back to first page rather than a broken Previous control.
4. Implement shared date formatting for UI-generated dates in `en-HK` and Hong Kong Traditional Chinese, explicitly using Asia/Hong_Kong. Relative times include an absolute accessible value. Preserve source-authored text and date precision in details.
5. Define a shared error presentation with explanation, next action, retry eligibility and expandable code. Honour Retry-After; never retry a non-retryable validation error automatically.
6. Fix public provider labels and status derivation immediately: a missing successful-check timestamp cannot render a claim that a successful check was recorded. An archive may be queryable without a recent upstream check; communicate those separately.
7. Reuse narrow shared helpers for dates, errors, evidence labels and page-state handling. Do not replace all page modules with a framework or broad generic renderer.

Acceptance: scope survives submit, language change and Back; pagination can return to earlier results; a new request cannot display an earlier response as current; unknown status remains unknown; retry state works with keyboard and screen-reader announcements.

### UX-02: Find data and dataset preview

**Search result list**

- Give each entry one explicit primary action: Open search tool, Preview dataset, Configure source, or Visit original source. Preserve a normal navigable link for dataset selection and give it the same visual treatment as other entries.
- Show title, concise description, provider, actionability and data/reference scope. Put resource counts and past-validation detail lower in the hierarchy.
- Collapse lengthy descriptions and offer useful English/Chinese aliases. Rank by existing relevance rules; do not silently drop less convenient or unsupported results from the inventory.

**Focused dataset detail**

- Keep the existing `/coverage?...&dataset=...&resource=...` deep-link contract. Render a focused detail view with a clear Back to results control, search context and preserved list position instead of stacking the complete lists above it.
- Show a readable title, description, provider, scope/date and a recommended compatible source when one can be justified. Resource display names describe contents, such as Rainfall by station; raw filenames remain available in details. Use checked-in explicit labels where raw metadata cannot be safely interpreted; do not generate speculative labels with a model.
- Select a recommendation using explicit dataset/source mapping or deterministic capability rules: compatible structured format, actual preview support, required settings satisfied and relevant content/language. A past read alone is insufficient to claim it works now. If no safe recommendation exists, offer a short labelled choice or Source link only.
- Put formats and alternate sources under Other sources and formats. Unsupported sources remain visible there with an explanation and original link.

**Safe preview and error recovery**

- Investigate the rainfall failure before changing behavior. The inspected reader enforces a 512,000-byte serialized-item cap and the current UI requests 20 rows; therefore a smaller count alone is not a proven fix. Check record-path selection, per-row geometry/nested payloads, field projection and response envelopes.
- For deliberate Preview records, use existing/cached schema where possible, then request at most five records with an explicit meaningful projection when the source supports one. Preserve the underlying row meaning and identify omitted columns. Geometry and large nested objects may be expandable separately; never truncate their bytes and call the result a complete record.
- Keep the response cap, upstream time/size budget and field-validation protections. Do not increase limits to hide the UX failure.
- Bound one preview action to at most one schema discovery and one record request. If it remains oversized, show “This source is too large for this preview” with Choose fields, Choose record list where valid, Other source, and Original source. Do not loop through formats, fetch the whole inventory or silently retry multiple page sizes.
- Remove unconditional whole-coverage/resource-list refreshes after each preview. Update visible evidence from the response and coalesce any necessary metadata refresh; the preview request budget includes its automatic source work. Reading an alternate source is a new explicit action.
- Required station/route/worksheet/layer choices become labelled controls when discoverable. Multiple nested record arrays require a choice; do not flatten them arbitrarily. JSON parameter editing remains advanced.
- Render preview rows as readable tables, with mobile row detail, meaningful units from documented metadata, clear missing values and original source fields available. Unknown field meaning stays unknown.
- Preserve version-pinned record pagination. A version conflict prompts Restart preview and clears invalid cursors. A source failure is never rendered as zero rows.

Acceptance: the promoted Weather → Current weather path must reach meaningful bounded records from a verified compatible existing resource. The original oversized rainfall resource must either preview correctly with an explicit valid projection/path or show a usable limitation and an explicit working alternative. Improving its error alone does not complete the weather repair. If no existing source can safely supply a working preview, remove the preview promise from that entry, retain the source link, and report this package as incomplete until the remaining limitation is resolved or explicitly accepted. Public holidays shows event rows, not a calendar wrapper. A source requiring input is usable without JSON editing when its required choices are discoverable. Existing HTTP/MCP query semantics remain compatible.

### UX-03: company discovery and detail

**One entry point, independent source results**

- One name input and one Search companies action. A plain hint explains current prefix matching; do not promise substring/fuzzy search. Identifier search is a separate advanced choice with explicit namespace labels.
- Search official observations and historical archive as independent bounded requests. Render separately labelled source groups as each completes. A failure or no result in one group never erases results from the other.
- Label official results Official records collected so far with actual coverage dates and omissions. Label archive results Historical Webb-site records with archive version and record-specific date limitations. Avoid calling official observations current registration verification.
- Do not match or merge BRNs, money-lender identifiers and Webb IDs by name. Preserve leading zeros and exact entity IDs. A selected entity carries source, namespace and version throughout detail, history, exports and links.

**Organisation grouping**

- The existing search contract returns matching name facts. Do not deduplicate only the visible 20 rows and imply a complete company count: aliases can span pages.
- Add an optional `groupBy=organisation` to HTTP/MCP company search, with omitted grouping preserving the existing matching-name-fact contract. Implement it in the owning curated service (`curated/read.py` for archival reads, `curated/official_read.py` for official reads), gateway and typed contracts. Group only within a source/version identity, use stable ordering and bind signed cursors to query, view, grouping and version. Do not approximate identity merging in the browser.
- Bound grouped responses to 20 organisations with at most three displayed matched-name examples each, plus truthful matched-fact counts when available and a version-pinned link/action to inspect further names. Do not scan/fetch the entire archive or return every alias in one response. Verify prefix-query plans on representative data; add only backward-compatible indexes if needed.
- Display one organisation entry per stable source identity, its matched former names and why it matched. Counts explicitly distinguish organisations shown from matching name facts; omit a global total when unavailable.
- Add tests with several aliases crossing page boundaries, identical names on different entities, leading-zero identifiers and the same display name in official/archive sources.
- Use one page controller for the shared search/URL/source selection and independent state for each source's cursor/version/detail requests. Replace conflicting URL mutations in the two existing modules. New links carry `companySource=both|official|archive`; a new ordinary name search uses `both`. Without that parameter, old `official_*` links restore official scope and old archive links restore archive scope. Cancelling or changing the query invalidates both result groups and their exports.

**Readable detail**

- Start with company name, clearly labelled source identity, dated incorporation/name/address observations where available, and a compact historical/coverage warning.
- Use task-oriented tabs: Summary, Names, Officers, SFC records. Show unavailable families as unavailable, not empty facts or current absence. Preserve the distinction between officer appointments and SFC staff relationships within their views.
- Raw namespaces, precision values, all source fields and archive schema are available in details. Never turn an unknown dissolution/end date into Active or an exact date into a current-status claim.
- Hide selection panels until a result is selected or show one short instruction. On selection, show loading and move focus to the detail heading when ready. Restore focus to the chosen result on Back.

**Coverage and downloads**

- Public coverage shows collected date range, incomplete/missing coverage and the consequence for the user's interpretation. Remove queue sizes, staging counts, address ceilings, schedule/recovery receipts from the ordinary paragraph. Keep diagnostics available without changing the raw status API's operational contract.
- Label exports Download these search results / Download these records, with displayed count and source/version. Exports retain attribution, warnings, safe CSV behavior and checksums. A grouped-result export contains the displayed organisation summaries and displayed matching-name evidence with explicit scope/counts; use the separate name-history view for version-pinned fact pages. Do not label a summary export as all matching facts or expand an export into an unbounded archive query. Preserve original-fact exports on the existing fact views.
- Move the full 430 MiB archival download into Advanced downloads, retaining the manifest, notice, typed schema and checksum verification. Do not download it for a browser search.
- Preserve existing `/companies?q=...`, `entity`, `version`, `tab`, `official_*` and cursor URLs through a compatibility parser. New source-group state must not reinterpret an old archive URL as an official identity.

Acceptance: HSBC-style searches show one row per organisation within each source across pages; same-name entities remain distinct; matching evidence remains accessible without unbounded responses; both result groups handle partial failures; older bookmarks work; source/version cannot mix in detail or export; missing records do not imply dissolution; repeated searches and expired cursors have recoverable states.

### UX-04: homepage, navigation and discovery copy

- Keep a short product statement followed by task examples: find neighbourhood licences, inspect property adverts, look up plate history, find company records, browse weather datasets. Use working capabilities already exposed by the service.
- Add clickable example searches beside the main input. Keep Search data primary and Connect AI secondary. Remove duplicated explanations and make the result promise concrete.
- Replace the instructional file/API step with Find data → View an available result → Use its sources or connect your AI. The detailed resource flow remains in the catalogue.
- Derive the capability list from the existing registry so company offerings cannot disappear while present in search. Keep official and independent provider labels. Do not count two source views as two separate companies or inflate government dataset counts.
- Topic shortcuts open labelled curated catalogue results, with useful query aliases and scope. They remain browse entry points unless a guided tool is actually delivered and checked. Do not promote weather as a live guided forecast feature in this repair.
- Keep coverage totals behind a disclosure with definitions. Simplify FAQ answers and link technical detail to Guides.
- Keep the initial analytics choice nonmodal and compact while optional analytics remain off until affirmative consent. Provide equally discoverable Allow and Reject, a way to reopen choices, and no blocked content or focus trap. Retain GPC/DNT behavior and search/query redaction.

Acceptance: all declared existing capability families are discoverable in English and Chinese from home or Find data; every promoted task reaches a real form/result; source limitations remain available before use; initial analytics UI does not cover the search action at 320px width.

### UX-05: existing guided searches

**Properties `/properties`**

- Replace the ten-button cloud with a candidate list showing available building name, estate/address and district. Display only fields actually supplied by the provider; missing context is not invented. State that candidates are limited.
- Default to recent building-matched adverts; explain it as a recency/matching filter, not verified availability. Offer All adverts with older/uncertain matches clearly marked.
- Add All / For sale / To rent to the displayed listings. If the backend only supplies a bounded subset, state that the filter applies to returned adverts; never imply a whole-market inventory or silently hide pagination.
- Show mode, HKD price, saleable area, readable observed date, source and a compact match indicator. Source links and the unit/availability caveat remain accessible at the result. Asking-price changes use a readable before/after list without implying transactions.
- Store selected building ID, listings/history view, quality, sale/rent filter and locale in the URL. Restore them on refresh and Back; retain free-text input in current-tab state. Abort obsolete search/listing requests and map errors to recovery actions.

**Plates `/plates`**

- Use two explicit modes: Auction history and Similar plates. Display only filters that the selected endpoint honours; preserve mode-specific state when switching.
- Explain comparison cohorts in plain language, show sample size/date range and historical-price caveat adjacent to the summary. Write 25th–75th percentile with an explanation, not unexplained P25/P75 alone. No current valuation claim.
- Use a compact result table with responsive row details, consistent UI date formatting and original-source date text in details. Preserve amounts/statuses exactly; missing prices and unsold results are not zero-value sales.
- Preserve plate/mode/filter/page state and use honest result counts. Normalize display spacing without changing the query's identity semantics.

**Neighbourhood `/demo`**

- Keep address search and candidate confirmation. Identify restaurant results as licences near an address; show names and distances first, readable location second, detailed licence text on expansion.
- Show selected address/district and radius together. Put district population in a secondary panel with reference year, units and a visible district-wide scope label. Radius changes must not imply that population was recomputed within the circle.
- Add a short explanation that distances are straight-line. Move WGS84 to details. Retain full source addresses, licence type and source evidence.
- Provide a route to district statistics from the capability entry for users interested in statistics, without pretending the existing address-driven tool is an independent district selector. A new selector is optional follow-up if already supported by the same endpoint.
- Do not require geolocation or new external map requests. A map remains a later enhancement subject to provider, privacy and cost decisions.

Acceptance: property selection survives a copied building link; supported filters are explicit; plate comparisons cannot appear to honour history-only filters; neighbourhood population stays district-wide when radius changes; all three tools handle valid-empty, provider error, stale data and repeated selection without misleading results.

### UX-06: Connect, Guides and API reference

**Connect `/connect`**

- Begin with Which app are you using? Provide clear supported-client choices and an Other app option explaining the requirement for a custom remote MCP connection.
- Retain Codex, Claude Code and Cursor as the initial supported set. Before publishing instructions, verify their current official documentation and actual supported settings on the chosen client version. Do not infer ChatGPT/Claude consumer-app support from CLI support or imply plan/workspace availability that has not been checked.
- For each supported client: prerequisites, exact destination, copyable settings/command, restart/reload step, connection-status check, a test prompt and expected evidence in the answer. Respect `mcp.hk` naming where supported and documented dotless `mcp-hk` where required.
- Explain delayed first connections plainly; disclose a possible two-minute start with the supported timeout setting in advanced help. Classify client configuration, service startup, quota and upstream-source problems separately.
- Use one verified deterministic HTTP request and representative response for non-MCP users. Prefer an existing guided data endpoint for the first success; connect generic resource exploration to the separate API guide.
- A website Copy success is never labelled Connected. Connection verification occurs in the actual client; a website health check is labelled only Service reachable.

**Guides `/guides`**

- Three concise task entries with audience, outcome and prerequisite: Connect an AI assistant; Make your first data request; Understand sources and dates. Add a return path and next action to each article.
- API article `/guides/hong-kong-open-data-api`: one complete catalogue → resource → bounded records walkthrough using real identifiers captured and checked at release. Include exact request bodies, meaningful response fields, source/date interpretation and expected success shape. Fixture examples are labelled with capture date; never pass them off as live responses. Include an actionable path when the source version changes.
- Connection article `/guides/connect-ai-to-hong-kong-data`: explain supported remote MCP behavior and link to the exact client section in Connect. Keep one authoritative set of settings rather than drifting duplicate instructions. Add symptom-based troubleshooting and a success example.
- Freshness article `/guides/data-sources-and-freshness`: annotate one real response showing catalogue sync, source check and observation/reference dates. Add one copyable citation and a status-to-action table. Keep archival dates, licence/availability limits and asking-price meanings distinct.

**API reference `/docs`**

- Retain the bundled Swagger reference and licence/notice files. Add the shared header, a concise first-request introduction and links to the complete walkthrough and limits.
- Group OpenAPI operations by actual capabilities: Discovery, Resource records, Addresses/restaurants/districts, Companies, Properties, Plates and Service status. Put operational endpoints last.
- Improve operation summaries and request examples without changing existing operation IDs, methods or paths. Keep OpenAPI machine consumption and existing MCP contracts intact.
- Keep the documentation reference in English if that is its established contract; provide bilingual navigation/introduction and an explicit language note. Do not manufacture translated source field identifiers.

Acceptance: a clean supported-client setup reaches tools and a cited read-only response; the HTTP and generic-resource tutorials each reach meaningful rows without unresolved placeholders; an alternate source and explanatory limitation cover provider/version failures rather than replacing the successful worked example. Unsupported clients receive truthful guidance; Swagger remains usable with its CSP and bundled assets. If an advertised client cannot be exercised in the available environment, retain accurate documented instructions but mark that client verification pending rather than claiming a passed end-to-end setup.

### UX-07: Data status, About and legal pages

**Data status `/sources`**

- Start with a compact list of existing capabilities, access outcome and last-check/reference time. Offer Open search tool, Preview dataset or Original source as appropriate.
- Separate readiness, source-check recency and observation freshness. Do not use one green badge for all three. Use meaningful source names instead of translation keys.
- Transport reports last tested route/stop and test time. Use Check arrivals on the existing guided resource with required parameters; never imply continuous network monitoring, trigger blanket checks on page load or call an expired test an operator outage.
- Keep large inventory totals, check denominators, format failures and operational receipts in expandable coverage/diagnostics with their existing definitions. No invented overall uptime percentage.

**About `/about`**

- Lead with who can use it and existing tasks. Explain the independent project, maintainer identity as already publicly established, upstream attribution and software/data licence distinction.
- Offer a simple Report a data problem link with an optional source ID and plain description. Never automatically include a person's query or returned records. Keep public GitHub issues for software/source reports.
- Use only an existing verified private contact channel if one exists. Otherwise explain how to request a private route without posting personal information; do not invent an email address or make contact-channel setup a release dependency.

**Terms `/terms` and Privacy `/privacy`**

- Add in-page contents, readable measure and a short non-authoritative summary linked to full sections. Preserve the existing substantive terms; revised legal rights or retention policy are outside this copy/structure repair.
- Terms: make source reuse obligations, service limitations, current machine-readable rate limits and contact route easy to find. Keep numeric statements synchronized with the actual limits policy at release.
- Privacy: summarize what requests go to which providers, necessary measurement, optional analytics, retention and user controls in a compact table that accurately reflects the existing policy. Keep the exact detail below it.
- Put an Analytics choices button beside its explanation. Link to account management only if a working supported account entry path is verified; otherwise describe the existing behavior accurately without inventing a sign-in flow.
- Keep full provider policy links and meaningful dates. A summary never silently supersedes the complete text. Do not change contractual effective dates solely for navigation or typography changes; follow existing policy if substance changes during implementation.

Acceptance: no internal source keys or success/date contradictions; status requests stay bounded; About identifies independence and source rights; Terms/Privacy links and anchors work; analytics withdrawal and consent behavior remain correct; no new unverified contact/account path appears.

## 4. Bilingual design and accessibility contract

- Body/input text: target 16px; supporting evidence and labels at least 14px; compact technical code at least 13px with zoom support. Essential caveats cannot depend on 10–11px copy. Use existing font families and wordmark; avoid a typography rebrand.
- Restrict long prose to roughly 65–75 characters per line. Distinguish titles, actions, results and evidence with spacing/weight. Do not wrap every field in a card or add decorative metric blocks.
- English and Hong Kong Traditional Chinese ship together for all authored headings, help, statuses, errors and actions. Raw provider descriptions, names and identifiers may retain their original language, labelled as source text where needed. No translation keys or template placeholders appear to users.
- Simplify public Chinese: 搜尋公司資料, 官方資料, 歷史資料 and 資料日期 where accurate. Keep detailed temporal/identity explanations available; do not replace precise archival semantics with misleading current-status wording.
- Use semantic headings, associated labels, valid links for navigation and correct tab/radio/pressed semantics for controls. Do not add a missing-label fix based only on the static detector: the reviewed neighbourhood input had an accessible name in the browser; verify rendered semantics first.
- Target WCAG 2.2 AA behavior: normal-text contrast at least 4.5:1, visible keyboard focus, no keyboard traps, no information conveyed by colour alone and 44px target design where feasible. Do not claim certification from automated checks.
- At 320, 390, 768 and 1280px, task inputs and primary actions remain usable. At 200% zoom and equivalent 400% reflow, the page has no horizontal overflow except clearly labelled table/code regions. Those regions remain keyboard accessible.
- Loading, counts and recoverable errors use restrained live announcements. Deliberate selection moves focus to detail; background refresh never steals focus. Respect reduced motion and OS colour preference. Blocked storage/clipboard and disabled JavaScript have useful fallbacks for public navigation and settings copying.

## 5. Technical change map

Paths are relative to the implementation checkout, and must be reconfirmed after updating to current main.

| Surface | Likely files | Main verification |
|---|---|---|
| Shared shell, homepage, tools, Connect and status | `web/index.html`, `web/app.js`, `web/style.css`, `web/i18n.js`, `web/translations.js`, `web/analytics.js` | Landing, analytics, locale and browser-journey checks. |
| Find data | `web/coverage.html`, `web/coverage.js`, `web/coverage.css`, `connected.py`, `discovery.py` | Catalogue UI, discovery and resource contracts. |
| Bounded preview | `resources.py`, `resource_api.py`, `resource_fields.py`, `resource_formats.py`, `resource_stream.py`, `contracts.py` as needed | Meaningful-row/projection/byte-cap/version tests; HTTP/MCP parity. |
| Company grouping and UI | `web/companies.html`, `web/companies.js`, `web/company-updates.js`, `web/companies.css`, `web/company-fields.js`, `web/company-export.js`, `companies.py`, `company_api.py`, `contracts.py`, `curated/read.py`, `curated/official_read.py`, `curated/backend.py` | Source identity, aliases across pages, partial failures, version pinning, bounded queries and export evidence. |
| Properties | `web/properties.html`, `web/properties.js` and current SeeHouse contract | URL, race, filter-scope, empty/error and provider tests. |
| Articles/legal/reference | `web/article.html`, `web/discovery.json`, `web/legal.html`, `web/legal.js`, `web/api-docs.html`, `web/api-docs.js`, `api.py`, `docs/connect.md`, `docs/discovery-ux.md` | Generated page content, canonical/locale links, OpenAPI and CSP checks. |
| Worker serving and release | `deploy/cloudflare/` asset/routing/config owners identified from current main | Existing Worker types/check/tests, cache adoption and production runbook. |
| Curated company service release | `deploy/curated/`, `docs/curated-read-model.md`, curated backend and PostgreSQL contract tests | Existing service adoption, grouped-search feature compatibility, query-plan and migration/rollback checks. No new host or paid service. |

`web/` above means `src/mcp_open_data_hk/web/`. Reuse the existing Node UI tests and Python tests. Add a small rendered-browser regression suite for behaviors the current DOM stubs cannot establish; do not substitute markup-string assertions for working Back, focus or async behavior. Do not edit vendored Swagger bundles.

## 6. Acceptance and test matrix

| ID | Scenario | Required observable outcome |
|---|---|---|
| A01 | New visitor uses home examples | Finds the chosen capability without API/file-format knowledge; result/action is visible and accurately described. |
| A02 | Search within each scope | Scope remains selected; zero results offers an explicit broader search; Back and language switch retain scope. |
| A03 | Dataset/resource pagination | Forward/back/refresh preserve query, page and selection; changed filters reset invalid pages. |
| A04 | Weather entry and oversized resource | Promoted weather path returns meaningful rows; oversized original has a safe preview or working alternative; cap remains enforced; no retry loop or raw error-only state. |
| A05 | Public holidays and ambiguous nested JSON | Calendar events render as records; ambiguous arrays require selection; units and source dates are preserved. |
| A06 | Company aliases, duplicates and same names | Unique organisation results per source/version across pages; no BRN/Webb inference; further alias evidence remains accessible; bounded responses. |
| A07 | One company source fails | Other group remains usable, failed scope is explicit, no false no-company conclusion. |
| A08 | Company cursor/version change and exports | Restart path is clear; source/version pinned; exported record/fact count and checksums match the advertised scope. |
| A09 | Property building URL and filters | Shared building opens correct selection/view/quality; refresh and Back work; sale/rent filtering scope is honest. |
| A10 | Plate mode switch | Only honoured filters appear; comparison sample/period/method are clear; missing/unsold values remain distinct. |
| A11 | Neighbourhood radius change | Restaurant list updates; population remains explicitly district-wide with reference year; no stale response overwrites selection. |
| A12 | Supported MCP client setup | Real tool discovery and a source-linked read in each claimed supported client; Copy and HTTP health are not counted as client success. |
| A13 | HTTP tutorial | Copyable requests reach the stated data with expected shape; no unresolved DATASET_ID/RESOURCE_ID or secrets. |
| A14 | Status and dates | Missing timestamps cannot produce successful-check assertions; historical and stale source data remain accurately labelled. |
| A15 | Keyboard, screen reader, mobile and zoom | Entire primary flow usable; correct focus/announcements; no hidden primary action or whole-page overflow. |
| A16 | Locale and provider language | EN/zh-Hant authored copy complete; locale persists; original source text is distinguishable; dates/identifiers are not corrupted. |
| A17 | Analytics and private input | No optional analytics before consent; reject/withdraw/GPC/DNT work; search/coordinates/arguments absent from analytics and document titles. |
| A18 | Rate limit, blocked source and valid empty | Retry-After honoured; failed data stays distinct from empty; last successful data is clearly identified and never attributed to a new failed query. |
| A19 | Public links and machine interfaces | All 16 reviewed routes, old deep links, canonical/hreflang, OpenAPI, MCP and agent discovery continue to work. |
| A20 | Cold start and deployment adoption | Cold first request yields truthful progress and success or actionable timeout; actual controller/container/asset version and recovery checks meet the runbook. |
| A21 | Page performance and request fan-out | Compare baseline/final transfer sizes, initial requests and three warm-load samples; explain any material increase; ordinary search does not start background provider crawls; company search dispatches at most one bounded request per requested source. |

Use deterministic fixtures for failure/race/version/large-payload cases and a bounded live browser/HTTP/MCP sample for provider-backed outcomes. Avoid repeatedly probing the same upstream source. No production writes are needed for UX journey tests.

Run the repository's required `bash scripts/check.sh all` against the final code state, including Python formatting/lint/tests and Worker generated types/typecheck/tests. Required CI includes Python 3.10, 3.11 and 3.12. For grouped search, also run the curated PostgreSQL integration contracts and bounded-query checks; a local SQLite fixture alone cannot establish the production PostgreSQL query behavior. Install/preserve the required pre-push hook before an eventual push. Browser checks and user-visible receipts supplement these gates.

Internal walkthrough target: an unfamiliar evaluator can complete an existing guided search and identify its source/date in two minutes, excluding a disclosed cold start; initial AI setup has a complete five-minute walkthrough target excluding external account installation. Record attempts, assistance and failure reasons. These are proposed usability targets, not existing user-research results or substitutes for functional acceptance.

## 7. Release sequence and evidence

1. Establish the current-main/live baseline and run targeted reproductions. Keep a small evidence bundle for known defects and the intended fixes.
2. Release candidate 1: UX-01 and UX-02, correcting broken search/preview behavior while retaining old routes/contracts.
3. Release candidate 2: UX-03 and UX-04, completing company discovery and the coherent navigation/home entry points.
4. Release candidate 3: UX-05 through UX-07, completing existing tools, onboarding, guides/status and supporting pages.
5. Complete UX-08 and all relevant acceptance scenarios for each candidate before its release. Reuse valid unaffected results; rerun checks when code, dependencies, deployed source versions or environment change. A partially delivered package list is reported as partial UX completion.

For each eventual release, follow current `docs/production.md` and repository instructions: pause only the documented resource cron before Worker/DO changes, respect propagation and leases, keep it paused through adoption, restore all five configured schedules, verify actual backend readiness and perform the required isolated restore of a fresh accepted backup. Never clear a lease because a response was interrupted. Static assets or a release header do not prove container adoption.

Freeze evidence to exact commit, Worker version, container/backend version and asset content hashes. Capture desktop/mobile EN/zh screenshots, exercised URLs, request outcomes, source timestamps and known unavailable scopes. Any provider outage remains explicit; do not call a synthetic fixture a production success. Clear only owned caches as documented; do not wipe accepted data to force the UI to update.

Keep each candidate additive or reversibly compatible. Retain old URL parsing and default HTTP/MCP response contracts. Roll back the exact application/assets candidate using the runbook; a frontend rollback must not require restoring or deleting the data database. Any new grouped-search storage/index work needs a backward-compatible migration and its own rollback plan before release.

For candidate 2, deploy and qualify the optional grouped-query support in the existing curated company service before enabling the gateway/UI that requires it. Verify its advertised contract/version through the gateway; prevent a mixed deployment from silently falling back to duplicate fact rows. Run compatibility tests against old callers and new grouping requests. Keep any additive indexes usable by the previous backend so an application rollback remains possible. Follow the curated service's own deployment/recovery instructions as well as the Cloudflare runbook.

The separate security-remediation release restrictions and any current release blockers must be rechecked at implementation/release time. This UX plan does not declare the old blocker current, resolve it or authorize bypassing it.

## 8. Completion definition

All 16 reviewed pages have their specified changes; every P1/P2 item has an acceptance result or an explicitly accepted residual limitation; old contracts/deep links are compatible; authored EN/zh-Hant copy is complete; required code/CI and rendered-browser checks pass; the released candidate is observed through real public journeys; schedules/readiness/recovery requirements are evidenced.

Keep statuses separate: planned → implemented → locally verified → CI verified → deployed → observed. Planning completion here does not imply implementation, client qualification, release or validated independent-user usability.

## 9. Plan review

Review record: `ux-completion-review-2026-10-25.md` in this directory. The final plan incorporates corrections for identity safety, grouping/pagination, preview budgets, URL privacy, current-client evidence, reversible delivery and rollout proof. See the review for resolved findings and remaining implementation checks.
