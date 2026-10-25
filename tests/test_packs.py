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
        assert len(tools) == 28
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
async def test_catalogue_legacy_facets_are_additive(monkeypatch):
    from mcp_open_data_hk import server

    async def read(url, params):
        return {
            "success": True,
            "result": {"results": [], "count": 0, "search_facets": {"tags": {}}},
        }

    monkeypatch.setattr(server, "make_api_request", read)
    result = await server.search_datasets_with_facets("transport")
    assert {"count", "results", "has_more", "search_facets"} == set(result)


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
