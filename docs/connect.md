# Use mcp.hk in your AI

Server URL: **https://mcp.hk/mcp**. Transport: **Streamable HTTP**.
This is a public read-only data service. No server API key or OAuth sign-in is
required. Your AI client must support custom remote MCP servers; availability and
settings depend on the client/workspace. The service does not grant your AI private
profile access or permission to make government submissions.

## Codex

```sh
codex mcp add mcp.hk --url https://mcp.hk/mcp
```

Start/reload the client, or use its MCP settings/status view to confirm the tools.
[Official MCP configuration documentation](https://learn.chatgpt.com/docs/extend/mcp?surface=cli).

## Claude Code

```sh
claude mcp add --transport http mcp-hk https://mcp.hk/mcp
```

Claude Code’s CLI does not allow dots in server identifiers, so its command uses
`mcp-hk`. Use `/mcp` to inspect connection status.
[Official documentation](https://code.claude.com/docs/en/mcp).

## Cursor

Add to `.cursor/mcp.json` for a project, or `~/.cursor/mcp.json` globally:

```json
{
  "mcpServers": {
    "mcp.hk": { "url": "https://mcp.hk/mcp" }
  }
}
```

[Official documentation](https://cursor.com/docs/mcp).

## Try it

“Use mcp.hk to resolve Central Government Offices, let me choose the address, then find
licensed restaurants within 500 metres. Include the district's population reference
year and official sources.”

“用 mcp.hk 查詢中環政府總部附近的持牌食肆，清楚標示牌照類別、直線距離、資料來源及人口統計年份。”

The tool directory includes government catalogue/resource tools, address/restaurant/
district/status tools, three Plate.hk tools, four SeeHouse tools and the pack directory.

“Use mcp.hk to look up the exact auction history of AA88 and compare AH168 with
historical sales. Keep the original sources, sample size and dates; do not present
historical prices as a current valuation.”

Plate.hk is the first independent external provider. See [its pack contract](platehk.md). Finding a catalogue entry does not mean every
dataset's records can be queried. Respect rate-limit responses and retry guidance.
The first call after inactivity can take longer while the accepted checkpoint is
restored; a cold start does not silently fabricate sample results.

For generic government resources, ask mcp.hk to call `hk_catalogue_search`, `hk_dataset_resources`, `hk_resource_schema` and `hk_resource_query`. Use `hk_coverage` for actual validation counts and failures. Discovery and API-response access do not establish that all government data is connected. See [resource contracts](resources.md).

## Cold startup

The single container restores its accepted inventory before serving data. Configure
Codex's existing connection with a 120-second startup window (the default 30-second
window timed out in the observed cold-client test):

```toml
[mcp_servers."mcp.hk"]
url = "https://mcp.hk/mcp"
startup_timeout_sec = 120
```

Update the existing section instead of duplicating it. The setting changes only this
connection; it does not change the model. A controlled cold restart followed by a real
Codex discovery/schema/record journey passed with this setting. Other clients should
also allow up to 120 seconds for cold startup.

The connection-specific startup setting is documented in the [official Codex configuration reference](https://learn.chatgpt.com/docs/config-file/config-reference).

For SeeHouse property data, use `hk_property_search` to choose a building, then
`hk_property_building` and `hk_property_price_history`. Read `hk_property_coverage`
for dated coverage and freshness. Prices are asking prices, not transactions.
See the [SeeHouse pack contract](seehouse.md) or [browser search](https://mcp.hk/properties).
