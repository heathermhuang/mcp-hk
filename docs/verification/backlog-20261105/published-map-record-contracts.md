# Remaining published map interfaces

Six dated parse-failure resources point to HTML specifications. This is a
published-interface distinction, not evidence of empty data or a provider denial.
The primary pages were inspected separately from the hosted reader failures.

| Native resource | Official specification | Record contract |
|---|---|---|
| `18e150f1f3e1fbe6f0171cdb5fe947d9` | [Identify](https://portal.csdi.gov.hk/csdi-webpage/apidoc/IdentifyAPI) | Explicit `x`, `y` in HK80 metres and `lang=en/zh`; JSON response. |
| `8249e3d730a8f969980548f55fd79d86` | [Search Nearby](https://portal.csdi.gov.hk/csdi-webpage/apidoc/SearchNearbyAPI) | Same explicit inputs; provider describes facilities within 1 km, not an independently complete/nearest mcp.hk result. |
| `6dcc39e9b683a2f8b1e38ae2e4cd6488` | [Number search](https://portal.csdi.gov.hk/csdi-webpage/apidoc/LPPUNSearchAPI) | Explicit published category and search text; JSON, with source identifier namespaces retained. |
| `7825a371cda35083cb7e0e3a40294a01` | [Lot Index](https://portal.csdi.gov.hk/csdi-webpage/apidoc/LotIndexAPI) | Explicit lot-index category and HK80 bbox; GML, at most 750 m by 600 m. |
| `30b638ab333c60296dfcd6ace9578b80` | [Vector map](https://portal.csdi.gov.hk/csdi-webpage/apidoc/VectorMapAPI) | PBF tiles and JSON presentation style; not a record representation. |
| `999d814248ffdd57ca4ab01355b44397` | [Vector labels](https://portal.csdi.gov.hk/csdi-webpage/apidoc/VectorMapLabelAPI) | PBF label tiles and JSON presentation style; not a record representation. |

The four record bindings use only their exact specification URLs, fixed documented
version `v1.0.0` and published request endpoints. Number search and Lot Index use
the currently recommended `mapapi.hkmapservice.gov.hk` domain; the publisher dates
old-domain deprecation to 15 March 2027. No old-host/version fallback is attempted.
Published category tokens and the explicitly shown lower-case example spellings
are accepted without changing caller case. Missing values have no defaults.

HK80 input units, allowed language/category values and the Lot Index extent limit
are exposed before any provider request. Nonfinite coordinates, unknown values,
inverted/oversized extents and undeclared parameters are rejected locally. Input
validation preserves caller text; output values, identifiers, geometry and CRS
remain raw. No WGS84 conversion, GeoAddress join, unique entity count, operational
availability, global nearest result or new semantic point binding is approved.

Vector map/style specifications expose non-record metadata without fetching tiles
or treating stylesheet JSON as data rows. Record queries fail explicitly. No
raster, PBF, OCR or general SQL/planner infrastructure is introduced.

Cached publisher examples establish shape only: Identify was observed from a
four-day-old web result and Search Nearby from an older cached result. The number
search example returned a web cache miss. The Lot Index example could not be read
by the web tool because of its XML content type; that tool limitation is not a
native provider status. Actual hosted HTTP/native MCP canaries and fresh recovery
remain required. No data access or whole-dataset gain is claimed by this document.

The publisher's attribution/terms notices remain attached to the specifications;
this change does not render maps or claim map-application acceptance.
