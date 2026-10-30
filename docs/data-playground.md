# Data playground

`/playground` is the public **Explore data** workspace in English and Traditional
Chinese. The directory homepage remains a directory; `/coverage` and specialist
URLs remain available. No account, model call or external map service is required.

Choose a subject or search the reconciled catalogue. Source files show their
language, format, validation state and original link. Only a complete, single,
readable resource choice can open automatically; otherwise choose deliberately.
Returned workbook sheets, map layers, record paths and required source parameters
are real source choices. Restricted and unsupported resources remain explanations;
PDF text remains explicitly unverified extraction.

## Explore and capture

- Edit filters and columns, then **Apply**. Typing performs no record request.
  The displayed table, chart, code and download belong to the applied query.
  Paging also uses that query while a new draft is being edited.
- Generic filters are at most ten conjunctive exact equalities. Choose the scalar
  kind explicitly. Text `00005`, integer `1`, float `1.0`, boolean `true`, empty
  text and null differ. Missing is not null. See [resource contract](resources.md).
- Inspect a row for exact source values and identifiers. Company histories retain
  source date precision. Original responses and developer examples are secondary.
- Charts represent the loaded page, one record per bar, with explicit measure and
  unit mapping. Duplicate labels are not aggregated. Unsafe or unrepresentable
  measures remain in the table. The native table is the accessible alternative.
- Address and premises locations use the existing WGS84 coordinate contract on a
  tile-free coordinate view. No CRS inference is applied to generic spatial data.
- **Copy query link** puts bounded, validated intent in the fragment, up to 8 KiB.
  It includes query inputs, not records, credentials, cursors or local version
  vectors. Racing shares the stable meeting identity, resolving accepted versions
  afresh. Results can change. Clipboard refusal has a selectable-link fallback.
- **Download this page** creates a bounded evidence ZIP only when the source policy
  is established. It contains exact server-parsed JSON, spreadsheet-safe CSV,
  schema/scalar cells, applied query, provenance, notices and SHA-256 manifest.
  No additional pages are fetched. Available records from a partial source feed can be captured with the named unavailable sources in the manifest. Large/precise numbers and negative zero are
  forced to spreadsheet text where necessary; JSON retains source numeric kinds.
  Source reader precision cannot be recovered after it was already lost upstream.

Generic evidence downloads currently require an attributed government DATA.GOV.HK
resource using its exact standard terms URL. A link to arbitrary terms does not
establish export permission. Company and disclosure exports retain their existing
source-specific view/notice validation. Other read capabilities can correctly show
an unavailable download. Racing uses its separately gated, pinned source packages,
labelled as a selected race or profile and selected history page.

## Family integration

Integration describes the interface, not current provider availability or complete
source coverage. No rights, activation, collection, publication or quota gate is
changed by this workspace.

| Family | Integrated mode | Limits retained |
|---|---|---|
| catalogue | Resource choice, typed table, column projection, document state | Inventory discovery is not successful record access |
| transport | Same resource mode with returned route/stop parameters and reference discovery | Explicit refresh; TTL removes expired arrivals from active results/export |
| addresses | Candidate search and exact address lookup; coordinate view | A similar name is not an identity match |
| restaurants | District/licence filters, licence records, coordinate view, cursor pages | Accepted licences do not prove current trading |
| population | District/year selection, published statistic and mapped chart | District-wide units/period; never radius population |
| company_registry | Independently versioned official/archive search and entity history | Dated partial observations; no inferred current status |
| enigma | Same entity workspace with archive selected | Exact Webb identifiers and date precision |
| hkex_daily | Accepted summary records and details | Retained summaries, source holds and unknown filing dates |
| webb_sdi | Issuer resolution, disclosures and amendments | Reused stock codes never join issuers; source numeric precision |
| sfc_archive | Archive licence/entity search plus independently gated official mode | REST and browser activation required for official reads |
| racing | Meeting/race/participant and dated profile/history modes | Accepted-version pins, family gaps; separate profile browser/export gates |
| platehk | Auction search and structural comparables | Cohort method, live-page consistency, historical amounts |
| seehouse | Exact building choice, qualified listings and price history | Listing quality/source coverage; no transaction or valuation inference |

## Resource use and failure behavior

The idle workspace requests its static family directory only. It does not request
all-family statuses. An explicit readable resource opens with schema plus one page
query. Required choices stop before the query. There is no keystroke scan, distinct
value scan, background arrival polling, all-pages export or automatic provider retry.

The browser retains at most the current and two recent pages. Abort/generation
checks prevent obsolete query, detail or export completions from changing a newer
selection. Failed reads can retain the labelled previous result. Version drift asks
for a restart; independent source failures retain the available sources and unknown
combined total. Retry reads only failed feed sources. Busy responses respect their
Retry-After countdown. Analytics retain existing consent and pathname-only behavior.

The resource service admits two read/scan jobs without a waiting queue and checks a
five-second cooperative scan deadline. Cancellation retains admission and the file
reader until the actual worker completes. Unfiltered pages use the accepted exact
row count and read only through the requested page; filtered totals still require a
scan. The opt-in exact sidecar is included in the 1,536,000-byte whole-response cap;
the existing 512,000-byte item cap and 16 MiB export payload cap remain in place.

## Qualification

See [local candidate evidence](verification/playground-20261029/README.md) for tests,
fixtures, measurements and explicit unverified boundaries. The preserved planning
snapshot is [data-playground plan](plans/data-playground.md). Release operations
follow [production](production.md); no release follows merely from passing local QA.

## Visible quality and source updates

The selected family's public status is shown beside its query controls; the idle
workspace does not fetch every family's status. Status failure leaves freshness
unknown and does not block record queries. Company counts distinguish published
addresses from successful but possibly unpublished queue checks and show the
capacity limit of a complete address cycle. HKEX source holds, incomplete racing
seasons and property observation freshness remain visible. The integrated company,
SFC and HKEX pages show the same summary outside their source disclosures.

Directory and playground search results retain catalogue origin, making equal
DATA.GOV.HK/CSDI titles distinguishable without merging their identities or changing
neutral ordering. The current-weather entries offer explicit station-temperature
and humidity shortcuts to the native HKO JSON in the selected language. A shortcut
selects an exact resource and returned record path; it uses normal schema/query
checks, source failure handling and the shared evidence export rules.

Result dates never substitute retrieval time for observation time. Dataset first
publication is labelled separately in source details, and generic source quality
remains explicitly unverified beyond the checks actually reported. No source
activation, collector quota, cron cadence or upstream access hold is changed.
