# SeeHouse / 睇樓 property data

SeeHouse is an independent Hong Kong property app and data pipeline built by our
team. mcp.hk reads its existing public API on `https://see.house`; the pipeline
continues to own ingestion, matching, moderation and refreshes. No duplicate
crawler, database mirror, write access or model call is added.

Reconnect an existing `https://mcp.hk/mcp` client to discover:

```json
{"tool":"hk_property_search","arguments":{"q":"太古城","limit":5,"lang":"zh-Hant"}}
{"tool":"hk_property_building","arguments":{"buildingId":"<id returned by search>"}}
{"tool":"hk_property_price_history","arguments":{"buildingId":"<id returned by search>"}}
{"tool":"hk_property_coverage","arguments":{}}
```

Use the same services over HTTP:

```sh
curl 'https://mcp.hk/api/v1/properties/search?q=Taikoo%20Shing&limit=5'
curl 'https://mcp.hk/api/v1/properties/building?buildingId=hk-csdi-95d9ff45d90eb3f5'
curl 'https://mcp.hk/api/v1/properties/price-history?buildingId=hk-csdi-95d9ff45d90eb3f5'
curl 'https://mcp.hk/api/v1/properties/coverage'
```

The bilingual [building and listing search](https://mcp.hk/properties) uses these
HTTP routes. `/api/v1/packs`, `hk_data_packs`, and unified catalogue search discover
`mcp:seehouse` with its tools, HTTP access, independent-provider label and attribution.
Government inventory and validation denominators remain separate.

`q` is required, trimmed, 1–200 characters; `limit` is 1–20 (default 10). Search
accepts a building, estate or address. Select a returned building ID before reading
its listings or price changes. IDs are bounded to 160 ASCII letters, digits, `_`,
`-`, and `:`. `lang` is `en` (default) or `zh-Hant`, translated to SeeHouse's
`en-HK` / `zh-HK` locale. Search and building queries reject unknown fields.

## Meaning and limits

- Search returns ranked, limited candidates. SeeHouse supplies no exact search
  total or pagination cursor. `meta.total` and `meta.truncated` are null; neither
  means a complete inventory was returned.
- Building listings retain source IDs and original URLs, buy/rent mode, asking
  price in HKD, area in square feet, observation dates, freshness, match confidence,
  status and dedupe context. Upstream caps the display at 50 listing cards from
  up to 200 rows; building statistics may describe more records than the returned
  cards. These are advertisements, not verified availability or unique homes.
- Price history is observed **asking-price changes**, not Land Registry
  transactions, achieved rents or valuations. Preserve `observedAt`, old/new HKD
  values, mode and caveats. The source returns at most 200 events; `eventCount`
  counts returned events, not all historical changes. No completeness claim or
  snapshot-pinned pagination is made.
- `retrievedAt` and `lastCheckedAt` mean mcp.hk successfully read the API.
  `freshness.observedAt`, `lastSeenAt`, source status and coverage `generatedAt`
  retain the pipeline's dates. Today's API read does not make an old listing fresh.
- An indexed building may have no active listings. Unit matching is not guaranteed.
  Coverage separates indexed buildings, source-backed buildings, matched/unmatched
  advertisements and fresh/aging/stale listings; it does not establish full market
  coverage. District rows and totals retain the provider's definitions.
- Original listing providers retain their rights. Keep SeeHouse and record-level
  source attribution; the repository's MIT license does not relicense the data.

## Operations and failures

Only four fixed read-only endpoint patterns are called; building IDs cannot change
the origin or inject path/query components. Nested field allowlists omit contacts,
raw captures, operations and analytics. Known demo/fixture fallbacks and malformed
schemas fail closed. Redirects are refused. The shared HTTP client enforces a
five-second timeout and 8 MB response bound.

Successful reads use the backed-up SQLite store: five-minute cache, 200 responses,
5,000 uncached reads per UTC day, three concurrent reads. Expired-cache errors stay
errors; old records are not returned as a successful fresh query. SeeHouse source
status is optional for government-pack readiness.

`INVALID_QUERY` is 400, `NOT_FOUND` 404, `SEEHOUSE_RATE_LIMITED` 429,
`UPSTREAM_TIMEOUT` 504; source/schema/budget failures are 503. Failures are never
cached as successful empty results. A valid empty result remains a successful
empty result and does not prove that no relevant properties exist.
