"""Public SeeHouse captures from 2026-10-18; original listing rights still apply."""

import copy
import json
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.contracts import DomainError, PropertySearchQuery
from mcp_open_data_hk.http import request_json
from mcp_open_data_hk.seehouse import parse
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store

BUILDING = "hk-csdi-95d9ff45d90eb3f5"


def fixture(kind):
    return json.loads(
        (Path(__file__).parent / "fixtures" / f"seehouse-{kind}.json").read_text()
    )


@pytest.fixture
def service(tmp_path):
    service = Service(Store(str(tmp_path / "data.sqlite3")))
    service.resources.catalogue.publish(
        [
            {
                "id": "sample",
                "title": "Sample",
                "catalogue": "DATA.GOV.HK",
                "provider": "Example",
                "providerType": "government",
            }
        ],
        [],
        {},
    )
    return service


@pytest.mark.asyncio
async def test_discovery_and_all_http_mcp_pairs(service, monkeypatch):
    calls = []

    async def upstream(url, params=None):
        calls.append((url, params))
        assert url.startswith("https://see.house/api/v1/")
        kind = (
            "search"
            if url.endswith("search")
            else (
                "coverage"
                if url.endswith("status")
                else "history" if url.endswith("price-history") else "building"
            )
        )
        if kind != "coverage":
            assert params["locale"] == "zh-HK"
        return fixture(kind)

    monkeypatch.setattr("mcp_open_data_hk.seehouse.request_json", upstream)
    app = create_app(service)
    cases = [
        (
            "search",
            "hk_property_search",
            {"q": "太古城", "limit": 2, "lang": "zh-Hant"},
        ),
        (
            "building",
            "hk_property_building",
            {"buildingId": BUILDING, "lang": "zh-Hant"},
        ),
        (
            "price-history",
            "hk_property_price_history",
            {"buildingId": BUILDING, "lang": "zh-Hant"},
        ),
        ("coverage", "hk_property_coverage", {}),
    ]
    with TestClient(app) as http:
        results = [
            http.get("/api/v1/properties/" + path, params=params)
            for path, _, params in cases
        ]
        assert all(r.status_code == 200 for r in results)
        found = http.get("/api/v1/catalogue/datasets", params={"q": "睇樓"}).json()
        assert found["items"][0]["id"] == "mcp:seehouse"
        assert found["items"][0]["action"]["url"] == "/properties"
        assert found["items"][0]["providerType"] == "independent"
        pack = next(
            p
            for p in http.get("/api/v1/packs").json()["items"]
            if p["id"] == "seehouse"
        )
        assert pack["tools"] == [tool for _, tool, _ in cases]
        assert http.get("/properties").status_code == 200
        assert b"properties.js" in http.get("/properties").content
    async with Client(app.state.mcp) as mcp:
        tools = {t.name: t for t in await mcp.list_tools()}
        for response, (_, tool, params) in zip(results, cases):
            assert tools[tool].annotations.readOnlyHint
            data = (await mcp.call_tool(tool, params)).data
            assert data["data"] == response.json()["data"]
            assert data["provenance"] == response.json()["provenance"]
            assert data["provenance"][0]["providerType"] == "independent"
            assert data["warnings"][0]["code"] == "PROPERTY_ADVERTISEMENTS"
    assert len(calls) == 4
    assert results[0].json()["meta"]["total"] is None
    assert results[0].json()["meta"]["truncated"] is None
    row = results[1].json()["data"]["listings"][0]
    assert row["priceHkd"] == 12000000 and row["mode"] == "buy"
    assert row["saleableAreaFt2"] == 684
    assert row["sourceAttribution"]["url"].startswith("https://hk.centanet.com/")
    assert row["freshness"]["observedAt"] == "2026-10-17T16:02:51+00:00"
    assert row["dedupeCluster"]["sourceListingRefs"]
    assert results[2].json()["data"]["events"][0]["oldPriceHkd"] == 9200000
    assert "not Land Registry" in results[2].json()["data"]["caveats"][1]
    assert service.store.checks()["seehouse"]["success"]


def test_nested_projection_does_not_relay_new_provider_fields():
    payload = fixture("building")
    payload["ownerContact"] = "private"
    payload["listings"][0]["agentPhone"] = "private"
    payload["listings"][0]["sourceAttribution"]["rawArchive"] = "private"
    result = parse("building", payload)
    assert "private" not in json.dumps(result)
    assert result["address"] is None
    assert result["listings"][0]["freshness"]["dateModified"] is None
    coverage = fixture("coverage")
    coverage["analyticsOps"] = {"reporter": "private"}
    coverage["productionCoverage"]["districts"][0]["secret"] = "private"
    assert "private" not in json.dumps(parse("coverage", coverage))


@pytest.mark.parametrize(
    "path",
    [
        "search?q=%20",
        "search?q=x&limit=21",
        "search?q=x&sourceUrl=https://evil.example",
        "search?q=x&lang=fr",
        "building?buildingId=..%2Fcoverage",
        "building?buildingId=https://evil.example",
        "building?buildingId=x%3Fq=y",
        "price-history?buildingId=x%25",
        "building?buildingId=",
        "search?q=x&page=2",
    ],
)
def test_invalid_queries_never_reach_upstream(service, path):
    with TestClient(create_app(service)) as http:
        assert http.get("/api/v1/properties/" + path).status_code == 400
    assert "seehouse" not in service.store.checks()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["search", "building", "history", "coverage"])
async def test_schema_failure_is_not_an_empty_success_or_cached(
    service, monkeypatch, kind
):
    async def broken(*args):
        return {"candidates": [], "listings": [], "events": []}

    monkeypatch.setattr("mcp_open_data_hk.seehouse.request_json", broken)
    with pytest.raises(DomainError, match="SOURCE_SCHEMA_CHANGED"):
        await service.properties.query(kind, building_id=BUILDING)
    assert service.store.checks()["seehouse"]["error"] == "SOURCE_SCHEMA_CHANGED"
    with service.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM address_cache").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_cache_expiry_failure_does_not_serve_old_listing_as_fresh(
    service, monkeypatch
):
    async def good(*args):
        return fixture("search")

    monkeypatch.setattr("mcp_open_data_hk.seehouse.request_json", good)
    first = await service.properties.search(PropertySearchQuery(q="Taikoo"))
    cached = await service.properties.search(PropertySearchQuery(q="Taikoo"))
    assert first["provenance"] == cached["provenance"]
    with service.store.connect() as db:
        db.execute("UPDATE address_cache SET retrieved=?", (time.time() - 301,))

    async def timeout(*args):
        raise DomainError("UPSTREAM_TIMEOUT", "Source timed out", 504)

    monkeypatch.setattr("mcp_open_data_hk.seehouse.request_json", timeout)
    with pytest.raises(DomainError, match="UPSTREAM_TIMEOUT"):
        await service.properties.search(PropertySearchQuery(q="Taikoo"))
    for n in range(205):
        service.store.cache_put(f"seehouse:{n}", {}, source="seehouse")
    with service.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM address_cache").fetchone()[0] == 200


@pytest.mark.asyncio
async def test_valid_empty_and_missing_building_are_distinct(service, monkeypatch):
    async def empty(*args):
        return {**fixture("search"), "candidates": []}

    monkeypatch.setattr("mcp_open_data_hk.seehouse.request_json", empty)
    result = await service.properties.search(PropertySearchQuery(q="NoMatch"))
    assert result["data"]["candidates"] == []

    async def missing(*args):
        raise DomainError("NOT_FOUND", "Missing building", 404)

    monkeypatch.setattr("mcp_open_data_hk.seehouse.request_json", missing)
    with TestClient(create_app(service)) as http:
        assert (
            http.get("/api/v1/properties/building?buildingId=missing").status_code
            == 404
        )
    assert service.store.checks()["seehouse"]["error"] is None


@pytest.mark.asyncio
async def test_http_source_bounds_redirects_and_provider_errors(monkeypatch):
    from mcp_open_data_hk import http

    real_client = httpx.AsyncClient
    responses = [httpx.Response(status) for status in [302, 429, 404, 400, 503]]

    def client(**kwargs):
        assert kwargs["follow_redirects"] is False
        assert kwargs["trust_env"] is False
        kwargs.pop("transport")
        return real_client(
            **kwargs,
            transport=httpx.MockTransport(lambda r: copy.copy(responses.pop(0))),
        )

    monkeypatch.setattr(http.httpx, "AsyncClient", client)
    for code in [
        "UPSTREAM_UNAVAILABLE",
        "SEEHOUSE_RATE_LIMITED",
        "NOT_FOUND",
        "INVALID_QUERY",
        "UPSTREAM_UNAVAILABLE",
    ]:
        with pytest.raises(DomainError, match=code):
            await request_json("https://see.house/api/v1/buildings/search")


def test_demo_or_inconsistent_rows_are_rejected():
    payload = fixture("search")
    payload["candidates"][0]["listingState"]["source"] = "fixture_fallback"
    with pytest.raises(ValueError):
        parse("search", payload)
    payload = fixture("history")
    payload["eventCount"] += 1
    with pytest.raises(ValueError):
        parse("history", payload)
    payload = fixture("building")
    payload["listings"][0]["priceHkd"] = "unknown"
    with pytest.raises(ValueError):
        parse("building", payload)


@pytest.mark.asyncio
async def test_wrong_building_is_not_cached(service, monkeypatch):
    async def upstream(*args):
        return fixture("building")

    monkeypatch.setattr("mcp_open_data_hk.seehouse.request_json", upstream)
    with TestClient(create_app(service)) as http:
        response = http.get("/api/v1/properties/building?buildingId=other-building")
        assert response.status_code == 503
        assert response.json()["error"]["code"] == "SOURCE_SCHEMA_CHANGED"
    with service.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM address_cache").fetchone()[0] == 0


@pytest.mark.parametrize("bad_price", [-1, float("nan"), True])
def test_invalid_prices_and_unsafe_source_urls_fail_closed(bad_price):
    payload = fixture("building")
    payload["listings"][0]["priceHkd"] = bad_price
    with pytest.raises(ValueError):
        parse("building", payload)
    payload = fixture("building")
    payload["listings"][0]["sourceUrl"] = "javascript:alert(1)"
    with pytest.raises(ValueError):
        parse("building", payload)


@pytest.mark.asyncio
async def test_expired_advert_link_keeps_other_listings_and_never_reconstructs_link(
    service, monkeypatch
):
    payload = fixture("expired-link")

    async def upstream(*args):
        return payload

    monkeypatch.setattr("mcp_open_data_hk.seehouse.request_json", upstream)
    with TestClient(create_app(service)) as http:
        response = http.get(
            "/api/v1/properties/building", params={"buildingId": payload["id"]}
        )
        assert response.status_code == 200
        rows = response.json()["data"]["listings"]
        assert len(rows) == 6
        expired = next(r for r in rows if r["id"] == "28hse:4012077")
        assert expired["sourceUrl"] is None
        assert expired["freshness"]["status"] == "stale"
        assert expired["sourceAttribution"]["url"]
        assert rows[0]["sourceUrl"].startswith("https://")
