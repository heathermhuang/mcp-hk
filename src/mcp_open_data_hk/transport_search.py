"""Source-backed bus discovery; operator IDs are verified before live ETA joins."""

import asyncio
import csv
import hashlib
import io
import math
import re
import time
import unicodedata
from collections import defaultdict, Counter

from defusedxml import ElementTree as ET
from defusedxml.common import DefusedXmlException

from .contracts import DomainError
from .resource_fetch import fetch, fetch_file
from .services import distance
from .transport import timestamp

TD = "https://static.data.gov.hk/td/"
FILES = {
    "stops_en": TD + "pt-headway-en/stops.txt",
    "stops_tc": TD + "pt-headway-tc/stops.txt",
    "routes": TD + "routes-fares-xml/ROUTE_BUS.xml",
    "route_stops": TD + "routes-fares-xml/RSTOP_BUS.xml",
}
CITYBUS = {
    "route_stops": "8794004d904a1b6dd40199d3a5db1778",
    "stop": "3eca9b6a7bf3414531b1206042744a2f",
    "eta": "2b1b8d6b425bf3ddd1e1ddb811d54ba4",
}
TTL = 86400
WARNING = {
    "code": "BUS_DISCOVERY_SCOPE",
    "message": "Direct bus routes from dated Transport Department files, not a fastest-trip planner or proof of current operation. Distances are straight-line. Joined live ETAs currently support Citybus; other arrival feeds remain available through resource queries. Temporary diversions and service calendars are not inferred.",
}


def normalise(text):
    return " ".join(unicodedata.normalize("NFKC", text).casefold().split())


def name_key(text):
    return re.sub(r"[\W_]+", "", normalise(text))


def source_name(row, prefix):
    return {"en": row[prefix + "E"], "zhHant": row[prefix + "C"]}


def xml_rows(body, tag):
    root = ET.fromstring(body)
    if root.tag != "dataroot" or not len(root) or len(root) > 100000:
        raise ValueError("Invalid transport table")
    rows = []
    for node in root:
        if node.tag != tag or len({c.tag for c in node}) != len(node):
            raise ValueError("Invalid transport row")
        rows.append({c.tag: c.text or "" for c in node})
    return rows


def compile_index(rows):
    index = {"stops": {}, "routes": {}, "paths": defaultdict(list)}
    for row in rows:
        if row["kind"] == "stop":
            index["stops"][row["stopId"]] = row
        elif row["kind"] == "route":
            index["routes"][row["routeId"]] = row
        elif row["kind"] == "route_stop":
            index["paths"][(row["routeId"], row["direction"])].append(row)
    index["memberships"] = defaultdict(list)
    for (route_id, direction), path in index["paths"].items():
        path.sort(key=lambda r: r["sequence"])
        if [r["sequence"] for r in path] != list(range(1, len(path) + 1)):
            raise ValueError("Noncontiguous route sequence")
        for row in path:
            index["memberships"][row["stopId"]].append(
                {**index["routes"][route_id], **row}
            )
    return index


def parse_index(bodies, receipts):
    languages = {}
    for lang in ("en", "tc"):
        rows = list(
            csv.DictReader(io.StringIO(bodies["stops_" + lang].decode("utf-8-sig")))
        )
        if not rows or len(rows) > 20000:
            raise ValueError("Invalid stop table")
        languages[lang] = {r["stop_id"]: r for r in rows}
        if len(languages[lang]) != len(rows):
            raise ValueError("Duplicate stop IDs")
    if languages["en"].keys() != languages["tc"].keys():
        raise ValueError("Language snapshots disagree")
    routes = {}
    for r in xml_rows(bodies["routes"], "ROUTE"):
        key = r["ROUTE_ID"]
        if key in routes or r["ROUTE_TYPE"] != "1":
            raise ValueError("Invalid bus route")
        routes[key] = {
            "id": "route:" + key,
            "kind": "route",
            "routeId": key,
            "operator": r["COMPANY_CODE"],
            "route": r["ROUTE_NAMEE"],
            "origin": source_name(r, "LOC_START_NAME"),
            "destination": source_name(r, "LOC_END_NAME"),
            "serviceMode": r["SERVICE_MODE"],
            "specialType": r["SPECIAL_TYPE"],
            "sourceUpdatedAt": r["LAST_UPDATE_DATE"],
        }
    stops, paths, identities = {}, [], set()
    for r in xml_rows(bodies["route_stops"], "RSTOP"):
        sid, rid = r["STOP_ID"], r["ROUTE_ID"]
        if (
            rid not in routes
            or sid not in languages["en"]
            or r["ROUTE_SEQ"] not in {"1", "2"}
        ):
            raise ValueError("Orphan route or stop")
        en, tc = languages["en"][sid], languages["tc"][sid]
        lat, lon = float(en["stop_lat"]), float(en["stop_lon"])
        if not (
            math.isfinite(lat)
            and math.isfinite(lon)
            and 22 <= lat <= 23
            and 113 <= lon <= 115
        ):
            raise ValueError("Invalid WGS84 stop location")
        if (en["stop_lat"], en["stop_lon"]) != (tc["stop_lat"], tc["stop_lon"]):
            raise ValueError("Language stop coordinates disagree")
        stops[sid] = {
            "id": "stop:" + sid,
            "kind": "stop",
            "stopId": sid,
            "namespace": "td:stop",
            "name": {"en": en["stop_name"], "zhHant": tc["stop_name"]},
            "latitude": lat,
            "longitude": lon,
        }
        seq = int(r["STOP_SEQ"])
        key = f"path:{rid}:{r['ROUTE_SEQ']}:{seq}"
        if (
            key in identities
            or not 1 <= seq <= 300
            or r["STOP_PICK_DROP"] not in {"0", "1", "2", "3"}
        ):
            raise ValueError("Invalid route stop sequence")
        identities.add(key)
        paths.append(
            {
                "id": key,
                "kind": "route_stop",
                "routeId": rid,
                "stopId": sid,
                "direction": "outbound" if r["ROUTE_SEQ"] == "1" else "inbound",
                "sequence": seq,
                "name": source_name(r, "STOP_NAME"),
                "pickup": r["STOP_PICK_DROP"] in {"2", "3"},
                "dropoff": r["STOP_PICK_DROP"] in {"1", "3"},
                "sourcePickupDrop": r["STOP_PICK_DROP"],
                "sourceUpdatedAt": r["LAST_UPDATE_DATE"],
            }
        )
    rows = list(stops.values()) + list(routes.values()) + paths
    compile_index(rows)
    return rows + [{"id": "sources", "kind": "sources", "receipts": receipts}]


async def download_index():
    bodies, receipts = {}, []
    for key, url in FILES.items():
        if key == "route_stops":
            path, headers, final, _ = await fetch_file(url, maximum=32_000_000)
            try:
                body = await asyncio.to_thread(path.read_bytes)
            finally:
                path.unlink(missing_ok=True)
        else:
            body, headers, final, _ = await fetch(url, maximum=8_000_000)
        bodies[key] = body
        receipts.append(
            {
                "sourceUrl": final,
                "originalSourceUrl": url,
                "retrievedAt": time.time(),
                "sourceModified": headers.get("last-modified"),
                "contentHash": hashlib.sha256(body).hexdigest(),
            }
        )
    try:
        return await asyncio.to_thread(parse_index, bodies, receipts)
    except (ValueError, KeyError, TypeError, ET.ParseError, DefusedXmlException) as exc:
        raise DomainError(
            "TRANSPORT_INDEX_INVALID",
            "Official bus files could not be joined; prior index retained",
            502,
        ) from exc


class TransportSearch:
    def __init__(self, service):
        self.service = service
        self.lock = asyncio.Lock()
        self.cached = None
        self.failed_at = 0

    async def index(self):
        async with self.lock:
            if self.cached is None:
                try:
                    snapshot, rows = await asyncio.to_thread(
                        self.service.store.snapshot, "transport"
                    )
                    self.cached = (
                        snapshot,
                        await asyncio.to_thread(compile_index, rows),
                        rows,
                    )
                except DomainError as exc:
                    if exc.code != "DATA_NOT_LOADED":
                        raise
            if (
                self.cached is None or time.time() - self.cached[0]["checked"] >= TTL
            ) and time.time() - self.failed_at >= 300:
                try:
                    await asyncio.to_thread(
                        self.service.store.consume_budget, "transport_index", 6
                    )
                    rows = await download_index()
                    prior = self.cached[0]["id"] if self.cached else None
                    await asyncio.to_thread(
                        self.service.store.publish, "transport", rows, prior
                    )
                    snapshot, rows = await asyncio.to_thread(
                        self.service.store.snapshot, "transport"
                    )
                    self.cached = (
                        snapshot,
                        await asyncio.to_thread(compile_index, rows),
                        rows,
                    )
                except DomainError as exc:
                    self.failed_at = time.time()
                    await asyncio.to_thread(
                        self.service.store.check, "transport", exc.code
                    )
                    if self.cached is None:
                        raise
            if self.cached is None:
                raise DomainError(
                    "TRANSPORT_INDEX_UNAVAILABLE",
                    "Bus index refresh is in cooldown",
                    503,
                )
            return self.cached

    def envelope(self, cached, data):
        snapshot, _, rows = cached
        result = self.service.envelope(data, "transport", snapshot=snapshot)
        result["warnings"].append(WARNING)
        result["provenance"] += next(
            r["receipts"] for r in rows if r["kind"] == "sources"
        )
        result["meta"]["indexVersion"] = snapshot["id"]
        result["meta"]["arrivalFreshnessIndependent"] = True
        return result

    @staticmethod
    def matches(index, q="", lat=None, lon=None, radius=500, operator=""):
        needle = normalise(q)
        result = []
        for sid, stop in index["stops"].items():
            memberships = index["memberships"][sid]
            if operator and not any(
                operator in r["operator"].split("+") for r in memberships
            ):
                continue
            names = list(stop["name"].values()) + [
                s for r in memberships for s in r["name"].values()
            ]
            if (
                needle
                and needle != sid
                and not any(needle in normalise(n) for n in names)
            ):
                continue
            metres = (
                distance(lat, lon, stop["latitude"], stop["longitude"])
                if lat is not None
                else None
            )
            if metres is not None and metres > radius:
                continue
            result.append(
                {
                    **stop,
                    "distanceM": round(metres, 1) if metres is not None else None,
                    "operators": sorted(
                        {o for r in memberships for o in r["operator"].split("+")}
                    ),
                }
            )
        return sorted(result, key=lambda r: (r["distanceM"] or 0, r["stopId"]))

    async def stops(self, query):
        cached = await self.index()
        rows = await asyncio.to_thread(
            self.matches,
            cached[1],
            query.q,
            query.lat,
            query.lon,
            query.radiusM,
            query.operator,
        )
        return self.envelope(
            cached,
            {
                "items": rows[: query.limit],
                "totalMatched": len(rows),
                "selectionRequired": len(rows) > 1,
            },
        )

    async def routes(self, stop_id, operator=""):
        cached = await self.index()
        if stop_id not in cached[1]["stops"]:
            raise DomainError(
                "STOP_NOT_FOUND", "Select a TD stopId from stop search", 404
            )
        rows = cached[1]["memberships"][stop_id]
        return self.envelope(
            cached,
            {
                "stop": cached[1]["stops"][stop_id],
                "items": [
                    r
                    for r in rows
                    if not operator or operator in r["operator"].split("+")
                ],
            },
        )

    @staticmethod
    def direct(index, query):
        origins = TransportSearch.matches(
            index,
            query.origin,
            query.originLat,
            query.originLon,
            query.radiusM,
            query.operator,
        )
        destinations = TransportSearch.matches(
            index,
            query.destination,
            query.destinationLat,
            query.destinationLon,
            query.radiusM,
            query.operator,
        )
        if len(origins) > 50 or len(destinations) > 50:
            raise DomainError(
                "STOP_SELECTION_REQUIRED",
                "Too many matching stops; select stop IDs or a smaller radius",
                400,
            )
        orig = {r["stopId"]: r for r in origins}
        dest = {r["stopId"]: r for r in destinations}
        candidates = []
        for (rid, direction), path in index["paths"].items():
            route = index["routes"][rid]
            if query.operator and query.operator not in route["operator"].split("+"):
                continue
            counts = Counter(row["stopId"] for row in path)
            seen, occurrences = Counter(), {}
            for row in path:
                seen[row["stopId"]] += 1
                occurrences[row["sequence"]] = seen[row["stopId"]]
            for board in path:
                if board["stopId"] not in orig or not board["pickup"]:
                    continue
                for alight in path:
                    if (
                        alight["stopId"] in dest
                        and alight["dropoff"]
                        and alight["sequence"] > board["sequence"]
                    ):
                        candidates.append(
                            {
                                "route": route,
                                "direction": direction,
                                "board": {
                                    **orig[board["stopId"]],
                                    **board,
                                    "occurrence": occurrences[board["sequence"]],
                                    "occurrenceCount": counts[board["stopId"]],
                                },
                                "alight": {
                                    **dest[alight["stopId"]],
                                    **alight,
                                    "occurrence": occurrences[alight["sequence"]],
                                    "occurrenceCount": counts[alight["stopId"]],
                                },
                                "referenceStopCount": alight["sequence"]
                                - board["sequence"],
                                "arrivalStatus": "not_requested",
                            }
                        )
                        if len(candidates) > 10000:
                            raise DomainError(
                                "STOP_SELECTION_REQUIRED",
                                "Too many route occurrences; select exact stops",
                                400,
                            )
        candidates.sort(
            key=lambda r: (
                r["route"]["specialType"] != "0",
                (r["board"]["distanceM"] or 0) + (r["alight"]["distanceM"] or 0),
                r["referenceStopCount"],
                r["route"]["routeId"],
            )
        )
        return candidates, origins, destinations

    async def citybus(self, candidate, remaining, cache=None):
        cache = cache if cache is not None else {}
        route = candidate["route"]["route"]
        resources = self.service.resources

        async def query(resource, parameters):
            key = resource, tuple(sorted(parameters.items()))
            if key in cache:
                until, prior = cache[key]
                if until > time.monotonic():
                    if isinstance(prior, DomainError):
                        raise prior
                    return prior
            if remaining[0] <= 0:
                raise DomainError(
                    "TRANSPORT_LOOKUP_LIMIT",
                    "Live stop verification reached its request bound",
                    503,
                )
            remaining[0] -= 1
            await asyncio.to_thread(
                self.service.store.consume_budget, "transport_lookup", 5000
            )
            try:
                result = await resources.query(
                    resource, parameters=parameters, limit=100, require_fresh=True
                )
            except DomainError as exc:
                cache[key] = (float("inf"), exc)
                raise
            ttl = 20 if resource == CITYBUS["eta"] else 45
            fresh_until = (
                result.get("schema", {}).get("transport", {}).get("freshUntil")
            )
            if resource == CITYBUS["eta"] and isinstance(fresh_until, (float, int)):
                ttl = min(ttl, max(0, fresh_until - time.time()))
            if ttl <= 0 or any(p.get("stale") for p in result.get("provenance", [])):
                error = DomainError(
                    "STALE_SOURCE", "Fresh operator reference data is required", 503
                )
                cache[key] = (float("inf"), error)
                raise error
            cache[key] = (time.monotonic() + ttl, result)
            return result

        route_result = await query(
            CITYBUS["route_stops"],
            {"route": route, "direction": candidate["direction"]},
        )
        path = route_result["data"]["items"]
        if route_result["meta"]["nextOffset"] is not None or not path:
            raise DomainError(
                "TRANSPORT_MAPPING_UNVERIFIED",
                "Operator route exceeds the verification bound",
                503,
            )
        expected_dir = "O" if candidate["direction"] == "outbound" else "I"
        if any(
            r.get("route") != route
            or r.get("dir") != expected_dir
            or not re.fullmatch(r"[0-9]{6}", str(r.get("stop", "")))
            or not 1 <= int(r.get("seq", -1)) <= 300
            for r in path
        ) or len({int(r["seq"]) for r in path}) != len(path):
            raise DomainError(
                "TRANSPORT_MAPPING_UNVERIFIED", "Operator route identity changed", 503
            )
        details, found, selected_occurrences = {}, [], []
        for target in (candidate["board"], candidate["alight"]):
            matched = None
            # Sequence is only a lookup hint. Both name and location must agree;
            # current operator order, never the TD sequence, determines the ride.
            for row in sorted(
                path, key=lambda r: abs(int(r["seq"]) - target["sequence"])
            ):
                sid = row["stop"]
                if sid not in details:
                    result = await query(CITYBUS["stop"], {"stop_id": sid})
                    if len(result["data"]["items"]) != 1:
                        raise DomainError(
                            "TRANSPORT_MAPPING_UNVERIFIED",
                            "Operator did not return exactly one stop",
                            503,
                        )
                    detail = result["data"]["items"][0]
                    details[sid] = detail.get("data", detail), result["provenance"]
                detail, _ = details[sid]
                if detail.get("stop") != sid:
                    raise DomainError(
                        "TRANSPORT_MAPPING_UNVERIFIED",
                        "Operator stop identity changed",
                        503,
                    )
                same_name = any(
                    bool(name_key(target["name"][key]))
                    and name_key(detail.get("name_" + lang, ""))
                    == name_key(target["name"][key])
                    for lang, key in (("en", "en"), ("tc", "zhHant"))
                )
                coordinates = float(detail["lat"]), float(detail["long"])
                if not all(math.isfinite(c) for c in coordinates):
                    raise DomainError(
                        "TRANSPORT_MAPPING_UNVERIFIED",
                        "Operator stop has invalid coordinates",
                        503,
                    )
                if (
                    same_name
                    and distance(
                        target["latitude"],
                        target["longitude"],
                        *coordinates,
                    )
                    <= 35
                ):
                    matched = sid
                    break
            if matched is None:
                raise DomainError(
                    "TRANSPORT_MAPPING_UNVERIFIED",
                    "No verified operator name/location match for the selected stop",
                    503,
                )
            found.append(matched)
            visits = sorted(
                (r for r in path if r["stop"] == matched), key=lambda r: int(r["seq"])
            )
            if len(visits) != target.get("occurrenceCount", 1):
                raise DomainError(
                    "TRANSPORT_MAPPING_UNVERIFIED",
                    "Repeated-stop topology differs from the reference; occurrence is unverified",
                    503,
                )
            selected_occurrences.append(visits[target.get("occurrence", 1) - 1])
        board, alight = selected_occurrences
        if int(board["seq"]) >= int(alight["seq"]):
            raise DomainError(
                "TRANSPORT_MAPPING_UNVERIFIED",
                "Stops are not in the requested order on the current operator route",
                503,
            )
        candidate["operatorEligibilityVerified"] = True
        eta = await query(CITYBUS["eta"], {"route": route, "stop_id": found[0]})
        if any(
            r.get("route") != route or r.get("stop") != found[0]
            for r in eta["data"]["items"]
        ):
            raise DomainError(
                "TRANSPORT_MAPPING_UNVERIFIED",
                "Arrival source returned a different route or stop",
                503,
            )
        items = [
            r
            for r in eta["data"]["items"]
            if r.get("route") == route
            and r.get("stop") == found[0]
            and r.get("dir") == expected_dir
            and int(r.get("seq", -1)) == int(board["seq"])
        ]
        candidate.update(
            {
                "arrivalStatus": "live",
                "operatorBoardStopId": found[0],
                "operatorAlightStopId": found[1],
                "operatorStopCount": int(alight["seq"]) - int(board["seq"]),
                "operatorBoardSequence": int(board["seq"]),
                "operatorAlightSequence": int(alight["seq"]),
                "arrivalCheckedAt": time.time(),
                "arrivals": {
                    "items": items,
                    "transport": {
                        **eta["schema"]["transport"],
                        "arrivalState": (
                            "arrivals"
                            if items
                            else "no_arrivals_for_selected_direction"
                        ),
                    },
                    "warnings": eta["warnings"],
                    "provenance": eta["provenance"],
                },
                "operatorVerification": {
                    "method": "route_membership_name_and_location",
                    "provenance": route_result["provenance"]
                    + [p for sid in found for p in details[sid][1]],
                },
            }
        )

    async def journey(self, query):
        cached = await self.index()
        candidates, origins, destinations = await asyncio.to_thread(
            self.direct, cached[1], query
        )
        remaining, request_cache = [64], {}
        deadline = time.monotonic() + 45
        for candidate in candidates:
            if not query.includeArrivals:
                candidate["arrivalStatus"] = "unchecked"
                candidate["uncheckedReason"] = "not_requested"
                continue
            if "CTB" not in candidate["route"]["operator"].split("+"):
                candidate["arrivalStatus"] = "unchecked"
                candidate["uncheckedReason"] = "operator_join_not_qualified"
                continue
            if time.monotonic() >= deadline:
                candidate["arrivalStatus"] = "unchecked"
                candidate["uncheckedReason"] = "comparison_deadline"
                continue
            try:
                await asyncio.wait_for(
                    self.citybus(candidate, remaining, request_cache),
                    timeout=max(0, deadline - time.monotonic()),
                )
            except (
                DomainError,
                asyncio.TimeoutError,
                ValueError,
                KeyError,
                TypeError,
                IndexError,
            ) as exc:
                code = (
                    exc.code
                    if isinstance(exc, DomainError)
                    else (
                        "comparison_deadline"
                        if isinstance(exc, asyncio.TimeoutError)
                        else "TRANSPORT_MAPPING_UNVERIFIED"
                    )
                )
                if code in {"TRANSPORT_LOOKUP_LIMIT", "comparison_deadline"}:
                    candidate["arrivalStatus"] = "unchecked"
                    candidate["uncheckedReason"] = code
                else:
                    candidate["arrivalStatus"] = "unavailable"
                    candidate["arrivalError"] = {
                        "code": code,
                        "message": "Live arrivals could not be verified; the reference candidate remains unknown.",
                    }
        now = time.time()
        for candidate in candidates:
            if candidate["arrivalStatus"] != "live":
                continue
            live = candidate["arrivals"]["transport"]
            fresh_until = live.get("freshUntil", candidate["arrivalCheckedAt"] + 20)
            if fresh_until <= now:
                candidate["arrivalStatus"] = "unavailable"
                candidate["arrivalError"] = {
                    "code": "STALE_SOURCE",
                    "message": "Arrival evidence expired during comparison.",
                }
                candidate.pop("arrivals")
                continue
            predictions = []
            expired, unknown = 0, 0
            for row in candidate["arrivals"]["items"]:
                try:
                    predicted = timestamp(row.get("eta"))
                    if predicted >= now:
                        predictions.append((predicted, row["eta"]))
                    else:
                        expired += 1
                except (DomainError, ValueError, TypeError, AttributeError):
                    unknown += 1
            candidate["earliestPredictedDeparture"] = (
                min(predictions)[1] if predictions else None
            )
            candidate["predictionCoverage"] = {
                "future": len(predictions),
                "expired": expired,
                "unknown": unknown,
                "emptyFeedDoesNotProveNoService": True,
            }
        # Only after checking all eligible references do we merge the same live
        # boarding occurrence and apply presentation limits. Retain variant flags.
        groups, presented = {}, []
        for candidate in candidates:
            if candidate["arrivalStatus"] != "live":
                presented.append(candidate)
                continue
            key = (
                candidate["route"]["route"],
                candidate["direction"],
                candidate["operatorBoardStopId"],
                candidate["operatorBoardSequence"],
            )
            if key not in groups:
                groups[key] = candidate
                candidate["referenceVariants"] = []
                candidate["alightingAlternatives"] = []
                candidate["alightingAlternativeCount"] = 0
                presented.append(candidate)
            group = groups[key]
            variant = candidate["route"]
            if variant not in group["referenceVariants"]:
                group["referenceVariants"].append(variant)
            group["alightingAlternativeCount"] += 1
            if len(group["alightingAlternatives"]) < 10:
                group["alightingAlternatives"].append(
                    {
                        "referenceStop": candidate["alight"],
                        "operatorStopId": candidate["operatorAlightStopId"],
                        "operatorSequence": candidate["operatorAlightSequence"],
                    }
                )
        presented.sort(
            key=lambda c: (
                (
                    timestamp(c["earliestPredictedDeparture"])
                    if c.get("earliestPredictedDeparture")
                    else float("inf")
                ),
                c["route"]["routeId"],
                c["direction"],
                c["board"]["sequence"],
            )
        )
        accepted = sum(c["arrivalStatus"] == "live" for c in candidates)
        failed = sum(c["arrivalStatus"] == "unavailable" for c in candidates)
        unchecked = len(candidates) - accepted - failed
        checked = accepted + failed
        eligible = sum(bool(c.get("operatorEligibilityVerified")) for c in candidates)
        stale_index = time.time() - cached[0]["checked"] >= TTL
        complete = not failed and not unchecked and not stale_index
        earliest = next(
            (
                c["earliestPredictedDeparture"]
                for c in presented
                if c.get("earliestPredictedDeparture")
            ),
            None,
        )
        return self.envelope(
            cached,
            {
                "items": presented[: query.limit],
                "totalMatched": len(candidates),
                "totalDepartureChoices": len(presented),
                "originCandidates": origins[:10],
                "destinationCandidates": destinations[:10],
                "scope": "direct_bus_routes_only",
                "currentServiceVerified": False,
                "coverage": {
                    "candidate": len(candidates),
                    "eligible": eligible,
                    "eligibilityUnknown": len(candidates) - eligible,
                    "acceptedArrivalChecks": accepted,
                    "checked": checked,
                    "failed": failed,
                    "unchecked": unchecked,
                    "uncheckedReasons": dict(
                        Counter(
                            c.get("uncheckedReason")
                            for c in candidates
                            if c["arrivalStatus"] == "unchecked"
                        )
                    ),
                    "sourceRequests": 64 - remaining[0],
                    "requestLimit": 64,
                    "deadlineSeconds": 45,
                    "referenceIndexStale": stale_index,
                    "complete": complete,
                    "eligibilityMeaning": "Verified current operator boarding/alighting occurrence; service calendars remain unknown.",
                },
                "departureComparison": {
                    "scope": "earliest_reported_departure_among_checked_candidates",
                    "earliestPredictedAt": earliest,
                    "allReferenceCandidatesChecked": complete,
                    "globallyEarliest": False,
                    "serviceCalendarsVerified": False,
                    "walkingFeasibilityVerified": False,
                    "fastestArrivalVerified": False,
                },
            },
        )
