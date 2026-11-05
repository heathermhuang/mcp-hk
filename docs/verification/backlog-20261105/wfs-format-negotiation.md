# Planning WFS format negotiation

The frozen resource `f517af5f1721b0896cca46a0dec103f3` advertised four explicit
feature types, but each selected read returned `SOURCE_PARSE_ERROR`. The generic
reader requested `application/json`; the source's WFS 2 GetFeature capability
advertises `GEOJSON` and `ESRIGEOJSON` but not that media type. This is an internal
reader defect, not a provider refusal or a successful empty response.

The repair applies the existing advertised-format and native before/after-hit
contract to ArcGIS-hosted `WFSServer` endpoints outside CSDI. It retains exact
type namespaces, source values/CRS, all count checks and the existing row, byte,
page, deadline, cache, selection and recovery bounds. Generic WFS URLs retain their
existing exact JSON matched-count requirement. The CSDI contract/key remains
unchanged; other negotiated endpoints get `wfs-2-count-1` and a distinct selection
key so prior acceptance cannot imply adoption. Provider denials stop immediately.

An official capability document and the small explicitly advertised
`APP_AMEND_CSDI:AMEND_CRT` selection were captured on 6 November 2026. Native hits
before and after both reported 16; the declared GEOJSON response contained 16
features. The compressed unmodified fixtures and their source-response hashes
are retained with the tests and adjacent receipts. This is one selected view,
already represented by an accepted ArcGIS alternative, not a new dataset gain.
Other planning feature types remain separately unqualified and can hit capacity
or source holds. Stable native counts do not establish an atomic publication.

Fixtures cover the real capability/16-feature response and both host families'
unsupported-format, unknown/changing/conflicting/short count, row-budget and
immediate-denial paths. Local source replay is distinct from deployed HTTP/native
MCP acceptance. That gate now passed for three exact planning selections, with
two capacity holds retained; fresh isolated recovery and actual restored clients
also passed. See `RELEASED.md` and `wfs-release/` for the released scope.
