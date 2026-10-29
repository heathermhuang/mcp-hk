# Discovery and preview UX

## What failed

The original catalogue only searched harvested DATA.GOV.HK/CSDI rows. Connected
query services lived in a separate pack registry, so a working Plate.hk integration
returned zero catalogue results for both `plate.hk` and `車牌`. This was an
information-architecture defect, not provider downtime. Two independent read-only
assessments reproduced it in separate browser tabs.

The broader review also reproduced a broken neighbourhood form (a shared CSS
selector bound the plate layout DIV instead of the address FORM), old previews
remaining under new searches, source settings leaking between resources, URLs
that failed to preserve selection, and a holiday preview showing a calendar
wrapper instead of event rows. Baseline expert assessment: 20/40 across Nielsen's
ten heuristics; five cognitive-load checklist failures. This is a design judgment,
not an accessibility certification. The optional Impeccable detector was not
cached locally; a bounded deterministic markup/source audit was used instead.

## Product model

One discovery path covers both connected services and source datasets:

1. **Find data** by name, provider, domain or English/Chinese keywords.
2. **Ready-to-use queries** open a guided task directly, including Plate.hk.
3. **Source catalogues** expose original files/APIs with preview/check status.
4. Select a source and preview its records. Required route/stop inputs are shown
   directly; JSON filters and developer examples remain secondary.

`connected.py` derives first-class discovery entries from the existing pack
registry. IDs use the `mcp:` namespace. Entries carry provider type, bilingual
description, aliases, direct user action and actual HTTP/MCP access methods.
`hk_catalogue_search` and `/api/v1/catalogue/datasets` share the same search.
`hk_dataset_resources` returns direct access instructions for connected entries,
not invented government resource IDs. Connected views may overlap native source
datasets and do **not** inflate harvested-government coverage denominators.

Homepage search, catalogue search and provider query pages now lead into the same
journey. Query pages belong under Browse data in navigation; Plate.hk is a
first-class independent source, not a hidden demo or government dataset.

## State, accessibility and previews

- New searches/datasets invalidate all downstream selections, results and pending
  query generations. New resources reset incompatible source parameters, fields,
  record paths and workbook/layer selectors.
- URLs preserve search, access mode, dataset, source and source-list page/format.
  Browser back and refresh restore that selection. Query input/results are not
  silently replayed or stored in URLs; fresh data requires a new query.
- Inactive stages stay hidden. Selected controls expose their state. Loading/count
  updates are announced, stage focus follows deliberate selection, skip links are
  available, and scrolling respects reduced motion.
- Search prioritizes title/provider matches over incidental description matches.
  Source resources prioritize previously readable/selection-ready structured
  formats. Descriptions and capability summaries appear before a source click.
- The canonical single-calendar iCalendar JSON shape previews its actual `vevent`
  rows. Calendar-level metadata and original date/value fields remain in the full
  response. The browser shows holiday name/date columns and formats only explicit
  iCalendar `DATE` values. An explicit `vcalendar` path still returns the wrapper.
  Other nested arrays use an explicit record-list choice, not arbitrary flattening.
- A reader-policy cache-key revision prevents serving old calendar-wrapper
  previews after the parser change. It is not evidence of a new provider update.

## Next dataset families

Prioritization is based on recurring user jobs and source feasibility, not proven
customer demand or unique-visitor figures. Many sources are already discoverable
or generically readable: the next milestone is a complete guided experience,
with cadence-aware semantics, rather than another catalogue count.

| Priority | Family / user job | Current evidence | Required before promoting it |
|---|---|---|---|
| 1 | HKO weather, forecasts and warnings: plan an outing or journey | Official current-weather API returned 200 with `updateTime=2026-10-17T22:02:00+08:00`; warning-summary API returned 200 with an empty object. CSDI weather resources are inventoried, including a previously checked 18-row rainfall resource. | Guided area/date views; source-issued timestamps and cadence-specific expiry; distinguish a valid no-warning response from provider failure; preserve warning issue/expiry and original advice. |
| 2 | AQHI station observations and forecasts: inspect local air conditions | Live MCP read of resource `f097d0d90fd98c9846f9109ec0ce6905` returned 18 stations; sample publication `2026-10-17T21:30:00`. | Replace the current generic 86,400-second file cache for this source with an hourly publication-aware policy. Preserve missing/maintenance values and provider risk labels; give station/district selectors and original attribution. Do not call the generic preview live. |
| 3 | School locations and types: extend address/neighbourhood discovery | EDB publishes monthly location/type data; inventoried JSON resource `41e8f7209e7d3db5cfdcc86ee36592e4` has a prior validated count of 3,496 records. | Bilingual school/type and district search, coordinate validation and original-school links. Treat this as a location directory, not an admissions, school-quality or catchment guarantee. |

Primary references: [HKO API specification](https://www.hko.gov.hk/en/weatherAPI/doc/files/HKO_Open_Data_API_Documentation.pdf),
[AQHI dataset](https://data.gov.hk/en-data/dataset/hk-dpo-datagovhk2-city-dashboard-aqhi),
[EDB school locations](https://data.gov.hk/en-data/dataset/hk-edb-schinfo-school-location-and-information).

## Onboarding definition of done

A new connected pack is incomplete until it has a discoverable provider/topic
entry, English and Traditional Chinese aliases, a useful default or guided form,
coverage and time semantics, preserved source terms/provenance, correct empty and
failure states, real HTTP/MCP query proof, and desktop/mobile browse-to-result
verification. The registry regression checks that every declared pack is included
in connected discovery. No provider-specific tool may be the only route to find it.

## UX completion release (25 October 2026)

The primary navigation is Find data, Connect AI, Guides and Data status. Anonymous
read-only access and existing routes remain supported. Dataset detail retains list
context; scope and offsets survive deliberate navigation. Preview restores only a
selection, never arbitrary source arguments or record POSTs. One deliberate preview
makes at most one schema and one record request, projects scalar source fields and
keeps the 512,000-byte item cap. Geometry is omitted explicitly, not truncated.

Company name entry dispatches one bounded grouped request to each selected source.
Official observations and Webb archival organisations remain separate identities.
Old archive and official URL forms are parsed explicitly. Property URLs contain
public building IDs, view and filters; typed addresses remain current-tab state.

`deploy/cloudflare/ux-browser.mjs` exercises actual browser history, focus, request
fan-out, source failure, shareable selection, mobile reflow and both authored locales.
The fixtures prove deterministic UI contracts, not live provider availability.

## Directory homepage (29 October 2026)

The homepage keeps broad topic discovery ahead of catalogue results, with the
existing Find data / Connect AI / Guides / Data status navigation. Topic links
search both connected queries and source datasets. They are navigation aids, not
claims of complete subject coverage. Company/archive views continue through the
same company explorer; source identities, dates and qualification gates remain
separate.

The homepage requests `order=title` from `/api/v1/catalogue/datasets`. HTTP and
`hk_catalogue_search` accept the optional `order` (`relevance` or `title`) and
`provider` (`all`, `government`, `independent`,
`independent_or_public_corporation`, `unclassified`) arguments. The default search
contract remains unchanged. Title order uses the original English title with
ASCII case folded, then the original ID as a stable tie-breaker, for every
provider. Provider filters run before counts and pagination; public-corporation
and unresolved classifications are retained without relabelling.

Expandable results use the shared `datasets.json` family copy for connected
scope, dates and download limits. Native catalogue entries keep the provider's
text, metadata modification date, reference period and terms where supplied,
with links to resource inspection. Source catalogue access is not a record-read
claim. Plate.hk and SeeHouse share an operator with mcp.hk; the homepage discloses
that relationship and applies the same title ordering to every provider.

Search, access, provider and page state survive refresh, history and language
switching. Starting another request clears previous rows, cancels the earlier
request and ignores obsolete responses. A catalogue failure shows a retry action
and the server-rendered family scope index. Without JavaScript, search submits
to the existing coverage explorer and the subject/family links remain available.

`deploy/cloudflare/home-browser.mjs` verifies both languages at 320, 390, 768 and
1280 pixels. Its deterministic fixtures establish UI behavior, not source
qualification. The Python catalogue tests establish ordering, filtering and
pagination against the real service. Release evidence lives in
[the Directory verification receipt](verification/directory-home-20261029/README.md).
