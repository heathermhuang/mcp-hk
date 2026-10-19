# mcp.hk — Hong Kong. One connection.

Open-source Hong Kong public data over **MCP and HTTP**, extending
[mcp-open-data-hk](https://github.com/mcp-open-data-hk/mcp-open-data-hk).
The upstream MIT licence and author attribution are preserved.

## Public interfaces

- **Addresses:** bilingual DPO ALS lookup and candidate selection.
- **Restaurants:** complete validated FEHD/CSDI licence snapshots, text/district/radius
  queries, stable pagination and full-result summaries. Imports use CSDI's official
  single-response GeoJSON download because its paginated API can serve mixed
  source editions. Source record dates remain separate from validation time;
  source status exposes the actual download URL. Invalid collections, duplicate
  licence IDs, low coordinate coverage and large row-count drops retain the
  previously accepted snapshot.
- **District population:** all 18 districts, published reference year, population in
  persons, area and density.
- **SeeHouse / 睇樓:** Hong Kong building search, source-linked sale/rental listings,
  observed asking-price changes and coverage from our existing pipeline. [Search properties](https://mcp.hk/properties). [Pack contract](docs/seehouse.md).
- **Plate.hk (first external pack):** independent auction-history index, historical
  comparisons and dataset coverage, with original source links. [Search Plate.hk](https://mcp.hk/coverage?q=Plate.hk&access=all).
- **Real-time transport:** source-timestamp-validated MTR, bus, green-minibus and ferry arrival adapters, short caches and explicit coverage scope. See [request contracts and live verification](docs/transport.md).
- **Generic resources:** reconciled DATA.GOV.HK/CSDI inventory, source schema inspection and bounded record queries across CSV, JSON, GeoJSON, Excel, XML and API families. See [resource contracts and honest coverage](docs/resources.md) and [the coverage explorer](https://mcp.hk/coverage).
- **Developer interfaces:** eight preserved catalogue tools plus sixteen resource/pack tools,
  remote Streamable HTTP, local stdio, REST and OpenAPI.
- **Discovery:** one bilingual search covers connected queries and source datasets, including independent providers. Guided queries and the neighbourhood explorer use the real HTTP
  API, with source citations, error/empty states and equivalent HTTP/MCP/JSON views.

Hosted service: **https://mcp.hk** · [Browse data](https://mcp.hk/coverage) · [Connect your AI](https://mcp.hk/connect).

Remote MCP: `https://mcp.hk/mcp` (Streamable HTTP, public read-only, no server API key).
See [client connection examples](docs/connect.md) and [production recovery/schedules](docs/production.md).
Importing data locally does not modify the hosted service.
No model key or Cloudflare account is required. Runtime databases/captures are not
bundled or relicensed as MIT data.

## Quickstart

```sh
git clone https://github.com/heathermhuang/mcp-hk.git
cd mcp-hk
uv sync --extra test --extra dev
uv run mcp-hk-refresh all
uv run mcp-hk-http
```

Open `http://127.0.0.1:8000/demo`, `/sources` or `/docs`.
Set `MCP_HK_DATABASE` to use a different persistent database path.

```sh
curl 'http://127.0.0.1:8000/api/v1/addresses/search?q=Central%20Government%20Offices'
curl 'http://127.0.0.1:8000/api/v1/restaurants?lat=22.28046&lon=114.16537&radiusM=500&includeSummary=true'
curl 'http://127.0.0.1:8000/api/v1/districts/central-western/statistics'
curl 'http://127.0.0.1:8000/api/v1/plates/search?q=AA88'
curl 'http://127.0.0.1:8000/api/v1/plates/comparables?q=AH168'
curl 'http://127.0.0.1:8000/api/v1/packs'
```

For local stdio use `uv run mcp-hk`; the original `mcp-open-data-hk` command remains
available. For remote MCP connect to `http://127.0.0.1:8000/mcp` after starting the
HTTP server. Host/Origin allowlists must be configured for another hostname.

See [source field contracts and attribution](docs/sources.md),
[operations, Docker and release gates](docs/operations.md), and
[the upstream README](docs/upstream-readme.md) for the eight original tools.

## Contribute and verify

```sh
uv run pytest
uv run black --check src tests
uv run flake8 src tests
uv run python -m build
```

Keep source connectors, shared services and transport adapters separate. Add a small
attributed fixture and a deterministic failure test when changing a source schema.
Never expose arbitrary upstream URLs, SQL, ingestion controls or credentials through
public tools. Existing live network probes are opt-in with `pytest --live`; they do
not replace deterministic regression tests.

See [Plate.hk pack examples, semantics and limits](docs/platehk.md). Government
metadata discovery stays on `/api/v1/datasets`. Unified discovery uses
`/api/v1/catalogue/datasets` or `hk_catalogue_search`, with `access=all`,
`connected` or `sources`. Connected results include direct user actions and
HTTP/MCP methods; native source results include resource capability summaries.
The pack-only `/api/v1/packs` and `hk_data_packs` remain available.
See [the discovery UX contract and next onboarding priorities](docs/discovery-ux.md).

Public [developer guides](https://mcp.hk/guides) cover the HTTP API, MCP connections,
source citations and freshness in English and Traditional Chinese. See the
[search and AI discovery contract](docs/search-and-ai-discovery.md) for canonical
pages, the sitemap, crawler checks and owner indexing/citation measurement.

The detailed expansion plan and acceptance criteria are in [the engineering plan](docs/plans/government-expansion.md). Inventory discovery is not full government data onboarding; consult live coverage for validation, failures and remaining work.
