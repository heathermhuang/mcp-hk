"""Government and independent provider registry, with source-specific parsers."""

from decimal import Decimal
from typing import Any

from .contracts import Address, DistrictStatistics, DomainError, Name, Restaurant

PORTAL = "https://portal.csdi.gov.hk/server/rest/services/common/"
RESTAURANTS = PORTAL + "fehd_rcd_1630036390312_58893/FeatureServer/0"
RESTAURANTS_SNAPSHOT = (
    "https://portal.csdi.gov.hk/csdi-webpage/file-api?"
    "dataset_id=fehd_rcd_1630036390312_58893&format=geojson&layer_name=FEHD_RL"
)
POPULATION = PORTAL + "censtatd_rcd_1635934215448_25451/FeatureServer/0"
SOURCES = {
    "addresses": {
        "sourceUrl": "https://data.gov.hk/en-data/dataset/hk-dpo-als_01-als",
        "attribution": "Digital Policy Office, HKSAR Government, DATA.GOV.HK",
        "freshnessSeconds": 86400,
    },
    "restaurants": {
        "sourceUrl": "https://data.gov.hk/en-data/dataset/hk-fehd-fehdlmis-restaurant-licences",
        "sourceResponseUrl": RESTAURANTS_SNAPSHOT,
        "attribution": "Food and Environmental Hygiene Department, HKSAR Government, DATA.GOV.HK / CSDI",
        "freshnessSeconds": 129600,
    },
    "population": {
        "sourceUrl": "https://data.gov.hk/en-data/dataset/hk-censtatd-census_geo-table110-02001-csdi",
        "attribution": "Census and Statistics Department, HKSAR Government, DATA.GOV.HK / CSDI",
        "freshnessSeconds": 691200,
    },
    "catalogue": {
        "sourceUrl": "https://data.gov.hk/",
        "attribution": "DATA.GOV.HK and the respective data providers",
        "freshnessSeconds": 172800,
    },
    "seehouse": {
        "sourceUrl": "https://see.house/",
        "attribution": "SeeHouse / 睇樓; original listing providers retain their rights and attribution",
        "freshnessSeconds": 3600,
        "provider": "SeeHouse",
        "providerType": "independent",
        "accessMode": "live_api",
        "termsUrl": "https://see.house/",
    },
    "platehk": {
        "sourceUrl": "https://plate.hk/api.html",
        "attribution": "Plate.hk, independent index of Transport Department auction publications",
        "freshnessSeconds": 3600,
        "provider": "Plate.hk",
        "providerType": "independent",
        "accessMode": "live_api",
        "termsUrl": "https://plate.hk/about.html",
    },
}

PACKS = [
    {
        "id": "addresses",
        "title": "Hong Kong addresses",
        "provider": "Digital Policy Office",
        "providerType": "government",
        "http": ["/api/v1/addresses/search"],
        "tools": ["hk_address_search", "hk_address_get"],
    },
    {
        "id": "restaurants",
        "title": "Restaurant licences",
        "provider": "FEHD",
        "providerType": "government",
        "http": ["/api/v1/restaurants"],
        "tools": ["hk_restaurant_search", "hk_restaurant_get"],
    },
    {
        "id": "population",
        "title": "District statistics",
        "provider": "Census and Statistics Department",
        "providerType": "government",
        "http": ["/api/v1/districts"],
        "tools": ["hk_district_list", "hk_district_statistics"],
    },
    {
        "id": "platehk",
        "title": "Plate.hk auction history",
        "provider": "Plate.hk",
        "providerType": "independent",
        "accessMode": "live_api",
        "http": [
            "/api/v1/plates/search",
            "/api/v1/plates/comparables",
            "/api/v1/plates/datasets",
        ],
        "tools": ["hk_plate_search", "hk_plate_comparables", "hk_plate_datasets"],
    },
    {
        "id": "seehouse",
        "title": "SeeHouse Hong Kong buildings and property listings",
        "provider": "SeeHouse / 睇樓",
        "providerType": "independent",
        "accessMode": "live_api",
        "http": [
            "/api/v1/properties/search",
            "/api/v1/properties/building",
            "/api/v1/properties/price-history",
            "/api/v1/properties/coverage",
        ],
        "tools": [
            "hk_property_search",
            "hk_property_building",
            "hk_property_price_history",
            "hk_property_coverage",
        ],
    },
]

# Explicit aliases, not fuzzy matching between neighbourhood and district names.
DISTRICT_NAMES = [
    (
        "central-western",
        "Central and Western",
        "中西區",
        ["Central/Western", "CENTRAL & WESTERN DISTRICT"],
    ),
    ("wan-chai", "Wan Chai", "灣仔區", []),
    ("eastern", "Eastern", "東區", []),
    ("southern", "Southern", "南區", []),
    # FEHD retains the two licensing district labels. Explicitly combine them;
    # this is a source-specific mapping, not fuzzy neighbourhood geocoding.
    ("yau-tsim-mong", "Yau Tsim Mong", "油尖旺區", ["Yau Tsim", "Mong Kok"]),
    ("sham-shui-po", "Sham Shui Po", "深水埗區", []),
    ("kowloon-city", "Kowloon City", "九龍城區", []),
    ("wong-tai-sin", "Wong Tai Sin", "黃大仙區", []),
    ("kwun-tong", "Kwun Tong", "觀塘區", []),
    ("kwai-tsing", "Kwai Tsing", "葵青區", []),
    ("tsuen-wan", "Tsuen Wan", "荃灣區", []),
    ("tuen-mun", "Tuen Mun", "屯門區", []),
    ("yuen-long", "Yuen Long", "元朗區", []),
    ("north", "North", "北區", []),
    ("tai-po", "Tai Po", "大埔區", []),
    ("sha-tin", "Sha Tin", "沙田區", []),
    ("sai-kung", "Sai Kung", "西貢區", []),
    ("islands", "Islands", "離島區", []),
]
DISTRICTS = [
    {"id": k, "name": {"en": en, "zhHant": zh}} for k, en, zh, _ in DISTRICT_NAMES
]
ALIASES = {}
for key, en, zh, aliases in DISTRICT_NAMES:
    for alias in [key, en, zh, en + " DISTRICT", *aliases]:
        ALIASES[alias.casefold()] = key


def district_id(value: str | None) -> str | None:
    return ALIASES.get((value or "").strip().casefold())


def coordinates(lat: Any, lon: Any) -> tuple[float | None, float | None]:
    if lat in (None, "") or lon in (None, ""):
        return None, None
    a, b = float(lat), float(lon)
    if not (22.1 <= a <= 22.6 and 113.8 <= b <= 114.6):
        raise ValueError("Coordinates are not Hong Kong WGS84 degrees")
    return a, b


def parse_restaurant(feature: dict) -> dict:
    a = feature["attributes"]
    lat, lon = coordinates(a.get("LATITUDE"), a.get("LONGITUDE"))
    return Restaurant(
        id=str(a["SEARCH02_EN"]),
        name=Name(en=a.get("NSEARCH03_EN"), zhHant=a.get("NSEARCH03_TC")),
        address=Name(en=a.get("ADDRESS_EN"), zhHant=a.get("ADDRESS_TC")),
        districtId=district_id(a.get("SEARCH01_EN")),
        licenceType=a["NAME_EN"],
        latitude=lat,
        longitude=lon,
        upstreamUpdatedAt=a.get("LASTUPDATE"),
    ).model_dump()


def parse_population(feature: dict) -> dict:
    a = feature["attributes"]
    key = district_id(a["DC_ENG"])
    if not key:
        raise ValueError("Unrecognized source district")
    year = int(a["PERIOD"])
    # Table 110-02001 documents MYPOPN_LAND as Number ('000), not persons.
    return DistrictStatistics(
        id=f"{key}:{year}",
        districtId=key,
        name=Name(en=a["DC_ENG"], zhHant=a["DC_CHI"]),
        referencePeriod=year,
        population=int(Decimal(str(a["MYPOPN_LAND"])) * 1000),
        areaKm2=a["LA"],
        populationDensity=a["POPN_D"],
    ).model_dump()


def _format_address(a: dict, chinese: bool = False) -> str:
    prefix = "Chi" if chinese else "Eng"
    street = a.get(prefix + "Street", {})
    values = [
        a.get("BuildingName"),
        street.get("BuildingNoFrom"),
        street.get("StreetName"),
        a.get("Region"),
    ]
    return (" " if not chinese else "").join(str(v) for v in values if v)


def parse_addresses(payload: dict) -> list[dict]:
    if "SuggestedAddress" not in payload:
        raise DomainError("SOURCE_SCHEMA_CHANGED", "ALS response format changed")
    results = []
    for candidate in payload["SuggestedAddress"]:
        a = candidate["Address"]["PremisesAddress"]
        en, zh = a.get("EngPremisesAddress", {}), a.get("ChiPremisesAddress", {})
        geo = a.get("GeospatialInformation", {})
        if isinstance(geo, list):
            geo = geo[0] if geo else {}
        lat, lon = coordinates(geo.get("Latitude"), geo.get("Longitude"))
        results.append(
            Address(
                id=a["GeoAddress"],
                name=Name(en=en.get("BuildingName"), zhHant=zh.get("BuildingName")),
                address=Name(en=_format_address(en), zhHant=_format_address(zh, True)),
                districtId=district_id(en.get("EngDistrict", {}).get("DcDistrict")),
                latitude=lat,
                longitude=lon,
                score=candidate.get("ValidationInformation", {}).get("Score"),
            ).model_dump()
        )
    return results
