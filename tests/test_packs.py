import json
import time
import traceback
from html.parser import HTMLParser
from pathlib import Path

import pytest
import httpx
from fastapi.testclient import TestClient
from fastmcp import Client

from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.contracts import DomainError, RestaurantQuery
from mcp_open_data_hk.ingest import read_features, refresh
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.sources import (
    district_id,
    parse_addresses,
    parse_population,
    parse_restaurant,
)
from mcp_open_data_hk.storage import Store


def fixture(name):
    return json.loads(
        (Path(__file__).parent / "fixtures" / (name + ".json")).read_text()
    )


@pytest.fixture
def service(tmp_path):
    store = Store(str(tmp_path / "data.sqlite3"))
    rows = [parse_restaurant(f) for f in fixture("restaurants")["features"]]
    store.publish("restaurants", rows, None)
    store.publish(
        "population",
        [parse_population(f) for f in fixture("population")["features"]],
        None,
    )
    return Service(store)


def test_population_units_and_reference_period():
    row = parse_population(fixture("population")["features"][0])
    assert row["population"] == 232200
    assert row["areaKm2"] == 12.55
    assert row["populationDensity"] == 18510
    assert row["referencePeriod"] == 2024


def test_api_docs_assets_work_with_the_actual_security_policy(service):
    class Assets(HTMLParser):
        def __init__(self):
            super().__init__()
            self.urls = []
            self.inline_scripts = 0
            self.metadata = []

        def handle_starttag(self, tag, attrs):
            attrs = dict(attrs)
            if tag == "script":
                if "src" in attrs:
                    self.urls.append(attrs["src"])
                else:
                    self.inline_scripts += 1
            if tag == "link":
                if attrs.get("rel") in {"canonical", "alternate"}:
                    self.metadata.append(attrs["href"])
                else:
                    self.urls.append(attrs["href"])

    with TestClient(create_app(service)) as client:
        response = client.get("/docs")
        assert response.status_code == 200
        assert "script-src 'self'" in response.headers["content-security-policy"]
        assert (
            "img-src 'self' data: https://hk.app/badges/;"
            in response.headers["content-security-policy"]
        )
        assets = Assets()
        assets.feed(response.text)
        assert assets.urls
        assert assets.inline_scripts == 0
        assert set(assets.metadata) == {
            "https://mcp.hk/docs",
            "https://mcp.hk/docs?lang=en",
            "https://mcp.hk/docs?lang=zh-Hant",
        }
        for url in assets.urls:
            assert url.startswith("/assets/")
            asset = client.get(url)
            assert asset.status_code == 200
            assert len(asset.content) > 0
        assert "/openapi.json" in client.get("/assets/api-docs.js").text
        assert "/api/v1/districts" in client.get("/openapi.json").json()["paths"]
        assert (
            client.get("/redoc", follow_redirects=False).headers["location"] == "/docs"
        )


def test_als_bilingual_coordinates_not_grid_values():
    row = parse_addresses(fixture("als"))[0]
    assert row["latitude"] == 22.28046
    assert row["longitude"] == 114.16537
    assert row["name"]["zhHant"] == "政府總部"
    assert row["districtId"] == "central-western"
    assert len(row["id"]) == 19


def test_source_specific_licensing_district_aliases():
    assert district_id("Yau Tsim") == "yau-tsim-mong"
    assert district_id("Mong Kok") == "yau-tsim-mong"
    assert district_id("Some shop in Mong Kok") is None


def test_source_budget_is_persisted(service):
    service.store.consume_budget("budget-test", 1)
    with pytest.raises(DomainError, match="budget exhausted"):
        Store(service.store.path).consume_budget("budget-test", 1)


def test_body_cap_and_rate_limit(service):
    with TestClient(create_app(service)) as client:
        assert client.post("/mcp", content=b"x" * 65537).status_code == 413
        assert (
            client.post("/mcp", content=iter([b"x" * 40000, b"x" * 40000])).status_code
            == 413
        )
        for _ in range(60):
            assert client.get("/api/v1/status").status_code == 200
        limited = client.get("/api/v1/status")
        assert limited.status_code == 429
        assert "Retry-After" in limited.headers


def test_radius_summary_is_not_a_page_count(service):
    q = RestaurantQuery(
        lat=22.283, lon=114.156, radiusM=500, limit=1, includeSummary=True
    )
    result = service.restaurants(q)
    assert len(result["data"]["items"]) == 1
    assert result["data"]["summary"]["totalMatched"] == 2
    assert sum(g["count"] for g in result["data"]["summary"]["byLicenceType"]) == 2
    next_page = service.restaurants(
        q.model_copy(update={"cursor": result["meta"]["nextCursor"]})
    )
    assert next_page["data"]["summary"] == result["data"]["summary"]
    assert next_page["data"]["items"][0]["id"] != result["data"]["items"][0]["id"]


def test_cursor_retains_generation_and_validates_filters(service):
    q = RestaurantQuery(limit=1)
    first = service.restaurants(q)
    old, rows = service.store.snapshot("restaurants")
    rows[0]["name"]["en"] = "Updated source name"
    service.store.publish("restaurants", rows, old["id"])
    page = service.restaurants(
        q.model_copy(update={"cursor": first["meta"]["nextCursor"]})
    )
    assert page["meta"]["snapshotIds"] == first["meta"]["snapshotIds"]
    with pytest.raises(DomainError, match="Cursor does not match"):
        service.restaurants(
            RestaurantQuery(limit=2, cursor=first["meta"]["nextCursor"])
        )


def test_failed_import_and_stale_data_retain_last_snapshot(service):
    sid = service.store.active("restaurants")
    with pytest.raises(DomainError):
        service.store.publish("restaurants", [], sid)
    assert service.store.active("restaurants") == sid
    with service.store.connect() as db:
        db.execute(
            "UPDATE snapshots SET checked=? WHERE id=?", (time.time() - 200000, sid)
        )
    assert (
        service.restaurants(RestaurantQuery())["warnings"][0]["code"] == "STALE_SOURCE"
    )
    with pytest.raises(DomainError, match="Fresh data is required"):
        service.restaurants(RestaurantQuery(requireFresh=True))


def test_unchanged_check_preserves_retrieval_time(service):
    old, rows = service.store.snapshot("population")
    assert service.store.publish("population", rows, old["id"]) == old["id"]
    new, _ = service.store.snapshot("population")
    assert new["retrieved"] == old["retrieved"]
    assert new["checked"] >= old["checked"]


def test_concurrent_publication_is_rejected(service):
    _, rows = service.store.snapshot("restaurants")
    with pytest.raises(DomainError, match="Another import published first"):
        service.store.publish("restaurants", rows, None)


def test_missing_coordinates_have_explicit_wider_coverage(service):
    old, rows = service.store.snapshot("restaurants")
    rows.append({**rows[0], "id": "unlocated", "latitude": None, "longitude": None})
    service.store.publish("restaurants", rows, old["id"])
    result = service.restaurants(
        RestaurantQuery(lat=22.283, lon=114.156, radiusM=500, includeSummary=True)
    )
    assert result["data"]["summary"]["totalMatched"] == 2
    assert result["data"]["summary"]["spatialCoverage"] == {
        "scope": "nonspatial_filters",
        "locatedCount": 2,
        "unlocatedCount": 1,
    }
    assert service.restaurants(RestaurantQuery())["meta"]["total"] == 3


def test_http_validation_and_population_year(service):
    with TestClient(create_app(service)) as client:
        assert client.get("/api/v1/restaurants?lat=22.3").status_code == 400
        assert client.get("/api/v1/restaurants?radiusM=300").status_code == 400
        assert client.get("/api/v1/restaurants?limit=101").status_code == 400
        assert client.get("/api/v1/restaurants?cursor=not-valid").status_code == 400
        assert (
            client.get("/api/v1/restaurants?sourceUrl=https://example.com").status_code
            == 400
        )
        result = client.get("/api/v1/districts/central-western/statistics").json()
        assert result["data"]["population"] == 232200
        assert result["provenance"][0]["referencePeriod"] == 2024
        assert len(client.get("/api/v1/districts").json()["items"]) == 18
        assert (
            client.get(
                "/api/v1/districts/central-western/statistics?year=2020"
            ).status_code
            == 404
        )
        assert client.get("/readyz").status_code == 200
        assert (
            client.get(
                "/mcp", headers={"Origin": "https://untrusted.example"}
            ).status_code
            == 403
        )
        assert (
            client.get("/healthz", headers={"Host": "evil.example"}).status_code == 403
        )


@pytest.mark.asyncio
async def test_mcp_http_parity_and_preserved_tools(service):
    app = create_app(service)
    async with Client(app.state.mcp) as client:
        tools = await client.list_tools()
        assert len(tools) == 39
        assert {
            "hk_sfc_status",
            "hk_hkex_status",
            "hk_hkex_archive_status",
            "hk_racing_status",
            "hk_transport_stop_search",
            "hk_transport_stop_routes",
            "hk_transport_journey",
        } <= {t.name for t in tools}
        assert {"list_datasets", "get_dataset_details", "search_datasets"} <= {
            t.name for t in tools
        }
        result = await client.call_tool(
            "hk_restaurant_search", {"includeSummary": True}
        )
        payload = result.data
        if hasattr(payload, "model_dump"):
            payload = payload.model_dump()
        expected = service.restaurants(RestaurantQuery(includeSummary=True))
        assert payload["data"] == expected["data"]
        assert payload["meta"]["snapshotIds"] == expected["meta"]["snapshotIds"]


@pytest.mark.asyncio
async def test_address_cache_reuses_source_timestamp(service, monkeypatch):
    calls = []

    async def read(url, params):
        calls.append(url)
        return fixture("als")

    monkeypatch.setattr("mcp_open_data_hk.services.request_json", read)
    a = await service.addresses("Central Government Offices")
    b = await service.addresses("Central Government Offices")
    assert len(calls) == 1
    assert a["data"] == b["data"]
    assert a["provenance"] == b["provenance"]
    assert (await service.addresses(a["data"]["items"][0]["id"], 1, geo=True))["data"][
        "id"
    ]


@pytest.mark.asyncio
async def test_incomplete_feature_page_is_rejected(monkeypatch):
    async def read(url, params):
        return (
            {"objectIds": [1, 2]}
            if params.get("returnIdsOnly")
            else {"features": [{"attributes": {"OBJECTID": 1}}]}
        )

    monkeypatch.setattr("mcp_open_data_hk.ingest.request_json", read)
    with pytest.raises(DomainError, match="incomplete"):
        await read_features("https://portal.csdi.gov.hk/layer")


@pytest.mark.asyncio
async def test_restaurant_import_uses_one_atomic_official_response(
    service, monkeypatch
):
    from mcp_open_data_hk import ingest
    from mcp_open_data_hk.sources import RESTAURANTS_SNAPSHOT

    features = [
        {"type": "Feature", "properties": f["attributes"]}
        for f in fixture("restaurants")["features"]
    ]
    calls = []

    async def download(url, **kwargs):
        calls.append((url, kwargs))
        return (
            json.dumps({"type": "FeatureCollection", "features": features}).encode(),
            {},
            url,
            200,
        )

    async def mixed_replicas(*args, **kwargs):
        raise AssertionError("Paginated restaurant replicas must not be mixed")

    monkeypatch.setattr(ingest, "fetch", download)
    monkeypatch.setattr(ingest, "read_features", mixed_replicas)
    result = await refresh(service.store, "restaurants")
    assert result["records"] == len(features)
    assert calls == [(RESTAURANTS_SNAPSHOT, {"maximum": 32_000_000})]
    source = next(
        s for s in service.status()["sources"] if s["sourceId"] == "restaurants"
    )
    assert source["sourceResponseUrl"] == RESTAURANTS_SNAPSHOT
    assert source["refreshHealth"]["state"] == "healthy"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "payload",
    [
        {"type": "FeatureCollection", "features": []},
        {"type": "FeatureCollection", "features": [{"type": "Feature"}]},
        {"type": "FeatureCollection", "features": [], "exceededTransferLimit": True},
        {"type": "FeatureCollection", "features": [], "error": {"code": 500}},
        {"type": "Feature", "features": []},
    ],
)
async def test_bad_atomic_restaurant_response_retains_snapshot(
    service, monkeypatch, payload
):
    from mcp_open_data_hk import ingest

    old = service.store.active("restaurants")

    async def download(url, **kwargs):
        return json.dumps(payload).encode(), {}, url, 200

    monkeypatch.setattr(ingest, "fetch", download)
    with pytest.raises(DomainError):
        await refresh(service.store, "restaurants")
    assert service.store.active("restaurants") == old


@pytest.mark.asyncio
async def test_schema_failure_persists_receipt_and_keeps_active(service, monkeypatch):
    old = service.store.active("population")

    async def bad(layer):
        return [{"attributes": {"DC_ENG": "changed schema"}}]

    monkeypatch.setattr("mcp_open_data_hk.ingest.read_features", bad)
    with pytest.raises(DomainError):
        await refresh(service.store, "population")
    assert service.store.active("population") == old
    assert service.status()["sources"][2]["lastError"] == "SOURCE_SCHEMA_CHANGED"


@pytest.mark.asyncio
@pytest.mark.parametrize("language", ["en", "tc", "sc"])
async def test_catalogue_legacy_facets_are_additive(monkeypatch, language):
    from mcp_open_data_hk import server

    async def read(url, params):
        assert url == server.BASE_URLS[language] + "/package_search"
        assert json.loads(params["facet.field"]) == ["groups", "res_format"]
        assert params["facet.limit"] == 10
        if params["q"] == "error":
            return {"success": False}
        if params["q"] == "zero":
            return {"success": True, "result": {"results": [], "count": 0}}
        return {
            "success": True,
            "result": {
                "results": [{"id": "weather"}],
                "count": 10,
                "search_facets": {
                    "groups": {"items": [{"name": "weather", "count": 10}]}
                },
            },
        }

    monkeypatch.setattr(server, "make_api_request", read)
    assert await server.search_datasets_with_facets("weather", language) == {
        "count": 10,
        "results": [{"id": "weather"}],
        "search_facets": {"groups": {"items": [{"name": "weather", "count": 10}]}},
        "has_more": True,
    }
    assert await server.search_datasets_with_facets("zero", language) == {
        "count": 0,
        "results": [],
        "search_facets": {},
        "has_more": False,
    }
    with pytest.raises(DomainError, match="CATALOGUE_ERROR"):
        await server.search_datasets_with_facets("error", language)


@pytest.mark.asyncio
async def test_source_failure_traceback_redacts_address_query(monkeypatch):
    from mcp_open_data_hk import http

    original = httpx.AsyncClient

    def unavailable(request):
        return httpx.Response(503)

    def client(**kwargs):
        return original(transport=httpx.MockTransport(unavailable), **kwargs)

    monkeypatch.setattr(httpx, "AsyncClient", client)
    with pytest.raises(DomainError) as error:
        await http.request_json(
            "https://www.als.gov.hk/lookup", {"q": "private-address-example"}
        )
    rendered = "".join(traceback.format_exception(error.value))
    assert "UPSTREAM_UNAVAILABLE" in rendered
    assert "private-address-example" not in rendered
    assert error.value.__suppress_context__


def test_introductory_http_guide_matches_the_source_linked_statistics_contract(service):
    from mcp_open_data_hk.discovery import content

    with TestClient(create_app(service)) as client:
        response = client.get("/api/v1/districts/central-western/statistics")
        assert response.status_code == 200
        payload = response.json()
        assert isinstance(payload["data"]["population"], int)
        assert isinstance(payload["data"]["referencePeriod"], int)
        assert payload["provenance"][0]["sourceUrl"].startswith("https://")
    for locale in ["en", "zh-Hant"]:
        first = content()["pages"]["/guides/hong-kong-open-data-api"][locale][
            "sections"
        ][0]
        assert "/api/v1/districts/central-western/statistics" in first["code"]
        assert "data.referencePeriod" in first["paragraphs"][0]
        assert "data.items" not in first["paragraphs"][0]


def test_district_statistics_wire_schema_and_validation(service):
    from jsonschema import validate

    headers = {"Accept": "application/json, text/event-stream"}

    def rpc(client, method, params):
        response = client.post(
            "/mcp",
            json={"jsonrpc": "2.0", "id": 1, "method": method, "params": params},
            headers=headers,
        )
        assert response.status_code == 200
        return json.loads(
            next(
                line[6:]
                for line in response.text.splitlines()
                if line.startswith("data: ")
            )
        )["result"]

    with TestClient(create_app(service)) as client:
        tools = rpc(client, "tools/list", {})["tools"]
        district = next(t for t in tools if t["name"] == "hk_district_statistics")
        assert (
            "hk_district_list"
            in district["inputSchema"]["properties"]["districtId"]["description"]
        )
        row = service.store.snapshot("population")[1][0]
        result = rpc(
            client,
            "tools/call",
            {
                "name": district["name"],
                "arguments": {"districtId": row["districtId"]},
            },
        )
        assert result["isError"] is False
        structured = result["structuredContent"]
        validate(structured, district["outputSchema"])
        assert json.loads(result["content"][0]["text"]) == structured
        assert structured["data"] == row
        for name, args, expected in [
            (district["name"], {}, "districtId: required"),
            (
                district["name"],
                {"districtId": [], "year": "private text"},
                "districtId: invalid",
            ),
            ("hk_transport_journey", {}, "Supply both endpoints"),
            ("hk_resource_query", {}, "resourceId: required"),
        ]:
            error = rpc(client, "tools/call", {"name": name, "arguments": args})
            assert error["isError"] is True
            assert error["content"][0]["text"].startswith("INVALID_QUERY: ")
            assert expected in error["content"][0]["text"]
            assert "private text" not in error["content"][0]["text"]


@pytest.mark.asyncio
async def test_full_public_tool_inventory_and_legacy_category_wire(
    service, monkeypatch
):
    from jsonschema import Draft202012Validator
    from mcp_open_data_hk import server

    monkeypatch.setenv("MCP_HK_CURATED_ORIGIN", "https://curated.example")
    monkeypatch.setenv("MCP_HK_CURATED_TOKEN", "x" * 32)
    monkeypatch.setenv("MCP_HK_HKEX_DAILY_ENABLED", "true")
    monkeypatch.setenv("MCP_HK_WEBB_SDI_ENABLED", "true")
    expected = set(
        json.loads(
            (
                Path(__file__).parents[1] / "deploy/cloudflare/mcp-tool-names.json"
            ).read_text()
        )
    ) - {"hk_racing_profile_observation", "hk_racing_profile_history"}

    async def group_list(url, params):
        assert url.endswith("/group_list")
        rows = (
            [{"name": "weather", "title": "Weather"}]
            if params["all_fields"] == "true"
            else ["weather"]
        )
        return {"success": True, "result": rows[: int(params.get("limit", 1))]}

    monkeypatch.setattr(server, "make_api_request", group_list)
    service = Service(service.store)
    async with Client(server.create_server(service)) as client:
        tools = {tool.name: tool for tool in await client.list_tools()}
        assert set(tools) == expected
        for tool in tools.values():
            assert (
                tool.annotations.readOnlyHint and not tool.annotations.destructiveHint
            )
            shape = tool.outputSchema.get("allOf", [tool.outputSchema])[0]
            assert shape.get("properties"), tool.name
            Draft202012Validator.check_schema(tool.outputSchema)
            Draft202012Validator.check_schema(tool.inputSchema)
            for name, field in tool.inputSchema.get("properties", {}).items():
                assert field.get("description"), (tool.name, name)
        assert (
            tools["hk_resource_query"].inputSchema["properties"]["limit"]["maximum"]
            == 100
        )
        assert (
            tools["hk_transport_journey"].inputSchema["properties"]["radiusM"][
                "maximum"
            ]
            == 2000
        )
        for fields, limit in ((False, 1), (True, 1), (False, 0), (True, 0)):
            result = await client.call_tool(
                "list_categories", {"all_fields": fields, "limit": limit}
            )
            shape = result.structured_content
            assert len(shape["result"]) == limit
            if limit:
                assert json.loads(result.content[0].text) == shape["result"]
                assert isinstance(shape["result"][0], dict if fields else str)
            else:
                assert result.content == []
            Draft202012Validator(tools["list_categories"].outputSchema).validate(shape)


@pytest.mark.asyncio
async def test_als_search_geoaddress_handoff_preserves_optional_nulls(
    service, monkeypatch
):
    exact = fixture("als-geo")

    async def read(url, params):
        if url.endswith("/galookup"):
            assert (
                params["ga"]
                == exact["SuggestedAddress"][0]["Address"]["PremisesAddress"][
                    "GeoAddress"
                ]
            )
            return exact
        assert url.endswith("/lookup")
        return fixture("als")

    monkeypatch.setattr("mcp_open_data_hk.services.request_json", read)
    app = create_app(service)
    async with Client(app.state.mcp) as mcp:
        match = await mcp.call_tool(
            "hk_address_search", {"q": "Central Government Offices"}
        )
        identifier = match.structured_content["data"]["items"][0]["id"]
        detail = await mcp.call_tool("hk_address_get", {"geoAddress": identifier})
        data = detail.structured_content["data"]
    with TestClient(app) as http:
        result = http.get("/api/v1/addresses/" + identifier)
    assert result.status_code == 200 and result.json()["data"] == data
    assert data["id"] == identifier
    assert data["score"] is None and data["districtId"] == "central-western"
    assert data["latitude"] and data["longitude"]


@pytest.mark.asyncio
async def test_als_malformed_optional_object_has_a_source_error(service, monkeypatch):
    exact = fixture("als-geo")
    exact["SuggestedAddress"][0]["ValidationInformation"] = "unexpected"

    async def read(*args):
        return exact

    monkeypatch.setattr("mcp_open_data_hk.services.request_json", read)
    async with Client(create_app(service).state.mcp) as mcp:
        result = await mcp.call_tool(
            "hk_address_get",
            {"geoAddress": "3508215732T20110704"},
            raise_on_error=False,
        )
    assert result.is_error and result.content[0].text.startswith(
        "SOURCE_SCHEMA_CHANGED:"
    )


@pytest.mark.asyncio
async def test_legacy_dataset_default_and_pagination_are_bounded(monkeypatch):
    from mcp_open_data_hk import server

    calls = []
    data = [f"dataset-{i}" for i in range(1600)]

    async def read(url, params):
        assert url.endswith("/package_list")
        calls.append(params)
        return {"success": True, "result": data[params.get("offset", 0) :]}

    monkeypatch.setattr(server, "make_api_request", read)
    async with Client(server.create_server()) as mcp:
        first = await mcp.call_tool("list_datasets", {})
        second = await mcp.call_tool("list_datasets", {"offset": 1000})
        for tool, arguments in (
            ("list_datasets", {"limit": -1}),
            ("list_datasets", {"offset": -1}),
            ("list_categories", {"limit": -1}),
            ("list_categories", {"offset": -1}),
            ("search_datasets", {"limit": -1}),
            ("search_datasets", {"offset": -1}),
            ("get_datasets_by_format", {"limit": -1, "file_format": "JSON"}),
        ):
            error = await mcp.call_tool(tool, arguments, raise_on_error=False)
            assert error.is_error and error.content[0].text.startswith("INVALID_QUERY:")
    assert first.structured_content["result"] == data[:1000]
    assert second.structured_content["result"] == data[1000:]
    assert calls == [{"limit": 1000}, {"limit": 1000, "offset": 1000}]
