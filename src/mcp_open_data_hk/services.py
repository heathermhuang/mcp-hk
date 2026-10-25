"""Transport-independent services; MCP and HTTP call the same functions."""

import base64
import asyncio
import hashlib
import json
import math
import os
import time
import uuid
from datetime import datetime, timezone
from functools import lru_cache

from .contracts import DomainError, Envelope, RestaurantQuery
from .http import request_json
from .sources import DISTRICTS, SOURCES, available_packs, parse_addresses
from .storage import Store


def iso(timestamp: float):
    return datetime.fromtimestamp(timestamp, timezone.utc).isoformat()


def distance(lat, lon, rlat, rlon):
    a, b = math.radians(rlat - lat), math.radians(rlon - lon)
    h = (
        math.sin(a / 2) ** 2
        + math.cos(math.radians(lat))
        * math.cos(math.radians(rlat))
        * math.sin(b / 2) ** 2
    )
    return 6371000 * 2 * math.asin(min(1, math.sqrt(h)))


def restaurant_quality(row):
    missing_name = not any(row["name"].values())
    return {
        **row,
        "quality": {
            "sourceNameMissing": missing_name,
            "missingNameLanguages": [
                lang for lang, value in row["name"].items() if not value
            ],
            "missingAddressLanguages": [
                lang for lang, value in row["address"].items() if not value
            ],
            "tradingStatusVerified": False,
        },
    }


class Service:
    def __init__(self, store: Store):
        from .companies import Companies
        from .platehk import PlateHK
        from .resources import Resources
        from .seehouse import SeeHouse

        self.store = store
        self.address_slots = asyncio.Semaphore(3)
        self.companies = Companies()
        from .hkex import Hkex

        self.hkex = Hkex(self.companies)
        self.plates = PlateHK(self)
        self.properties = SeeHouse(self)
        self.resources = Resources(store)

    def envelope(
        self,
        data,
        pack,
        snapshot=None,
        retrieved=None,
        reference=None,
        require_fresh=False,
        **meta,
    ):
        source = SOURCES[pack]
        retrieved = snapshot["retrieved"] if snapshot else (retrieved or time.time())
        checked = snapshot["checked"] if snapshot else retrieved
        stale = time.time() - checked > source["freshnessSeconds"]
        if stale and require_fresh:
            raise DomainError(
                "STALE_SOURCE", "Fresh data is required; refresh this source"
            )
        provenance = {
            "sourceId": pack,
            "sourceUrl": source["sourceUrl"],
            "attribution": source["attribution"],
            "retrievedAt": iso(retrieved),
            "lastCheckedAt": iso(checked),
            "referencePeriod": reference,
            "stale": stale,
            "freshnessBasis": "last_successful_source_check",
        }
        warnings = (
            [
                {
                    "code": "STALE_SOURCE",
                    "message": "Last accepted snapshot is being served",
                    "affectedSourceId": pack,
                }
            ]
            if stale
            else []
        )
        return Envelope(
            data=data,
            meta={
                "requestId": uuid.uuid4().hex,
                "apiVersion": "v1",
                "snapshotIds": [snapshot["id"]] if snapshot else [],
                "truncated": False,
                **meta,
            },
            provenance=[provenance],
            warnings=warnings,
        ).model_dump()

    async def addresses(self, q: str, limit: int = 5, geo: bool = False):
        if not q.strip() or len(q) > 200 or not 1 <= limit <= 10:
            raise DomainError(
                "INVALID_QUERY", "Provide an address and limit between 1 and 10", 400
            )
        if geo and (len(q) != 19 or not q.isalnum()):
            raise DomainError("INVALID_GEOADDRESS", "Invalid GeoAddress", 400)
        key = hashlib.sha256(
            f"{geo}:{limit}:{q.strip().casefold()}".encode()
        ).hexdigest()
        cached = self.store.cache_get(key)
        if cached:
            rows, retrieved = cached
        else:
            try:
                self.store.consume_budget(
                    "addresses",
                    int(os.environ.get("MCP_HK_ADDRESS_DAILY_BUDGET", "10000")),
                )
                async with self.address_slots:
                    payload = await request_json(
                        "https://www.als.gov.hk/" + ("galookup" if geo else "lookup"),
                        {"ga" if geo else "q": q, "n": limit},
                    )
                rows = parse_addresses(payload)
                retrieved = self.store.cache_put(key, rows)
            except DomainError as exc:
                self.store.check("addresses", exc.code)
                raise
            except (KeyError, ValueError, TypeError) as exc:
                self.store.check("addresses", "SOURCE_SCHEMA_CHANGED")
                raise DomainError(
                    "SOURCE_SCHEMA_CHANGED", "ALS response schema changed"
                ) from exc
        if geo and not rows:
            raise DomainError("NOT_FOUND", "GeoAddress was not found", 404)
        return self.envelope(
            rows[0] if geo else {"items": rows, "selectionRequired": len(rows) > 1},
            "addresses",
            retrieved=retrieved,
        )

    def restaurants(self, query: RestaurantQuery):
        offset, snapshot_id = 0, None
        filters = query.model_dump(exclude={"cursor"})
        fingerprint = hashlib.sha256(
            json.dumps(filters, sort_keys=True).encode()
        ).hexdigest()
        if query.district and query.district not in {d["id"] for d in DISTRICTS}:
            raise DomainError(
                "INVALID_DISTRICT", "Use an ID from /api/v1/districts", 400
            )
        if query.cursor:
            try:
                token = json.loads(
                    base64.urlsafe_b64decode(
                        query.cursor + "=" * (-len(query.cursor) % 4)
                    )
                )
                if (
                    token["filter"] != fingerprint
                    or type(token["offset"]) is not int
                    or token["offset"] < 0
                    or not isinstance(token["snapshot"], str)
                    or len(token["snapshot"]) != 32
                ):
                    raise ValueError()
                offset, snapshot_id = token["offset"], token["snapshot"]
            except (ValueError, KeyError, TypeError) as exc:
                raise DomainError(
                    "INVALID_CURSOR", "Cursor does not match this query", 400
                ) from exc
        snapshot, rows = self.store.snapshot("restaurants", snapshot_id)
        term = query.q.casefold().strip()
        candidates = [
            r
            for r in rows
            if (not query.district or r["districtId"] == query.district)
            and (not query.licenceType or r["licenceType"] == query.licenceType)
            and (
                not term
                or term
                in json.dumps([r["name"], r["address"]], ensure_ascii=False).casefold()
            )
        ]
        located = sum(r["latitude"] is not None for r in candidates)
        results = []
        for row in candidates:
            if query.lat is not None:
                if row["latitude"] is None:
                    continue
                d = distance(query.lat, query.lon, row["latitude"], row["longitude"])
                if d > (query.radiusM or 500):
                    continue
                row = {**row, "distanceM": round(d, 1)}
            results.append(row)
        results.sort(key=lambda r: (r.get("distanceM", 0), r["id"]))
        end = offset + query.limit
        cursor = (
            base64.urlsafe_b64encode(
                json.dumps(
                    {"filter": fingerprint, "snapshot": snapshot["id"], "offset": end}
                ).encode()
            )
            .decode()
            .rstrip("=")
            if end < len(results)
            else None
        )
        data = {"items": [restaurant_quality(r) for r in results[offset:end]]}
        if query.includeSummary:
            groups = {}
            for r in results:
                groups[r["licenceType"]] = groups.get(r["licenceType"], 0) + 1
            data["summary"] = {
                "scope": "full_filtered_set",
                "totalMatched": len(results),
                "byLicenceType": [
                    {"licenceType": k, "count": v} for k, v in sorted(groups.items())
                ],
                "spatialCoverage": {
                    "scope": "nonspatial_filters",
                    "locatedCount": located,
                    "unlocatedCount": len(candidates) - located,
                },
            }
        return self.envelope(
            data,
            "restaurants",
            snapshot=snapshot,
            require_fresh=query.requireFresh,
            nextCursor=cursor,
            total=len(results),
            truncated=bool(cursor),
        )

    def restaurant(self, licence_id):
        snapshot, rows = self.store.snapshot("restaurants")
        for row in rows:
            if row["id"] == licence_id:
                return self.envelope(
                    restaurant_quality(row), "restaurants", snapshot=snapshot
                )
        raise DomainError(
            "NOT_FOUND", "Licence is not present in the accepted snapshot", 404
        )

    def districts(self):
        return {"items": DISTRICTS}

    def packs(self):
        return {
            "items": [
                {
                    **pack,
                    "catalogueId": "mcp:" + pack["id"],
                    "sourceUrl": SOURCES[pack["id"]]["sourceUrl"],
                    "attribution": SOURCES[pack["id"]]["attribution"],
                    "capability": "queryable",
                }
                for pack in available_packs()
            ]
        }

    def statistics(self, district, year=None, require_fresh=False):
        if district not in {d["id"] for d in DISTRICTS}:
            raise DomainError("NOT_FOUND", "District does not exist", 404)
        snapshot, rows = self.store.snapshot("population")
        rows = [
            r
            for r in rows
            if r["districtId"] == district
            and (year is None or r["referencePeriod"] == year)
        ]
        if not rows:
            raise DomainError(
                "NOT_FOUND",
                "No published statistic for that district/year in this snapshot",
                404,
            )
        row = max(rows, key=lambda r: r["referencePeriod"])
        return self.envelope(
            row,
            "population",
            snapshot=snapshot,
            reference=row["referencePeriod"],
            require_fresh=require_fresh,
        )

    def status(self):
        checks = self.store.checks()
        sources = []
        for pack, source in SOURCES.items():
            if pack in {"enigma", "company_registry"}:
                if self.companies.configured:
                    sources.append(
                        {
                            "sourceId": pack,
                            "sourceUrl": source["sourceUrl"],
                            "providerType": source["providerType"],
                            "attribution": source["attribution"],
                            "view": (
                                "archive" if pack == "enigma" else "latest_observed"
                            ),
                            "currentVerification": False,
                            "backendConfigured": True,
                            "availability": "checked_on_query",
                            "stale": True if pack == "enigma" else None,
                            "observationStatusUrl": (
                                "/api/v1/companies/updates/status"
                                if pack == "company_registry"
                                else None
                            ),
                        }
                    )
                continue
            check = checks.get(pack, {})
            sid = self.store.active(pack)
            item = {
                "sourceId": pack,
                "sourceUrl": source["sourceUrl"],
                "providerType": source.get("providerType", "government"),
                "attribution": source["attribution"],
                "snapshotId": sid,
                "lastSuccess": iso(check["success"]) if check.get("success") else None,
                "lastFailure": iso(check["failure"]) if check.get("failure") else None,
                "lastError": check.get("error"),
                "stale": not check.get("success")
                or time.time() - check["success"] > source["freshnessSeconds"],
            }
            if pack in {"restaurants", "population"}:
                interval = 86400 if pack == "restaurants" else 7 * 86400
                next_due = check["success"] + interval if check.get("success") else None
                missed = next_due is None or time.time() > next_due
                failed = bool(
                    check.get("failure")
                    and check["failure"] > (check.get("success") or 0)
                )
                item["refreshHealth"] = {
                    "state": "degraded" if missed or failed else "healthy",
                    "overdue": missed,
                    "latestAttemptFailed": failed,
                    "nextDueAt": iso(next_due) if next_due else None,
                    "acceptedSnapshotRetained": bool(sid),
                }
            if source.get("sourceResponseUrl"):
                item["sourceResponseUrl"] = source["sourceResponseUrl"]
            if sid:
                snap, rows = self.store.snapshot(pack)
                item.update(
                    recordCount=snap["count"],
                    snapshotRetrievedAt=iso(snap["retrieved"]),
                )
                if pack == "restaurants":
                    item["quality"] = {
                        "sourceNamesMissingBothLanguages": sum(
                            not any(r.get("name", {}).values()) for r in rows
                        ),
                        "chineseAddressesMissing": sum(
                            not r.get("address", {}).get("zhHant") for r in rows
                        ),
                        "scope": "Complete accepted licence snapshot; missing source labels are not invented.",
                    }
                    item["spatialCoverage"] = {
                        "locatedCount": sum(r["latitude"] is not None for r in rows),
                        "totalCount": len(rows),
                    }
            sources.append(item)
        return {
            "sources": sources,
            "ready": all(self.store.active(p) for p in ["restaurants", "population"]),
        }


@lru_cache(maxsize=1)
def get_service():
    return Service(Store(os.environ.get("MCP_HK_DATABASE", ".data/mcp-hk.sqlite3")))
