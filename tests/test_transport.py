"""Live transport must validate semantic success and freshness before coverage."""

import json

import pytest

from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store


@pytest.fixture
def transport_service(tmp_path):
    service = Service(Store(str(tmp_path / "transport.sqlite3")))
    service.resources.catalogue.publish(
        [
            {
                "id": "mtr-data2-nexttrain-data",
                "title": "MTR",
                "provider": "MTR",
                "providerType": "independent_or_public_corporation",
                "sourceUrl": "https://data.gov.hk/en-data/dataset/mtr-data2-nexttrain-data",
                "catalogue": "DATA.GOV.HK",
            }
        ],
        [
            {
                "id": "mtr",
                "datasetId": "mtr-data2-nexttrain-data",
                "format": "JSON",
                "url": "https://rt.data.gov.hk/v1/transport/mtr/getSchedule.php",
                "sourceUrl": "https://data.gov.hk/en-data/dataset/mtr-data2-nexttrain-data",
                "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
                "catalogue": "DATA.GOV.HK",
                "isApi": True,
                "aliases": [],
            }
        ],
        {},
    )
    return service


@pytest.mark.asyncio
async def test_error_json_is_not_queryable(transport_service, monkeypatch):
    async def source(url, headers=None, **kwargs):
        return (
            json.dumps(
                {
                    "status": 0,
                    "message": "Please type the line-station.",
                    "error": {"errorCode": "NT-301"},
                }
            ).encode(),
            {},
            url,
            200,
        )

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", source)
    with pytest.raises(DomainError, match="SOURCE_RESPONSE_ERROR"):
        await transport_service.resources.query(
            "mtr", parameters={"line": "TWL", "sta": "CEN"}
        )
    check = transport_service.resources.catalogue.check("mtr")
    assert check["status"] != "queryable"


from datetime import datetime
from mcp_open_data_hk import transport

NOW = 1_800_000_000
STAMP = datetime.fromtimestamp(NOW, transport.HKT).isoformat()


def mtr_payload(stamp=STAMP, empty=False):
    return {
        "status": 1,
        "curr_time": stamp,
        "data": {
            "TWL-CEN": {
                "UP": (
                    []
                    if empty
                    else [{"time": stamp, "dest": "TSW", "plat": "1", "seq": "1"}]
                )
            }
        },
    }


@pytest.mark.asyncio
async def test_mtr_selection_request_flattening_cache_and_failure(
    transport_service, monkeypatch
):
    clock = [NOW]
    calls = []
    failure = [False]
    monkeypatch.setattr(transport.time, "time", lambda: clock[0])

    async def source(url, headers=None, **kwargs):
        calls.append(url)
        assert "line=TWL" in url and "sta=CEN" in url
        if failure[0]:
            raise DomainError("SOURCE_HTTP_ERROR", "Source down", 502)
        stamp = datetime.fromtimestamp(clock[0], transport.HKT).isoformat()
        return json.dumps(mtr_payload(stamp)).encode(), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", source)
    choice = await transport_service.resources.schema("mtr")
    assert choice["selectionRequired"] == "parameters" and choice["parameters"] == [
        "line",
        "sta",
    ]
    args = {"parameters": {"line": "TWL", "sta": "CEN"}}
    one = await transport_service.resources.query("mtr", **args)
    assert one["data"]["items"][0]["station"] == "CEN"
    assert one["schema"]["transport"]["freshnessBasis"] == "provider_timestamp"
    assert one["schema"]["cacheTTLSeconds"] == 10
    await transport_service.resources.query("mtr", **args)
    assert len(calls) == 1
    clock[0] += 1
    await transport_service.resources.query("mtr", require_fresh=True, **args)
    assert len(calls) == 2
    clock[0] += 11
    directory = transport_service.resources.catalogue.resources(
        "mtr-data2-nexttrain-data"
    )
    assert directory["items"][0]["validation"]["status"] == "stale"
    await transport_service.resources.query("mtr", **args)
    assert len(calls) == 3
    clock[0] += 11
    failure[0] = True
    with pytest.raises(DomainError, match="SOURCE_HTTP_ERROR"):
        await transport_service.resources.query("mtr", **args)
    assert transport_service.resources.catalogue.check("mtr")["status"] == "unavailable"


@pytest.mark.asyncio
async def test_stale_source_and_empty_arrivals(transport_service, monkeypatch):
    monkeypatch.setattr(transport.time, "time", lambda: NOW)
    payload = [mtr_payload(empty=True)]

    async def source(url, headers=None, **kwargs):
        return json.dumps(payload[0]).encode(), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", source)
    args = {"parameters": {"line": "TWL", "sta": "CEN"}, "require_fresh": True}
    result = await transport_service.resources.query("mtr", **args)
    assert result["data"]["items"] == []
    assert result["schema"]["transport"]["arrivalState"] == "no_arrivals"
    # Normal empty/nonempty changes do not become generic schema-drift failures.
    payload[0] = mtr_payload()
    assert (await transport_service.resources.query("mtr", **args))["meta"][
        "total"
    ] == 1
    payload[0] = mtr_payload("2000-01-01T00:00:00+08:00")
    with pytest.raises(DomainError, match="STALE_TRANSPORT_DATA"):
        await transport_service.resources.query("mtr", **args)


def test_provider_contracts_preserve_schedule_and_advisories():
    cases = [
        (
            "mtr-lrnt_data-light-rail-nexttrain-data",
            "https://rt.data.gov.hk/v1/transport/mtr/lrt/getSchedule?station_id=",
            {"station_id": "001"},
            {
                "status": 1,
                "system_time": STAMP,
                "platform_list": [
                    {
                        "platform_id": 2,
                        "route_list": [{"time_en": "5 mins", "route_no": "507"}],
                    }
                ],
            },
        ),
        (
            "mtr-mtr_bus-mtr-bus-eta-data",
            "https://rt.data.gov.hk/v1/transport/mtr/bus/getSchedule",
            {"routeName": "K12"},
            {
                "status": "0",
                "routeName": "K12",
                "routeStatusTime": STAMP,
                "footerRemarks": "Testing advisory",
                "busStop": [
                    {
                        "busStopId": "K12-A010",
                        "isSuspended": "0",
                        "bus": [{"isScheduled": "1", "arrivalTimeInSecond": "300"}],
                    }
                ],
            },
        ),
        (
            "ctb-eta-transport-realtime-eta",
            "https://rt.data.gov.hk/v1/transport/citybus-nwfb/eta/ctb",
            {"stop_id": "001145", "route": "11"},
            {
                "type": "ETA",
                "generated_timestamp": STAMP,
                "data": [{"eta": STAMP, "rmk_en": "Scheduled Bus"}],
            },
        ),
        (
            "hk-td-tis_21-etakmb",
            "https://data.etabus.gov.hk/v1/transport/kmb/route-eta/{route}/{service_type}",
            {"route": "1", "service_type": "1"},
            {
                "generated_timestamp": STAMP,
                "data": [{"eta": None, "rmk_en": "No service"}],
            },
        ),
        (
            "hk-td-sm_7-real-time-arrival-data-of-gmb",
            "https://data.etagmb.gov.hk/eta/route-stop/{route_id}/{route_seq}/{stop_seq}",
            {"route_id": "2006408", "route_seq": "1", "stop_seq": "1"},
            {
                "generated_timestamp": STAMP,
                "data": {
                    "enabled": True,
                    "eta": [{"timestamp": STAMP, "diff": 5, "remarks_en": "Scheduled"}],
                },
            },
        ),
        (
            "nlb-bus-nlb-bus-service-v2",
            "https://rt.data.gov.hk/v2/transport/nlb/stop.php?action=estimatedArrivals&routeId={routeId}&stopId={stopId}&language={languageCode}",
            {"routeId": "1", "stopId": "1", "languageCode": "en"},
            {
                "estimatedArrivals": [
                    {"estimatedArrivalTime": STAMP, "generateTime": STAMP, "noGPS": "1"}
                ]
            },
        ),
        (
            "sunferry-eta-eta",
            "https://www.sunferry.com.hk/eta/?route=<routecode>",
            {"routecode": "CECC"},
            {
                "generated_timestamp": STAMP,
                "data": [{"eta": "14:15", "routecode": "CECC"}],
            },
        ),
        (
            "hkkf-hkkfdata-hkkf-eta-data",
            "https://www.hkkfeta.com/opendata/eta/",
            {"route_id": "3", "direction": "inbound"},
            {
                "generated_timestamp": STAMP,
                "data": [{"ETA": STAMP, "direction": "inbound"}],
            },
        ),
    ]
    for dataset, url, parameters, data in cases:
        p = transport.profile({"datasetId": dataset, "url": url})
        resolved, payload = transport.request(p, parameters)
        raw, meta = transport.validate(
            json.dumps(data).encode(), p, parameters, {}, NOW
        )
        assert json.loads(raw) and meta["transport"]["sourceTimestamp"] == STAMP
        assert meta["transport"]["cacheTTLSeconds"] <= 20
        if p.kind == "mtrbus":
            assert payload["routeName"] == "K12" and p.method == "POST"
            assert meta["transport"]["advisories"] == ["Testing advisory"]
            assert json.loads(raw)[0]["isScheduled"] == "1"
        if p.operator == "Citybus":
            assert "/v2/transport/citybus/eta/CTB/001145/11" in resolved
        if p.operator == "Hong Kong & Kowloon Ferry":
            assert resolved.endswith("/eta/3/inbound")


def test_reject_errors_bad_timestamps_and_unsafe_parameters():
    p = transport.profile(
        {
            "datasetId": "mtr-data2-nexttrain-data",
            "url": "https://rt.data.gov.hk/v1/transport/mtr/getSchedule.php",
        }
    )
    for params in [
        {},
        {"line": "TWL", "sta": "http://127.0.0.1"},
        {"line": "TWL", "sta": "CEN", "url": "private"},
    ]:
        with pytest.raises(DomainError):
            transport.request(p, params)
    for body in [
        {"status": 0, "message": "error"},
        {"status": 1, "curr_time": STAMP, "data": {}},
        mtr_payload("2099-01-01T00:00:00+08:00"),
    ]:
        with pytest.raises(DomainError):
            transport.validate(
                json.dumps(body).encode(), p, {"line": "TWL", "sta": "CEN"}, {}, NOW
            )


@pytest.mark.asyncio
async def test_legacy_false_success_label_is_invalidated(transport_service):
    store = transport_service.resources.catalogue
    with store.store.connect() as db:
        db.execute("DELETE FROM resource_policies WHERE id='mtr'")
        db.execute(
            "INSERT OR REPLACE INTO resource_checks(id,status,validated,rows) VALUES ('mtr','queryable',?,1)",
            (NOW,),
        )
    result = store.resources("mtr-data2-nexttrain-data")["items"][0]
    assert result["validation"]["status"] == "needs_selection"
    assert result["validation"]["lastValidatedAt"] is None
    assert result["transport"]["operation"] == "arrivals"


@pytest.mark.asyncio
async def test_mtr_http_mcp_parity_and_no_store(transport_service, monkeypatch):
    from fastapi.testclient import TestClient
    from fastmcp import Client
    from mcp_open_data_hk.api import create_app

    monkeypatch.setattr(transport.time, "time", lambda: NOW)

    async def source(url, headers=None, **kwargs):
        return json.dumps(mtr_payload()).encode(), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", source)
    app = create_app(transport_service)
    params = {"line": "TWL", "sta": "CEN"}
    with TestClient(app) as http:
        response = http.post("/api/v1/resources/mtr/query", json={"parameters": params})
        assert response.status_code == 200
        assert response.headers["cache-control"] == "no-store"
        rest = response.json()
        assert http.get("/api/v1/resources").headers["cache-control"] == "no-store"
    async with Client(app.state.mcp) as mcp:
        reply = await mcp.call_tool(
            "hk_resource_query", {"resourceId": "mtr", "parameters": params}
        )
        assert reply.data["data"] == rest["data"]
        assert reply.data["schema"]["transport"] == rest["schema"]["transport"]


def test_old_records_and_provider_error_never_become_fresh():
    p = transport.profile(
        {
            "datasetId": "hk-td-tis_21-etakmb",
            "url": "https://data.etabus.gov.hk/v1/transport/kmb/route-eta/{route}/{service_type}",
        }
    )
    for data in [
        {
            "generated_timestamp": STAMP,
            "data": [{"eta": STAMP, "data_timestamp": "2000-01-01T00:00:00+08:00"}],
        },
        {"generated_timestamp": STAMP, "data": [{"eta": 42}]},
        {"generated_timestamp": STAMP, "message": "Failure"},
    ]:
        with pytest.raises(DomainError):
            transport.validate(json.dumps(data).encode(), p, {}, {}, NOW)
    body, meta = transport.validate(
        json.dumps({"generated_timestamp": STAMP, "data": []}).encode(), p, {}, {}, NOW
    )
    assert json.loads(body) == [] and meta["transport"]["arrivalState"] == "no_arrivals"


def test_transport_post_redirect_is_rejected(monkeypatch):
    from mcp_open_data_hk import resource_fetch

    sent = []

    class Reply:
        status = 307

        def getheaders(self):
            return [("Location", "https://example.com/other")]

    class Connection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            sent.append((args, kwargs))

        def getresponse(self):
            return Reply()

        def close(self):
            pass

    monkeypatch.setattr(resource_fetch, "PinnedHTTPS", Connection)
    with pytest.raises(DomainError, match="UNSAFE_SOURCE"):
        resource_fetch.fetch_sync(
            "https://rt.data.gov.hk/v1/transport/mtr/bus/getSchedule",
            payload=b'{"routeName":"K12"}',
        )
    assert sent[0][0][0] == "POST"
    assert sent[0][1]["body"] == b'{"routeName":"K12"}'
    assert len(sent) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "dataset,operator,code",
    [
        ("ff-fortune-schedule2", "Fortune Ferry", "NPKT"),
        ("ff-watertaxi-schedule2", "Water Taxi", "WATERTAXI"),
    ],
)
async def test_ferry_failure_survives_parameter_discovery(
    transport_service, monkeypatch, dataset, operator, code
):
    catalogue = transport_service.resources.catalogue
    resource = catalogue.resource("mtr")
    resource.pop("transport")
    resource.update(
        id="ferry",
        datasetId=dataset,
        url="https://www.hongkongwatertaxi.com.hk/eta/?route={route_code}",
    )
    definition = catalogue.dataset("mtr-data2-nexttrain-data")
    definition.update(id=dataset, title=operator)
    catalogue.publish([definition], [resource], {})
    seen = []

    async def missing(url, headers=None, **kwargs):
        seen.append(url)
        raise DomainError("SOURCE_NOT_FOUND", "Source returned HTTP 404", 502)

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", missing)
    with pytest.raises(DomainError, match="SOURCE_NOT_FOUND"):
        await transport_service.resources.query(
            "ferry", parameters={"route_code": code}
        )
    previous = catalogue.check("ferry")
    schema = await transport_service.resources.schema("ferry")
    assert schema["selectionRequired"] == "parameters"
    assert schema["transport"]["operator"] == operator
    assert schema["transport"]["parameterExamples"] == {"route_code": code}
    assert catalogue.check("ferry") == previous
    assert previous["status"] == "unavailable" and not previous["validated"]
    assert seen == ["https://www.hongkongwatertaxi.com.hk/eta/?route=" + code]

    # The current operator site is HTML. A soft-404/maintenance page must also
    # fail, even if it changes to HTTP 200. No timetable/empty-list fallback.
    async def maintenance(url, headers=None, **kwargs):
        return b"<html><title>Page not found</title></html>", {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", maintenance)
    with pytest.raises(DomainError, match="SOURCE_RESPONSE_ERROR"):
        await transport_service.resources.query(
            "ferry", parameters={"route_code": code}
        )
    assert catalogue.check("ferry")["status"] == "unavailable"


def test_upstream_404_has_distinct_receipt(monkeypatch):
    from mcp_open_data_hk import resource_fetch

    class Reply:
        status = 404

        def getheaders(self):
            return [("content-type", "text/html")]

    class Connection:
        def __init__(self, *args, **kwargs):
            pass

        def request(self, *args, **kwargs):
            pass

        def getresponse(self):
            return Reply()

        def close(self):
            pass

    monkeypatch.setattr(resource_fetch, "PinnedHTTPS", Connection)
    with pytest.raises(DomainError, match="SOURCE_NOT_FOUND: Source returned HTTP 404"):
        resource_fetch.fetch_sync(
            "https://www.hongkongwatertaxi.com.hk/eta/?route=NPKT"
        )


@pytest.mark.asyncio
async def test_arrival_304_cannot_refresh_old_payload(transport_service, monkeypatch):
    clock = [NOW]
    not_modified = [False]
    monkeypatch.setattr(transport.time, "time", lambda: clock[0])

    async def source(url, headers=None, **kwargs):
        if not_modified[0]:
            return b"", {}, url, 304
        return json.dumps(mtr_payload()).encode(), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", source)
    args = {"parameters": {"line": "TWL", "sta": "CEN"}}
    await transport_service.resources.query("mtr", **args)
    clock[0] += 11
    not_modified[0] = True
    with pytest.raises(DomainError, match="SOURCE_RESPONSE_ERROR"):
        await transport_service.resources.query("mtr", **args)


@pytest.mark.asyncio
async def test_arrival_selectors_are_not_silently_ignored(transport_service):
    with pytest.raises(DomainError, match="INVALID_QUERY"):
        await transport_service.resources.query(
            "mtr", record_path="UP", parameters={"line": "TWL", "sta": "CEN"}
        )


@pytest.mark.parametrize(
    "route,advisory,code",
    [
        ("K12", "Arrival time temporarily not available", "SOURCE_UNAVAILABLE"),
        ("wrong", "Arrival time temporarily not available", "SOURCE_RESPONSE_ERROR"),
        ("K12", "", "SOURCE_RESPONSE_ERROR"),
    ],
)
def test_mtr_bus_explicit_outage_is_not_empty_arrivals(route, advisory, code):
    from mcp_open_data_hk import transport

    p = transport.profile(
        {
            "datasetId": "mtr-mtr_bus-mtr-bus-eta-data",
            "url": "https://rt.data.gov.hk/v1/transport/mtr/bus/getSchedule",
        }
    )
    body = json.dumps(
        {
            "routeName": route,
            "busStop": [],
            "status": "0",
            "routeStatusRemarkTitle": advisory,
            "routeStatusTime": "2026/10/18 23:16",
        }
    ).encode()
    with pytest.raises(DomainError, match=code) as error:
        transport.validate(body, p, {"routeName": "K12"}, {})
    if code == "SOURCE_UNAVAILABLE":
        assert advisory in str(error.value)
