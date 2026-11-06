# Location Search API: bind the published request contract

The exact frozen resource `01d13836b343a057c89bf7f3dcb2abb7` belongs to native
dataset `hk-landsd-openmap-development-location-search-api`. Root diagnostics
returned `SOURCE_PARSE_ERROR`. Fresh native DATA.GOV.HK metadata identifies its
JSON resource URL as an HTML API specification, not a JSON response file.

The [official specification](https://portal.csdi.gov.hk/csdi-webpage/apidoc/LocationSearchAPI)
identifies version `v1.0.0` and a required search string `q` at
`https://www.map.gov.hk/gs/api/v1.0.0/locationSearch`. Its published `cultural centre`
example returns a JSON array with original bilingual names/addresses and numeric
`x/y` values. The separately retrieved example was a cached web observation;
it establishes response shape, not current hosted acceptance.

The exact specification URL now binds to that fixed published request template.
Missing input exposes `q` with no provider request or default search. Caller input
uses the existing 200-character bound and URL escaping; unknown parameters and
credentialed templates remain rejected. The known query API uses the existing
300-second API cache policy even if the catalogue marks its resource as a file.
Other URLs, versions, hosts and query endpoints are not guessed or auto-upgraded.

Responses retain native values and explicitly describe a parameter-scoped source
response. They do not establish unique places, a complete location inventory,
GeoAddress identity, geographic-coordinate interpretation, proximity or current
facility availability. No semantic point binding is added. Original catalogue
and actual response URLs remain distinct in provenance. Caller values remain in
caller-scoped actions and are not stored in shared selection options.

Tests cover exact URL binding/escaping, zero-call missing-input discovery,
source-context isolation after accepted queries, unchanged native coordinates,
held proximity, and preservation of an upstream denial through later metadata
requests. Actual hosted HTTP/native MCP canary and fresh recovery subsequently passed
for `fc71d10`, with 27 raw source matches; see `combined-release/`. No alternative host, header,
proxy, credential or source-denial retry is authorized by this contract.
