"""Reviewed KMB/NLB joins over the existing fixed resource contracts.

Operator reference identities never come from TD IDs or a guessed service type.
"""

import math
import re
import time

from .contracts import DomainError
from .services import distance

KMB = {
    "routes": "5e0220a1c8fd74795df45db20cdadf25",
    "path": "e77eb5223d5a6a5a0efd1d3f1ebf613c",
    "stop": "f9bf5abc8a5ba5648102ed3e9f6b3d91",
    "eta": "853cb7eef6227f6f1c7e8fbdf73e4e02",
}
NLB = {
    "routes": "e93e78ef62922558d254b40ab498debe",
    "path": "7ecc09ed2263c187ca759ef34faf3587",
    "eta": "6364bb25c65c4f24f73b9b9a982c05a3",
}
ARRIVAL_RESOURCES = {KMB["eta"], NLB["eta"], "2b1b8d6b425bf3ddd1e1ddb811d54ba4"}


def invalid(message):
    return DomainError("TRANSPORT_MAPPING_UNVERIFIED", message, 503)


def complete(result):
    if result["meta"]["nextOffset"] is not None:
        raise invalid("Operator selection exceeds the verification bound")
    return result["data"]["items"]


def integer(value, maximum=10000):
    if isinstance(value, bool) or not re.fullmatch(r"[0-9]{1,6}", str(value)):
        raise invalid("Invalid operator identifier or sequence")
    number = int(value)
    if not 1 <= number <= maximum:
        raise invalid("Operator identifier or sequence exceeds its bound")
    return number


def kmb_names(value):
    names = {"en": value["name_en"], "zhHant": value["name_tc"]}
    # Current official stop responses append the same pole annotation in both
    # languages. This narrowly reviewed source convention is not fuzzy matching;
    # preserve the full original detail and still require the location and route.
    parsed = [
        re.fullmatch(r"(.+?)\s*\(([A-Z]{2}[0-9]{3})\)\s*", names[k]) for k in names
    ]
    if all(parsed) and parsed[0][2] == parsed[1][2]:
        names = {key: match[1].rstrip() for key, match in zip(names, parsed)}
    return names


async def expand_join(candidate, namespace, query):
    route = candidate["route"]["route"]
    if namespace == "kmb":
        bound = "O" if candidate["direction"] == "outbound" else "I"
        source = await query(
            KMB["routes"], {}, filters={"route": route, "bound": bound}
        )
        rows = complete(source)
        choices = []
        for row in rows:
            if row.get("route") != route or row.get("bound") != bound:
                raise invalid("KMB route/direction changed")
            service_type = row.get("service_type")
            integer(service_type, 999)
            choices.append(
                {
                    **candidate,
                    "operatorNamespace": "kmb",
                    "operatorServiceType": service_type,
                }
            )
        keys = [c["operatorServiceType"] for c in choices]
    else:
        source = await query(NLB["routes"], {}, filters={"routeNo": route})
        rows = complete(source)
        choices = []
        for row in rows:
            if row.get("routeNo") != route:
                raise invalid("NLB returned a different route")
            route_id = row.get("routeId")
            integer(route_id, 999999)
            choices.append(
                {
                    **candidate,
                    "operatorNamespace": "nlb",
                    "operatorRouteId": route_id,
                    "operatorRouteReference": row,
                }
            )
        keys = [str(c["operatorRouteId"]) for c in choices]
    if not choices or len(keys) != len(set(keys)):
        raise invalid("Operator route variants are missing or ambiguous")
    return choices


async def verified_stops(candidate, path, detail, name_key):
    """Match names/location and repeated occurrences against current operator order."""
    selected = []
    for target in (candidate["board"], candidate["alight"]):
        matched = None
        for row in sorted(path, key=lambda r: abs(r["sequence"] - target["sequence"])):
            sid, value = await detail(row)
            names = value["names"]
            coordinates = value["coordinates"]
            if not all(math.isfinite(v) for v in coordinates) or not (
                22 <= coordinates[0] <= 23 and 113 <= coordinates[1] <= 115
            ):
                raise invalid("Invalid operator stop coordinates")
            if (
                any(
                    name_key(target["name"][lang])
                    and name_key(target["name"][lang]) == name_key(names[lang])
                    for lang in ("en", "zhHant")
                )
                and distance(target["latitude"], target["longitude"], *coordinates)
                <= 35
            ):
                # Same policy as the existing Citybus join: source sequence is
                # only a lookup hint; exact name AND location establish the
                # selected route occurrence. This is not a global ID crosswalk.
                matched = sid
                break
        if matched is None:
            raise invalid("Operator name/location match is absent")
        sid = matched
        visits = [r for r in path if r["stopId"] == sid]
        occurrence = target.get("occurrence", 1)
        if len(visits) != target.get(
            "occurrenceCount", 1
        ) or not 1 <= occurrence <= len(visits):
            raise invalid("Repeated-stop topology differs from the reference")
        selected.append(visits[occurrence - 1])
    if selected[0]["sequence"] >= selected[1]["sequence"]:
        raise DomainError(
            "TRANSPORT_NOT_SERVING_ORDER",
            "Verified operator occurrences do not serve the selected stop order",
            422,
        )
    return selected


async def verify_join(candidate, query, name_key):
    namespace = candidate["operatorNamespace"]
    route = candidate["route"]["route"]
    provenance, details = [], {}
    if namespace == "kmb":
        service_type = candidate["operatorServiceType"]
        expected = "O" if candidate["direction"] == "outbound" else "I"
        source = await query(
            KMB["path"],
            {
                "route": route,
                "direction": candidate["direction"],
                "service_type": str(service_type),
            },
        )
        raw = complete(source)
        if any(
            r.get("route") != route
            or r.get("bound") != expected
            or str(r.get("service_type")) != str(service_type)
            or not re.fullmatch(r"[0-9A-F]{16}", str(r.get("stop", "")))
            for r in raw
        ):
            raise invalid("KMB route/stop/service identity changed")
        path = sorted(
            [
                {
                    "stopId": r["stop"],
                    "sequence": integer(r.get("seq"), 300),
                    "source": r,
                }
                for r in raw
            ],
            key=lambda r: r["sequence"],
        )
        if [r["sequence"] for r in path] != list(range(1, len(path) + 1)):
            raise invalid("KMB route sequence is incomplete")

        async def detail(row):
            sid = row["stopId"]
            if sid not in details:
                result = await query(KMB["stop"], {"stop_id": sid})
                values = complete(result)
                if len(values) != 1:
                    raise invalid("KMB did not return exactly one stop")
                value = values[0].get("data", values[0])
                if value.get("stop") != sid:
                    raise invalid("KMB stop identity changed")
                details[sid] = {
                    "names": kmb_names(value),
                    "coordinates": (float(value["lat"]), float(value["long"])),
                    "source": value,
                }
                provenance.extend(result["provenance"])
            return sid, details[sid]

        board, alight = await verified_stops(candidate, path, detail, name_key)
        candidate["operatorEligibilityVerified"] = True
        eta = await query(
            KMB["eta"],
            {
                "route": route,
                "stop_id": board["stopId"],
                "service_type": str(service_type),
            },
        )
        raw_eta = complete(eta)
        if any(
            r.get("route") != route
            or r.get("co") != "KMB"
            or r.get("dir") not in {"O", "I"}
            or (r.get("stop") is not None and r["stop"] != board["stopId"])
            for r in raw_eta
        ):
            raise invalid("KMB ETA route/stop/operator changed")
        for row in raw_eta:
            integer(row.get("seq"), 300)
            integer(row.get("service_type"), 999)
        items = [
            r
            for r in raw_eta
            if r["dir"] == expected
            and str(r["service_type"]) == str(service_type)
            and integer(r["seq"], 300) == board["sequence"]
        ]
        prediction_field = "eta"
        candidate["operatorBoardDetail"] = details[board["stopId"]]["source"]
        candidate["operatorAlightDetail"] = details[alight["stopId"]]["source"]
        candidate["operatorNameQualification"] = (
            "kmb-bilingual-pole-annotation-1: exact names after an optional identical bilingual (AA999) suffix, an evidence-backed source convention inference; full names retained."
        )
        candidate["variantWarning"] = (
            "KMB documents that shared-stop ETA predictions can occur in other service types; these are not independently identified buses."
        )
    else:
        route_id = candidate["operatorRouteId"]
        source = await query(NLB["path"], {"routeId": str(route_id)})
        raw = complete(source)
        path = [
            {"stopId": str(r["stopId"]), "sequence": i + 1, "source": r}
            for i, r in enumerate(raw)
        ]
        if len(path) > 300:
            raise invalid("NLB route exceeds occurrence bound")
        for r in raw:
            integer(r.get("stopId"), 999999)

        async def detail(row):
            value = row["source"]
            return row["stopId"], {
                "names": {"en": value["stopName_e"], "zhHant": value["stopName_c"]},
                "coordinates": (float(value["latitude"]), float(value["longitude"])),
            }

        board, alight = await verified_stops(candidate, path, detail, name_key)
        if sum(r["stopId"] == board["stopId"] for r in path) != 1:
            raise invalid("NLB ETA does not identify repeated boarding occurrences")
        candidate["operatorEligibilityVerified"] = True
        eta = await query(
            NLB["eta"],
            {"routeId": str(route_id), "stopId": board["stopId"], "languageCode": "en"},
        )
        items = complete(eta)
        prediction_field = "estimatedArrivalTime"
    candidate.update(
        {
            "arrivalStatus": "live",
            "operatorBoardStopId": board["stopId"],
            "operatorAlightStopId": alight["stopId"],
            "operatorBoardSequence": board["sequence"],
            "operatorAlightSequence": alight["sequence"],
            "operatorStopCount": alight["sequence"] - board["sequence"],
            "operatorBoardReference": board["source"],
            "operatorAlightReference": alight["source"],
            "arrivalCheckedAt": time.time(),
            "arrivals": {
                "items": items,
                "predictionField": prediction_field,
                "transport": eta["schema"]["transport"],
                "warnings": eta["warnings"],
                "provenance": eta["provenance"],
            },
            "operatorVerification": {
                "method": "route_membership_name_location_and_occurrence",
                "namespace": namespace,
                "provenance": source["provenance"] + provenance,
            },
        }
    )
