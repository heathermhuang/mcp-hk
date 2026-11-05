"""Bus discovery joins must preserve namespaces, direction and failure evidence."""

import copy
import json
import sqlite3
import time
from xml.etree import ElementTree as ET

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.server import create_server
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store
from mcp_open_data_hk.transport_api import JourneyQuery, StopQuery
from mcp_open_data_hk.transport_search import CITYBUS, compile_index, parse_index
from mcp_open_data_hk.transport_joins import KMB, NLB


def test_kmb_name_annotation_is_bilingual_exact_and_preserves_source_values():
    from mcp_open_data_hk.transport_joins import kmb_names

    source = {"name_en": "STOP NAME (WT001)", "name_tc": "巴士站 (WT001)"}
    assert kmb_names(source) == {"en": "STOP NAME", "zhHant": "巴士站"}
    assert source["name_en"].endswith("(WT001)")
    different = {**source, "name_tc": "巴士站 (WT002)"}
    assert kmb_names(different)["en"] == source["name_en"]
    ordinary_name = {"name_en": "STOP (TERMINAL)", "name_tc": "巴士站 (總站)"}
    assert kmb_names(ordinary_name)["en"] == ordinary_name["name_en"]


def xml(tag, rows):
    root = ET.Element("dataroot")
    for row in rows:
        node = ET.SubElement(root, tag)
        for key, value in row.items():
            ET.SubElement(node, key).text = str(value)
    return ET.tostring(root)


@pytest.fixture
def bodies():
    route = {
        "ROUTE_ID": "1750",
        "COMPANY_CODE": "CTB",
        "ROUTE_NAMEE": "12",
        "ROUTE_TYPE": "1",
        "LOC_START_NAMEE": "Central",
        "LOC_START_NAMEC": "中環",
        "LOC_END_NAMEE": "Robinson Road",
        "LOC_END_NAMEC": "羅便臣道",
        "SERVICE_MODE": "R",
        "SPECIAL_TYPE": "0",
        "LAST_UPDATE_DATE": "2026-11-01",
    }
    stop_names = [
        ("261", "Lan Kwai Fong", "蘭桂坊"),
        ("262", "Lyndhurst Terrace", "擺花街"),
        ("249", "Seymour Road", "西摩道"),
    ]
    rows = [
        {
            "ROUTE_ID": "1750",
            "ROUTE_SEQ": "1",
            "STOP_SEQ": str(i),
            "STOP_ID": sid,
            "STOP_PICK_DROP": "3",
            "STOP_NAMEE": en,
            "STOP_NAMEC": zh,
            "LAST_UPDATE_DATE": "2026-11-01",
        }
        for i, (sid, en, zh) in enumerate(stop_names, 1)
    ]
    header = "stop_id,stop_name,stop_lat,stop_lon\n"
    return {
        "stops_en": (
            header
            + "261,Lan Kwai Fong,22.2815165,114.1561392\n262,Lyndhurst Terrace,22.282,114.155\n249,Seymour Road,22.2831597,114.1478635\n"
        ).encode(),
        "stops_tc": (
            header
            + "261,蘭桂坊,22.2815165,114.1561392\n262,擺花街,22.282,114.155\n249,西摩道,22.2831597,114.1478635\n"
        ).encode(),
        "routes": xml("ROUTE", [route]),
        "route_stops": xml("RSTOP", rows),
    }


@pytest.fixture
def service(tmp_path, bodies, monkeypatch):
    service = Service(Store(str(tmp_path / "transport.sqlite3")))

    async def download():
        return parse_index(
            bodies,
            [
                {
                    "sourceUrl": "https://static.data.gov.hk/td/example",
                    "contentHash": "source-hash",
                }
            ],
        )

    monkeypatch.setattr("mcp_open_data_hk.transport_search.download_index", download)
    return service


def test_source_join_preserves_td_namespace_and_refuses_language_mismatch(bodies):
    rows = parse_index(bodies, [])
    index = compile_index(rows)
    assert index["stops"]["261"]["namespace"] == "td:stop"
    assert index["stops"]["261"]["name"]["zhHant"] == "蘭桂坊"
    changed = {
        **bodies,
        "stops_tc": bodies["stops_tc"].replace(b"114.1561392", b"114.2"),
    }
    with pytest.raises(ValueError, match="coordinates disagree"):
        parse_index(changed, [])


def test_unknown_pickup_flag_never_becomes_permission(bodies):
    changed = {
        **bodies,
        "route_stops": bodies["route_stops"].replace(
            b"<STOP_PICK_DROP>3", b"<STOP_PICK_DROP>0"
        ),
    }
    index = compile_index(parse_index(changed, []))
    candidates, _, _ = service_direct(index)
    assert candidates == []
    assert index["paths"][("1750", "outbound")][0]["sourcePickupDrop"] == "0"


def service_direct(index, **args):
    from mcp_open_data_hk.transport_search import TransportSearch

    return TransportSearch.direct(
        index, JourneyQuery(origin="Lan Kwai Fong", destination="Seymour Road", **args)
    )


@pytest.mark.asyncio
async def test_bilingual_nearby_search_routes_and_restored_index(service, monkeypatch):
    english = await service.transport.stops(StopQuery(q="lan kwai"))
    chinese = await service.transport.stops(StopQuery(q="蘭桂坊"))
    nearby = await service.transport.stops(
        StopQuery(lat=22.2815165, lon=114.1561392, radiusM=20)
    )
    for result in (english, chinese, nearby):
        assert result["data"]["items"][0]["stopId"] == "261"
        assert result["meta"]["indexVersion"] == english["meta"]["indexVersion"]
    routes = await service.transport.routes("261")
    assert routes["data"]["items"][0]["route"] == "12"
    assert routes["data"]["items"][0]["direction"] == "outbound"
    # Exercise a physical SQLite backup, rather than a second connection to the
    # source WAL database. The optional bus index must survive normal recovery.
    restored_path = service.store.path + ".restored"
    with service.store.connect() as source, sqlite3.connect(restored_path) as target:
        source.backup(target)
    restored = Service(Store(restored_path))

    async def forbidden():
        raise AssertionError("A fresh restored snapshot must not be downloaded again")

    monkeypatch.setattr("mcp_open_data_hk.transport_search.download_index", forbidden)
    assert (await restored.transport.stops(StopQuery(q="lan kwai")))["data"] == english[
        "data"
    ]


@pytest.mark.asyncio
async def test_direct_routes_obey_order_pickup_and_operator(service):
    result = await service.transport.journey(
        JourneyQuery(origin="261", destination="249", includeArrivals=False)
    )
    assert result["data"]["items"][0]["referenceStopCount"] == 2
    assert not result["data"]["currentServiceVerified"]
    assert (
        await service.transport.journey(JourneyQuery(origin="249", destination="261"))
    )["data"]["items"] == []
    assert (await service.transport.stops(StopQuery(q="Lan", operator="KMB")))["data"][
        "items"
    ] == []


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "broken",
    [
        None,
        "direction",
        "location",
        "eta_identity",
        "empty_stop",
        "path_sequence_bool",
        "eta_sequence_bool",
        "eta_direction",
        "eta_operator",
    ],
)
async def test_live_join_uses_verified_operator_order_and_preserves_eta_flags(
    service, monkeypatch, broken
):
    calls = []

    async def query(resource, parameters, **kwargs):
        calls.append((resource, parameters))
        if resource == CITYBUS["route_stops"]:
            items = [
                {"route": "12", "dir": "O", "seq": seq, "stop": sid}
                for seq, sid in [(4, "001042"), (5, "001084"), (11, "001021")]
            ]
        elif resource == CITYBUS["stop"]:
            sid = parameters["stop_id"]
            en, tc, lat, lon = {
                "001042": ("Lan Kwai Fong", "蘭桂坊", 22.2815165, 114.1561392),
                "001021": ("Seymour Road", "西摩道", 22.2831597, 114.1478635),
                "001084": ("Elsewhere", "其他", 22.282, 114.155),
            }[sid]
            items = [
                {
                    "data": {
                        "stop": sid,
                        "name_en": en,
                        "name_tc": tc,
                        "lat": str(lat),
                        "long": str(lon),
                    }
                }
            ]
        else:
            items = [
                {
                    "route": "12",
                    "stop": "001042",
                    "dir": "O",
                    "seq": 4,
                    "eta": "2026-11-05T18:00:00+08:00",
                    "rmk_en": "Scheduled bus",
                }
            ]
        if broken == "direction" and resource == CITYBUS["route_stops"]:
            for row in items:
                row["dir"] = "I"
        if broken == "location" and resource == CITYBUS["stop"]:
            items[0]["data"]["lat"] = "22.5"
        if broken == "eta_identity" and resource == CITYBUS["eta"]:
            items[0]["stop"] = "999999"
        if broken == "empty_stop" and resource == CITYBUS["stop"]:
            items = []
        if broken == "path_sequence_bool" and resource == CITYBUS["route_stops"]:
            items[0]["seq"] = True
        if broken == "eta_sequence_bool" and resource == CITYBUS["eta"]:
            items[0]["seq"] = True
        if broken == "eta_direction" and resource == CITYBUS["eta"]:
            items[0]["dir"] = "unknown"
        if broken == "eta_operator" and resource == CITYBUS["eta"]:
            items[0]["co"] = "another-operator"

        return {
            "data": {"items": items},
            "meta": {"nextOffset": None},
            "schema": {
                "transport": {"cacheTTLSeconds": 20, "arrivalState": "arrivals"}
            },
            "provenance": [
                {"sourceUrl": "https://rt.data.gov.hk/example", "stale": False}
            ],
            "warnings": [{"code": "PROVIDER_ADVISORY"}],
        }

    monkeypatch.setattr(service.resources, "query", query)
    result = await service.transport.journey(
        JourneyQuery(origin="Lan Kwai Fong", destination="Seymour Road")
    )
    candidate = result["data"]["items"][0]
    if broken:
        assert candidate["arrivalStatus"] == "unavailable"
        assert candidate["arrivalError"]["code"] == "TRANSPORT_MAPPING_UNVERIFIED"
        assert "arrivals" not in candidate
        return
    assert candidate["arrivalStatus"] == "live"
    assert candidate["operatorBoardStopId"] == "001042"
    assert candidate["operatorAlightStopId"] == "001021"
    assert candidate["operatorStopCount"] == 7
    assert candidate["referenceStopCount"] == 2
    assert candidate["arrivals"]["items"][0]["rmk_en"] == "Scheduled bus"
    assert candidate["arrivals"]["warnings"][0]["code"] == "PROVIDER_ADVISORY"
    assert (CITYBUS["eta"], {"route": "12", "stop_id": "001042"}) in calls
    assert all(p.get("stop_id") != "261" for _, p in calls)


@pytest.mark.asyncio
async def test_source_failure_is_not_an_empty_success(service, monkeypatch):
    async def failing(*args, **kwargs):
        raise DomainError("SOURCE_NOT_FOUND", "Provider returned HTTP 404", 502)

    monkeypatch.setattr(service.resources, "query", failing)
    result = await service.transport.journey(
        JourneyQuery(origin="Lan Kwai Fong", destination="Seymour Road")
    )
    candidate = result["data"]["items"][0]
    assert candidate["arrivalStatus"] == "unavailable"
    assert candidate["arrivalError"]["code"] == "SOURCE_NOT_FOUND"
    assert "arrivals" not in candidate


@pytest.mark.asyncio
async def test_expired_index_refresh_failure_retains_last_good_with_stale_warning(
    service, monkeypatch
):
    await service.transport.stops(StopQuery(q="Lan"))
    service.transport.cached[0]["checked"] = time.time() - 2 * 86400
    calls = []

    async def failing():
        calls.append(True)
        raise DomainError("SOURCE_UNAVAILABLE", "Source offline", 502)

    monkeypatch.setattr("mcp_open_data_hk.transport_search.download_index", failing)
    result = await service.transport.stops(StopQuery(q="Lan"))
    assert result["data"]["items"]
    assert result["provenance"][0]["stale"]
    assert "STALE_SOURCE" in {w["code"] for w in result["warnings"]}
    await service.transport.stops(StopQuery(q="Lan"))
    assert len(calls) == 1


def test_http_validation_and_discovery(service):
    with TestClient(create_app(service)) as client:
        assert client.get("/api/v1/transport/stops").status_code == 400
        assert client.get("/api/v1/transport/stops?lat=22.28").status_code == 400
        assert (
            client.get("/api/v1/transport/stops?q=Lan&operator=unknown").status_code
            == 400
        )
        assert (
            client.post(
                "/api/v1/transport/journeys", json={"origin": "Lan"}
            ).status_code
            == 400
        )
        result = client.get("/api/v1/transport/stops?q=Lan%20Kwai").json()
        assert result["data"]["items"][0]["stopId"] == "261"
        packs = client.get("/api/v1/packs").json()["items"]
        assert {"transport", "catalogue"} <= {p["id"] for p in packs}
        assert (
            client.get("/api/v1/transport/stops/261/routes").json()["data"]["items"][0][
                "route"
            ]
            == "12"
        )


@pytest.mark.asyncio
async def test_mcp_and_http_search_contracts_match(service):
    server = create_server(service)
    async with Client(server) as client:
        tools = {t.name for t in await client.list_tools()}
        assert {
            "hk_transport_stop_search",
            "hk_transport_stop_routes",
            "hk_transport_journey",
        } <= tools
        schema = next(
            t for t in await client.list_tools() if t.name == "hk_transport_stop_search"
        ).inputSchema
        assert {"CTB", "KMB"} <= set(schema["properties"]["operator"]["enum"])
        result = await client.call_tool("hk_transport_stop_search", {"q": "蘭桂坊"})
        payload = json.loads(result.content[0].text)
    assert (
        payload["data"]
        == (await service.transport.stops(StopQuery(q="蘭桂坊")))["data"]
    )


def test_parser_rejects_duplicate_ids_and_orphan_stop(bodies):
    changed = copy.deepcopy(bodies)
    changed["route_stops"] = bodies["route_stops"].replace(
        b"<STOP_ID>261", b"<STOP_ID>999"
    )
    with pytest.raises(ValueError, match="Orphan"):
        parse_index(changed, [])


@pytest.mark.asyncio
async def test_comparison_checks_later_candidates_before_presentation_limit(
    service, monkeypatch
):
    from datetime import datetime, timezone

    cached = await service.transport.index()
    base = service.transport.direct(
        cached[1], JourneyQuery(origin="Lan", destination="Seymour")
    )[0][0]
    candidates = [copy.deepcopy(base) for _ in range(2)]
    for i, candidate in enumerate(candidates):
        candidate["route"]["routeId"] = "synthetic-" + str(i)
        candidate["route"]["route"] = "fixture-later" if i == 0 else "fixture-earlier"
    monkeypatch.setattr(service.transport, "direct", lambda *a: (candidates, [], []))
    calls = []

    async def citybus(candidate, remaining, cache):
        calls.append(candidate["route"]["route"])
        eta = datetime.fromtimestamp(
            time.time() + (600 if len(calls) == 1 else 120), timezone.utc
        ).isoformat()
        candidate.update(
            arrivalStatus="live",
            operatorEligibilityVerified=True,
            operatorBoardStopId="001042",
            operatorAlightStopId="001021",
            operatorBoardSequence=4,
            operatorAlightSequence=11,
            arrivalCheckedAt=time.time(),
            arrivals={
                "items": [{"eta": eta}],
                "transport": {"freshUntil": time.time() + 20},
            },
        )

    monkeypatch.setattr(service.transport, "citybus", citybus)
    result = await service.transport.journey(
        JourneyQuery(origin="Lan", destination="Seymour", limit=1)
    )
    data = result["data"]
    assert len(calls) == data["coverage"]["checked"] == 2
    assert data["items"][0]["route"]["route"] == "fixture-earlier"
    assert data["coverage"]["complete"]
    assert not data["departureComparison"]["globallyEarliest"]


@pytest.mark.asyncio
@pytest.mark.parametrize("loop", [False, True])
async def test_operator_reads_deduplicate_and_repeated_stops_keep_occurrence(
    service, bodies, monkeypatch, loop
):
    from datetime import datetime, timezone

    if loop:
        root = ET.fromstring(bodies["route_stops"])
        first, last = copy.deepcopy(root[0]), copy.deepcopy(root[-1])
        first.find("STOP_SEQ").text = "3"
        last.find("STOP_SEQ").text = "4"
        root.remove(root[-1])
        root.append(first)
        root.append(last)
        bodies["route_stops"] = ET.tostring(root)
    cached = await service.transport.index()
    base = service.transport.direct(
        cached[1], JourneyQuery(origin="Lan", destination="Seymour")
    )[0]
    if not loop:
        alternative = copy.deepcopy(base[0])
        alternative["alight"] = {
            **cached[1]["stops"]["262"],
            **cached[1]["paths"][("1750", "outbound")][1],
            "distanceM": None,
            "occurrence": 1,
            "occurrenceCount": 1,
        }
        base.append(alternative)
    monkeypatch.setattr(service.transport, "direct", lambda *a: (base, [], []))
    calls = []

    async def query(resource, parameters, **kwargs):
        calls.append((resource, tuple(sorted(parameters.items()))))
        if resource == CITYBUS["route_stops"]:
            pairs = (
                [(4, "001042"), (5, "001084")]
                + ([(9, "001042")] if loop else [])
                + [(11, "001021")]
            )
            items = [
                {"route": "12", "dir": "O", "seq": seq, "stop": sid}
                for seq, sid in pairs
            ]
        elif resource == CITYBUS["stop"]:
            sid = parameters["stop_id"]
            en, tc, lat, lon = {
                "001042": ("Lan Kwai Fong", "蘭桂坊", 22.2815165, 114.1561392),
                "001084": ("Lyndhurst Terrace", "擺花街", 22.282, 114.155),
                "001021": ("Seymour Road", "西摩道", 22.2831597, 114.1478635),
            }[sid]
            items = [
                {
                    "data": {
                        "stop": sid,
                        "name_en": en,
                        "name_tc": tc,
                        "lat": str(lat),
                        "long": str(lon),
                    }
                }
            ]
        else:
            items = [
                {
                    "route": "12",
                    "stop": "001042",
                    "dir": "O",
                    "seq": seq,
                    "eta": datetime.fromtimestamp(
                        time.time() + seconds, timezone.utc
                    ).isoformat(),
                }
                for seq, seconds in ([(4, 600), (9, 120)] if loop else [(4, 120)])
            ]
        return {
            "data": {"items": items},
            "meta": {"nextOffset": None},
            "schema": {"transport": {"freshUntil": time.time() + 20}},
            "provenance": [{"stale": False}],
            "warnings": [],
        }

    monkeypatch.setattr(service.resources, "query", query)
    result = await service.transport.journey(
        JourneyQuery(origin="Lan", destination="Seymour", limit=1)
    )
    data = result["data"]
    candidate = data["items"][0]
    assert len(calls) == len(set(calls)) == data["coverage"]["sourceRequests"] == 5
    assert data["coverage"]["checked"] == 2
    assert data["coverage"]["failed"] == data["coverage"]["unchecked"] == 0
    if loop:
        assert candidate["operatorBoardSequence"] == 9
        assert candidate["board"]["occurrence"] == 2
        assert data["totalDepartureChoices"] == 2
    else:
        assert candidate["alightingAlternativeCount"] == 2
        assert data["totalDepartureChoices"] == 1


@pytest.mark.asyncio
async def test_budget_unchecked_and_other_operator_are_unknown_not_ineligible(
    service, monkeypatch
):
    cached = await service.transport.index()
    base = service.transport.direct(
        cached[1], JourneyQuery(origin="Lan", destination="Seymour")
    )[0][0]
    candidates = [copy.deepcopy(base) for _ in range(70)]
    candidates[-1]["route"]["operator"] = "DB"
    monkeypatch.setattr(service.transport, "direct", lambda *a: (candidates, [], []))

    async def citybus(candidate, remaining, cache):
        if remaining[0] <= 0:
            raise DomainError("TRANSPORT_LOOKUP_LIMIT", "bound", 503)
        remaining[0] -= 1
        raise DomainError("SOURCE_UNAVAILABLE", "source down", 502)

    monkeypatch.setattr(service.transport, "citybus", citybus)
    data = (
        await service.transport.journey(
            JourneyQuery(origin="Lan", destination="Seymour")
        )
    )["data"]
    assert data["coverage"]["candidate"] == 70
    assert data["coverage"]["checked"] == data["coverage"]["failed"] == 64
    assert data["coverage"]["unchecked"] == 6
    assert data["coverage"]["eligibilityUnknown"] == 70
    assert data["coverage"]["uncheckedReasons"]["operator_join_not_qualified"] == 1
    assert not data["coverage"]["complete"]


@pytest.mark.asyncio
@pytest.mark.parametrize("operator", ["KMB", "NLB"])
@pytest.mark.parametrize(
    "broken", [None, "stop_identity", "loop", "eta_identity", "truncated"]
)
async def test_new_operator_variants_preserve_ids_native_eta_and_complete_comparison(
    service, monkeypatch, operator, broken
):
    from datetime import datetime, timezone, timedelta

    cached = await service.transport.index()
    base = service.transport.direct(
        cached[1], JourneyQuery(origin="Lan", destination="Seymour")
    )[0][0]
    base["route"]["operator"] = operator
    monkeypatch.setattr(service.transport, "direct", lambda *a: ([base], [], []))
    calls = []
    ids = ["0000000000000001", "0000000000000002"]
    early = (datetime.now(timezone.utc) + timedelta(minutes=3)).isoformat()
    late = (datetime.now(timezone.utc) + timedelta(minutes=8)).isoformat()

    async def query(resource, parameters, filters=None, **kwargs):
        calls.append((resource, tuple(sorted(parameters.items()))))
        next_offset = None
        if resource == KMB["routes"]:
            assert filters == {"route": "12", "bound": "O"}
            items = [
                {"route": "12", "bound": "O", "service_type": s} for s in ["2", "7"]
            ]
        elif resource == KMB["path"]:
            assert parameters["service_type"] in {"2", "7"}
            items = [
                {
                    "route": "12",
                    "bound": "O",
                    "service_type": parameters["service_type"],
                    "seq": str(i + 1),
                    "stop": sid,
                }
                for i, sid in enumerate(ids)
            ]
            if broken == "loop":
                items.append({**items[0], "seq": "3"})
        elif resource == KMB["stop"]:
            sid = parameters["stop_id"]
            target = base["board"] if sid == ids[0] else base["alight"]
            items = [
                {
                    "data": {
                        "stop": (
                            "FFFFFFFFFFFFFFFF" if broken == "stop_identity" else sid
                        ),
                        "name_en": target["name"]["en"] + " (WT001)",
                        "name_tc": target["name"]["zhHant"] + " (WT001)",
                        "lat": str(target["latitude"]),
                        "long": str(target["longitude"]),
                    }
                }
            ]
        elif resource == KMB["eta"]:
            items = [
                {
                    "co": "CTB" if broken == "eta_identity" else "KMB",
                    "route": "12",
                    "dir": "O",
                    "service_type": int(parameters["service_type"]),
                    "seq": 1,
                    "eta": early if parameters["service_type"] == "7" else late,
                }
            ]
        elif resource == NLB["routes"]:
            assert filters == {"routeNo": "12"}
            items = [{"routeNo": "12", "routeId": i} for i in [12, 73]]
        elif resource == NLB["path"]:
            targets = [base["board"], base["alight"]]
            if parameters["routeId"] == "12":
                targets.reverse()
            items = [
                {
                    "stopId": 1 if t is base["board"] else 2,
                    "stopName_e": (
                        "different" if broken == "stop_identity" else t["name"]["en"]
                    ),
                    "stopName_c": (
                        "different"
                        if broken == "stop_identity"
                        else t["name"]["zhHant"]
                    ),
                    "latitude": str(t["latitude"]),
                    "longitude": str(t["longitude"]),
                }
                for t in targets
            ]
            if broken == "loop":
                items.append(items[0])
        elif resource == NLB["eta"]:
            if broken == "eta_identity":
                raise DomainError("STALE_TRANSPORT_DATA", "source expired", 503)
            items = [
                {
                    "estimatedArrivalTime": early,
                    "routeVariantName": "source variant",
                    "departed": 0,
                    "noGPS": 1,
                }
            ]
        else:
            raise AssertionError(resource)
        if broken == "truncated" and resource in {KMB["routes"], NLB["routes"]}:
            next_offset = 100
        return {
            "data": {"items": items},
            "meta": {"nextOffset": next_offset},
            "schema": {"transport": {"freshUntil": time.time() + 20}},
            "warnings": [],
            "provenance": [],
        }

    monkeypatch.setattr(service.resources, "query", query)
    result = await service.transport.journey(
        JourneyQuery(origin="Lan", destination="Seymour", limit=1)
    )
    data = result["data"]
    coverage = data["coverage"]
    assert coverage["sourceRequests"] <= 64
    assert coverage["candidate"] == coverage["checked"] + coverage["unchecked"]
    assert not data["departureComparison"]["globallyEarliest"]
    if broken:
        assert coverage["failed"] > 0
        assert not coverage["complete"]
        assert not any(c["arrivalStatus"] == "live" for c in data["items"])
    else:
        assert data["referenceCandidateCount"] == 1
        assert data["totalMatched"] == 1
        assert data["expandedCandidateCount"] == 2
        assert coverage["candidate"] == coverage["checked"] == 2
        assert coverage["complete"]
        assert data["items"][0]["earliestPredictedDeparture"] == early
        if operator == "KMB":
            assert data["items"][0]["operatorServiceType"] == "7"
            assert data["items"][0]["operatorBoardStopId"] == ids[0]
            assert len(calls) == len(set(calls)) == 7
            assert "shared-stop" in data["items"][0]["variantWarning"]
        else:
            assert data["items"][0]["operatorRouteId"] == 73
            assert coverage["verifiedNotServingOrder"] == 1
            assert data["items"][0]["arrivals"]["items"][0]["noGPS"] == 1
            assert (
                data["items"][0]["arrivals"]["predictionField"]
                == "estimatedArrivalTime"
            )


@pytest.mark.asyncio
@pytest.mark.parametrize("expired", [False, True])
async def test_empty_or_expired_eta_is_not_no_bus(service, monkeypatch, expired):
    cached = await service.transport.index()
    candidates = service.transport.direct(
        cached[1], JourneyQuery(origin="Lan", destination="Seymour")
    )[0]
    monkeypatch.setattr(service.transport, "direct", lambda *a: (candidates, [], []))

    async def citybus(candidate, remaining, cache):
        candidate.update(
            arrivalStatus="live",
            operatorEligibilityVerified=True,
            operatorBoardStopId="001042",
            operatorAlightStopId="001021",
            operatorBoardSequence=4,
            operatorAlightSequence=11,
            arrivalCheckedAt=time.time(),
            arrivals={
                "items": [],
                "transport": {"freshUntil": time.time() + (-1 if expired else 20)},
            },
        )

    monkeypatch.setattr(service.transport, "citybus", citybus)
    data = (
        await service.transport.journey(
            JourneyQuery(origin="Lan", destination="Seymour")
        )
    )["data"]
    assert data["departureComparison"]["earliestPredictedAt"] is None
    assert not data["currentServiceVerified"]
    if expired:
        assert data["coverage"]["failed"] == 1
        assert "arrivals" not in data["items"][0]
    else:
        assert data["items"][0]["predictionCoverage"]["emptyFeedDoesNotProveNoService"]


@pytest.mark.asyncio
async def test_stale_shared_read_cannot_be_reused_as_a_live_success(
    service, monkeypatch
):
    cached = await service.transport.index()
    base = service.transport.direct(
        cached[1], JourneyQuery(origin="Lan", destination="Seymour")
    )[0][0]
    candidates = [copy.deepcopy(base), copy.deepcopy(base)]
    monkeypatch.setattr(service.transport, "direct", lambda *a: (candidates, [], []))
    calls = []

    async def query(*args, **kwargs):
        calls.append(True)
        return {"schema": {}, "provenance": [{"stale": True}]}

    monkeypatch.setattr(service.resources, "query", query)
    data = (
        await service.transport.journey(
            JourneyQuery(origin="Lan", destination="Seymour")
        )
    )["data"]
    assert len(calls) == 1
    assert data["coverage"]["failed"] == 2
    assert all(c["arrivalError"]["code"] == "STALE_SOURCE" for c in data["items"])
    assert data["departureComparison"]["earliestPredictedAt"] is None
