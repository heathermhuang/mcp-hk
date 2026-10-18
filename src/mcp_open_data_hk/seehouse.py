"""Read SeeHouse's existing public pipeline; never crawl or trigger refresh jobs."""

import asyncio
import hashlib
import json
import math
from urllib.parse import urlsplit

from .contracts import DomainError
from .http import request_json

ORIGIN = "https://see.house"
WARNING = {
    "code": "PROPERTY_ADVERTISEMENTS",
    "message": (
        "SeeHouse aggregates third-party advertisements. Prices and price changes are "
        "asking prices in HKD, not transactions or valuations. Availability and unit-level "
        "matching are not guaranteed. Keep original attribution, listing observation dates, "
        "freshness and dedupe context. API retrieval is not listing freshness; coverage is incomplete."
    ),
    "affectedSourceId": "seehouse",
}


def fields(names):
    return dict.fromkeys(names.split())


# Nested allowlists prevent new upstream fields (contacts, raw captures, operations)
# from silently entering the public MCP surface. None denotes a JSON scalar.
MATCH = fields("level confidence method unitLevelMatching")
BUILDING = {
    **fields("id name district address distanceMeters heightMeters storeys builtYear"),
    "coordinates": fields("latitude longitude"),
    "match": MATCH,
    "stats": fields(
        "rentCount buyCount dedupeClusterCount duplicateClusterCount lastUpdated"
    ),
    "listingState": fields("status source message"),
}
LISTING = {
    **fields(
        "id source sourceListingId mode propertyType title floorBand priceHkd saleableAreaFt2 grossAreaFt2 pricePerFt2 sourceUrl updatedAt parseQualityScore attributionRequired"
    ),
    "freshness": fields(
        "status score reason observedAt firstSeenAt lastSeenAt datePublished dateModified expiresAt"
    ),
    "confidence": fields("buildingMatch parseQualityScore matchLevel towerCount"),
    "sourceAttribution": fields("required source sourceListingId url observedAt"),
    "dedupeCluster": {
        **fields("id size displayRank isPrimary confidence reason"),
        "sourceListingRefs": [None],
    },
    "listingStatus": fields(
        "displayStatus showInApp sourceStatusChanged reason updatedAt"
    ),
    "trustBadges": [None],
}
EVENT = fields("source sourceListingId mode observedAt oldPriceHkd newPriceHkd")
TOTALS = fields(
    "officialIndexedDistricts queuedDistricts sourceBackedDistricts launchReadyDistricts activeSourceListings matchedSourceListings unmatchedSourceListings activeListingBuildings identityMatchedBuildingRefs freshListings agingListings staleListings avgMatchConfidence"
)
DISTRICT = {
    **fields(
        "key nameEn officialBuildings officialNamedBuildings activeSourceListings matchedSourceListings unmatchedSourceListings activeListingBuildings identityMatchedBuildingRefs freshListings staleListings latestSeenAt"
    ),
    "sourcesWithListings": [None],
    "knownGaps": [None],
}
SCHEMAS = {
    "search": {
        "candidates": [BUILDING],
        "releaseScope": {
            **fields("allowedMode"),
            "supportedDistricts": [fields("key nameEn nameZhHk")],
        },
        "unitLevelMatching": None,
    },
    "building": {**BUILDING, "listings": [LISTING]},
    "history": {
        **fields("buildingId generatedAt eventCount unitLevelMatching"),
        "events": [EVENT],
        "caveats": [None],
    },
    "coverage": {
        **fields("generatedAt fetchPolicy"),
        "officialIndex": {
            **fields("available reason"),
            "totals": fields(
                "officialBuildings indexedDistricts namedBuildings missingCoordinates apiFacingOfficialRows latestObservedAt"
            ),
        },
        "productionCoverage": {
            **fields("available reason computedAt reportPolicy"),
            "totals": TOTALS,
            "districts": [DISTRICT],
        },
    },
}


def project(value, schema):
    if value is None:
        return None
    if isinstance(schema, dict):
        if not isinstance(value, dict):
            raise ValueError("Expected an object")
        return {
            k: project(value[k], child) for k, child in schema.items() if k in value
        }
    if isinstance(schema, list):
        if not isinstance(value, list):
            raise ValueError("Expected a list")
        return [project(v, schema[0]) for v in value]
    if type(value) not in (str, int, float, bool) or (
        isinstance(value, float) and not math.isfinite(value)
    ):
        raise ValueError("Expected a finite JSON scalar")
    return value


def required(value, **types):
    if not isinstance(value, dict) or any(
        type(value.get(k)) is not t for k, t in types.items()
    ):
        raise ValueError("Missing or invalid public fields")


def amount(value):
    if value is not None and (
        type(value) not in (int, float) or not math.isfinite(value) or value < 0
    ):
        raise ValueError("Invalid asking price")


def source_url(value):
    if not isinstance(value, str):
        raise ValueError("Missing original source URL")
    url = urlsplit(value)
    if url.scheme != "https" or not url.hostname or url.username or url.password:
        raise ValueError("Invalid original source URL")


def parse(kind, payload):
    if kind == "search":
        required(payload, candidates=list, releaseScope=dict, unitLevelMatching=str)
        rows = payload["candidates"]
    elif kind == "building":
        required(payload, id=str, listings=list)
        rows = [payload]
        for row in payload["listings"]:
            required(
                row,
                id=str,
                source=str,
                sourceListingId=str,
                mode=str,
                sourceUrl=str,
                freshness=dict,
                sourceAttribution=dict,
            )
            if row["mode"] not in {"buy", "rent"}:
                raise ValueError("Unknown listing mode")
            if "priceHkd" not in row:
                raise ValueError("Missing asking price")
            amount(row["priceHkd"])
            source_url(row["sourceUrl"])
            required(row["freshness"], status=str)
            required(row["sourceAttribution"], url=str, source=str, sourceListingId=str)
            if (
                row["sourceAttribution"]["source"] != row["source"]
                or row["sourceAttribution"]["sourceListingId"] != row["sourceListingId"]
            ):
                raise ValueError("Mismatched listing attribution")
            source_url(row["sourceAttribution"]["url"])

    elif kind == "history":
        required(
            payload,
            buildingId=str,
            generatedAt=str,
            events=list,
            eventCount=int,
            caveats=list,
        )
        if payload["eventCount"] != len(payload["events"]):
            raise ValueError("Inconsistent event count")
        for row in payload["events"]:
            required(row, source=str, sourceListingId=str, observedAt=str)
            if not {"oldPriceHkd", "newPriceHkd"} <= row.keys():
                raise ValueError("Missing price-change values")
            amount(row["oldPriceHkd"])
            amount(row["newPriceHkd"])
        rows = []
    else:
        required(payload, generatedAt=str, officialIndex=dict, productionCoverage=dict)
        for layer in ["officialIndex", "productionCoverage"]:
            required(payload[layer], available=bool)
        rows = []
    for row in rows:
        required(row, id=str, match=dict, stats=dict, listingState=dict)
        required(row["match"], level=str, method=str, unitLevelMatching=str)
        required(row["stats"], rentCount=int, buyCount=int)
        required(row["listingState"], status=str, source=str)
        if (
            row["id"].startswith("hk-demo-")
            or row["listingState"].get("source") == "fixture_fallback"
            or row["match"].get("method") == "source_address_geo_fixture"
        ):
            raise ValueError("Demo data is not a pipeline result")
    return project(payload, SCHEMAS[kind])


class SeeHouse:
    def __init__(self, service):
        self.service = service
        self.slots = asyncio.Semaphore(3)

    async def query(self, kind, params=None, building_id=None):
        paths = {
            "search": "/api/v1/buildings/search",
            "coverage": "/api/v1/coverage/status",
            "building": f"/api/v1/buildings/{building_id}/listings",
            "history": f"/api/v1/buildings/{building_id}/price-history",
        }
        path = paths[kind]
        key = (
            "seehouse:"
            + hashlib.sha256(
                json.dumps([path, params], sort_keys=True).encode()
            ).hexdigest()
        )
        cached = self.service.store.cache_get(key, ttl=300)
        if cached:
            data, retrieved = cached
        else:
            try:
                async with self.slots:
                    cached = self.service.store.cache_get(key, ttl=300)
                    if cached:
                        data, retrieved = cached
                    else:
                        self.service.store.consume_budget("seehouse", 5000)
                        data = parse(kind, await request_json(ORIGIN + path, params))
                        if (
                            building_id
                            and data.get("id", data.get("buildingId")) != building_id
                        ):
                            raise ValueError("Wrong building returned")
                        retrieved = self.service.store.cache_put(
                            key, data, source="seehouse"
                        )
            except (ValueError, KeyError, TypeError, AttributeError, OverflowError):
                self.service.store.check("seehouse", "SOURCE_SCHEMA_CHANGED")
                raise DomainError(
                    "SOURCE_SCHEMA_CHANGED",
                    "SeeHouse returned an unexpected data schema",
                ) from None
            except DomainError as exc:
                if exc.code not in {"INVALID_QUERY", "NOT_FOUND"}:
                    self.service.store.check("seehouse", exc.code)
                raise
        envelope = self.service.envelope(data, "seehouse", retrieved=retrieved)
        envelope["provenance"][0].update(
            provider="SeeHouse",
            providerType="independent",
            accessMode="live_api",
            upstreamUrl=ORIGIN + path,
            cacheTtlSeconds=300,
        )
        envelope["warnings"].append(WARNING.copy())
        if kind in {"building", "history"}:
            envelope["meta"].update(total=None, truncated=None)
        if kind == "search":
            # Provider publishes a limited candidate list, not an exact total or cursor.
            envelope["meta"].update(
                returnedCount=len(data["candidates"]), total=None, truncated=None
            )
        return envelope

    async def search(self, query):
        return await self.query(
            "search",
            {
                "q": query.q,
                "limit": query.limit,
                "locale": "zh-HK" if query.lang == "zh-Hant" else "en-HK",
            },
        )

    async def building(self, query):
        return await self.query(
            "building",
            {"locale": "zh-HK" if query.lang == "zh-Hant" else "en-HK"},
            query.buildingId,
        )

    async def history(self, query):
        return await self.query(
            "history",
            {"locale": "zh-HK" if query.lang == "zh-Hant" else "en-HK"},
            query.buildingId,
        )
