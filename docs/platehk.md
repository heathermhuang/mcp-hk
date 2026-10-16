# Plate.hk: the first external data pack

Plate.hk is an independent Hong Kong data provider. Its public index compiles
Transport Department vehicle-registration-mark auction publications and official
workbook exports. The mcp.hk code is open source; this does not relicense any data.
Keep [Plate.hk attribution and guidance](https://plate.hk/about.html) and each
record's original source link. Official published results prevail.

## Connect and query

Existing `https://mcp.hk/mcp` connections gain these tools after reconnecting:

```json
{"tool":"hk_plate_search","arguments":{"q":"AA88"}}
{"tool":"hk_plate_search","arguments":{"q":"88","mode":"contains","dataset":"pvrm","pageSize":5}}
{"tool":"hk_plate_comparables","arguments":{"q":"AH168","pageSize":5}}
{"tool":"hk_plate_datasets","arguments":{}}
{"tool":"hk_data_packs","arguments":{}}
```

HTTP calls use the same services and response envelopes:

```sh
curl 'https://mcp.hk/api/v1/plates/search?q=AA88&mode=exact&pageSize=5'
curl 'https://mcp.hk/api/v1/plates/comparables?q=AH168&pageSize=5'
curl 'https://mcp.hk/api/v1/plates/datasets'
curl 'https://mcp.hk/api/v1/packs'
```

Try the bilingual [browser demo](https://mcp.hk/plates). No model or provider API
key is required. Data comes from Plate.hk's public API, not fixtures or model calls.

## Search contract

`q` is required (1–16 characters). `dataset` is `all` (default), `pvrm`,
`tvrm_physical`, `tvrm_eauction`, or `tvrm_legacy`. `mode` defaults to `exact`;
`contains` and `exact_prefix` support broader discovery. Exact search avoids
silently treating AA8888 as an AA88 match. Plate.hk performs query normalization,
including full-width forms, and rejects invalid marks.

`sort` is `date_desc` (default), `amount_desc`, `amount_asc`, or
`plate_asc`. `page` is 1–100; `pageSize` is 1–50 (default 20, comparisons 8).
Provider query-window limits still apply. Each response includes `data.items`,
`page`, `pageSize`, `total` and `nextPage` for search. Reuse all filters for the
next page. These are live provider pages, **not snapshot-pinned generations**;
source updates between pages can move records. No complete-set summary is computed
from a single page.

Comparisons use Plate.hk's published structural method. Preserve `method`, `cohort`,
`sampleSize`, date range and `statistics` (P25/median/P75, HKD). A comparison cohort
can exist without an exact historical sale. Null statistics must remain null; the
adapter rejects non-null statistics for samples smaller than five. Some structural
example responses do not publish a complete sample count and have no next page.
Search dataset/mode filters do not apply to the comparison cohort.

## Record and provenance semantics

- Preserve `single_line`, `double_line`, `dataset_key`, `auction_key`, dates and
  labels, `date_precision`, `year_range`, `amount_hkd`, status and linked sources.
  Records retain the provider's snake_case auction fields inside `data.items`.
- `pdf_url` can point to a PDF or legacy workbook. Relative provider workbook links
  become absolute Plate.hk URLs. `detailUrl` links back to Plate.hk.
- An E-Auction issue date is the opening date, not every mark's sale/payment date.
  A legacy date can be a shard key; use its year-range label, not an invented day.
  `@` special-fee allocations are not competitive sales; `U/S` is not a zero price.
  General search coverage may omit unsold marks and some dispositions.
- Historical auction amounts and comparisons are not current valuations, asking
  prices, ownership, availability or official legal classifications.
- Dataset `generatedAt` is Plate.hk's index publication date; a response's
  `retrievedAt`/`lastCheckedAt` records mcp.hk's successful API read, not the auction
  date or a claim that the underlying observations are from today.
- `all` already includes component collections; do not sum its record count with
  those components. Coverage is the provider's published index, not a completeness
  claim about all Hong Kong auctions.

The source ID is `platehk`, with `providerType: independent` and `accessMode:
live_api`. `/api/v1/packs` discovers this alongside government packs;
`/api/v1/datasets` remains government catalogue discovery. Status reports record
successful reads and errors without making Plate.hk a government-readiness gate.

## Failure and resource limits

Only three fixed public paths on `https://plate.hk` are called. No arbitrary source
URL, private marketplace data, seller contacts, payments or OCR is exposed. Only
allowlisted auction fields pass through, even if upstream adds unrelated fields.
HTTP reads are timed, bounded to 8 MB, and refuse redirects. Existing public request
budgets apply. Plate.hk adds a persisted 5,000 uncached-read daily budget, three
concurrent reads and a five-minute, 200-response cache using the backed-up store.

Errors remain errors: `INVALID_QUERY` (400), `PLATEHK_RATE_LIMITED` (429),
`UPSTREAM_TIMEOUT` (504), `UPSTREAM_UNAVAILABLE` (503), and `SOURCE_SCHEMA_CHANGED`
(503). Failed/malformed responses are never cached as successful empty pages.
Plate.hk owns source refreshes; mcp.hk does not launch a duplicate auction crawler.
