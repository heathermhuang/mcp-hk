# Sources and field contracts

Validated against live sources on 2026-10-16. Source content retains its provider's
terms; the MIT code licence does not relicense government data. The small attributed
fixtures under `tests/fixtures` are public source responses, not current data.

## Addresses

DPO Address Lookup Service: `https://www.als.gov.hk/lookup` and `/galookup`.
Use `Accept: application/json` and `Accept-Language: en,zh-Hant`.
`SuggestedAddress[].Address.PremisesAddress` contains the bilingual address,
19-character `GeoAddress`, and `GeospatialInformation.Latitude/Longitude` in WGS84.
`Easting/Northing` are HK1980 grid coordinates and must not be used as degrees.
Scores rank candidates; they are not probabilities. A candidate must be selected.
The register is not exhaustive and currently the display formatter focuses on
building/street information; it does not promise complete floor/unit formatting.

Attribution: Digital Policy Office, HKSAR Government, DATA.GOV.HK.
[Dataset](https://data.gov.hk/en-data/dataset/hk-dpo-als_01-als).

## Restaurant licences

FEHD CSDI layer:
`https://portal.csdi.gov.hk/server/rest/services/common/fehd_rcd_1630036390312_58893/FeatureServer/0`.

- `SEARCH02_EN`: licence record identity; do not deduplicate businesses by address.
- `NSEARCH03_EN/TC`: premises name; `ADDRESS_EN/TC`: address.
- `NAME_EN`: licence type; `SEARCH01_EN`: district label with explicit alias mapping.
- `LATITUDE/LONGITUDE`: named WGS84 coordinates; the default geometry is HK1980.
- `LASTUPDATE`: source record update date, not download or observation time.

FEHD exposes `Yau Tsim` and `Mong Kok` separately. The explicit alias registry maps
both to the current `yau-tsim-mong` district used in C&SD statistics. This is not
fuzzy matching. See the [C&SD 1996 by-census report](https://www.censtatd.gov.hk/en/data/stat_report/product/B1120083/att/B11200831996XXXXE0100.pdf)
for the combination of the former districts.

Read the complete object-ID set and request batches of at most 100 identities.
Larger encoded GET URLs were rejected by this gateway with HTTP 404. Verify every
batch's IDs and the final ID set; do not publish truncated pages. Missing coordinates
exclude a record from radius queries, not text queries. Spatial coverage counts
refer to nonspatial filters, not an estimate of unlocated records inside the radius.
The refresh rejects overall coordinate coverage below 95% or an unexpected >20%
row-count drop, retaining the previous generation.

Attribution: Food and Environmental Hygiene Department, HKSAR Government,
DATA.GOV.HK / CSDI. [Dataset](https://data.gov.hk/en-data/dataset/hk-fehd-fehdlmis-restaurant-licences).
A licence list is not evidence of opening hours, food quality or current trading.

## District statistics

C&SD layer:
`https://portal.csdi.gov.hk/server/rest/services/common/censtatd_rcd_1635934215448_25451/FeatureServer/0`.
The layer inspected was `Density_2024`. Keep `PERIOD` as the reference year.
`MYPOPN_LAND` is in thousands: convert 232.2 to 232200 persons.
`LA` is square kilometres and `POPN_D` is persons per square kilometre.
Require all 18 district identities before publishing. Do not substitute ingestion
date for the reference period or apply district-wide population to a radius.

Attribution: Census and Statistics Department, HKSAR Government, DATA.GOV.HK / CSDI.
[Dataset](https://data.gov.hk/en-data/dataset/hk-censtatd-census_geo-table110-02001-csdi).
[Units: C&SD table 110-02001](https://www.censtatd.gov.hk/en/web_table.html?id=110-02001).

## Catalogue and reuse

The inherited tools use the DATA.GOV.HK CKAN metadata APIs. The HTTP catalogue
currently searches live metadata; it is not an offline complete catalogue index.
The government packs and independent Plate.hk and SeeHouse packs query records. The compatibility catalogue response marks entries as catalogue-only. The separate reconciled inventory and generic record layer are described in [resource contracts](resources.md); validation and failure counts are public at `/coverage`.

[DATA.GOV.HK terms](https://data.gov.hk/en/terms-and-conditions),
[reuse FAQ](https://data.gov.hk/en/faq), [CSDI](https://portal.csdi.gov.hk/geoportal/).
Retain provider attribution. Review provider/CSDI redistribution conditions before
publishing bulk snapshots; full runtime captures and databases are excluded from
the repository, wheel and Docker build context.

## Plate.hk: first independent external pack

[Plate.hk](https://plate.hk/) is an independent index of Transport Department auction
PDFs and official workbook exports, not a government agency or a DATA.GOV.HK auction
dataset. The connector queries its public API directly and caches validated responses
for five minutes. It does not import a second full archive. Original source links,
plate layout, disposition, year ranges and provider attribution accompany records.
Read the [pack contract](platehk.md) and [provider guide](https://plate.hk/about.html).
The MIT software licence does not relicense provider or underlying source data.

## SeeHouse / 睇樓: independent property pack

[SeeHouse](https://see.house/) exposes our existing Hong Kong building and listing
pipeline through read-only public APIs. mcp.hk adds building search, attributed
sale/rental listings, observed asking-price changes and dated coverage.
Listing freshness and API retrieval remain separate. These advertisements are
not verified availability, achieved transaction prices or complete market coverage.
Read the [pack contract](seehouse.md) for examples, limits and source semantics.
