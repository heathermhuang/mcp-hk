"""Small public Plate.hk captures, 2026-10-16; provider/source terms still apply."""

import copy
import json
import time
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.contracts import DomainError, PlateSearchQuery
from mcp_open_data_hk.http import request_json
from mcp_open_data_hk.platehk import parse_comparables, public_row
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store


def fixture(name):
    return json.loads(
        (Path(__file__).parent / "fixtures" / f"platehk-{name}.json").read_text()
    )


@pytest.fixture
def service(tmp_path):
    return Service(Store(str(tmp_path / "data.sqlite3")))


@pytest.mark.asyncio
async def test_http_mcp_parity_and_independent_discovery(service, monkeypatch):
    calls = []

    async def upstream(url, params=None):
        calls.append((url, params))
        if url.endswith("index.json"):
            return fixture("datasets")
        if url.endswith("comparables"):
            return fixture("comparables")
        assert params["mode"] == "exact"
        return fixture("search")

    monkeypatch.setattr("mcp_open_data_hk.platehk.request_json", upstream)
    app = create_app(service)
    with TestClient(app) as http:
        rest = http.get("/api/v1/plates/search?q=AA88&pageSize=2").json()
        packs = http.get("/api/v1/packs").json()["items"]
        assert len(packs) == 6 and [
            p["id"] for p in packs if p["providerType"] == "independent"
        ] == ["platehk", "seehouse", "racing"]
        coverage = http.get("/api/v1/plates/datasets").json()
        assert coverage["data"]["generatedAt"] == "2026-10-15"
        assert len(coverage["data"]["items"]) == 5
        compared = http.get("/api/v1/plates/comparables?q=AH168&pageSize=2").json()
        assert compared["data"]["sampleSize"] == 22
        assert compared["data"]["statistics"]["median"] == 50000
    async with Client(app.state.mcp) as client:
        tools = {t.name: t for t in await client.list_tools()}
        assert len(tools) == 35
        assert tools["hk_sfc_status"].annotations.readOnlyHint

        assert tools["hk_plate_search"].annotations.readOnlyHint
        result = (
            await client.call_tool("hk_plate_search", {"q": "AA88", "pageSize": 2})
        ).data
        assert result["data"] == rest["data"]
        assert len((await client.call_tool("hk_data_packs", {})).data["items"]) == 6
        assert (await client.call_tool("hk_plate_datasets", {})).data[
            "data"
        ] == coverage["data"]
        assert (
            await client.call_tool(
                "hk_plate_comparables", {"q": "AH168", "pageSize": 2}
            )
        ).data["data"] == compared["data"]
    assert len(calls) == 3  # Both transports share successful, bounded query caches.
    row = rest["data"]["items"][0]
    assert row["single_line"] == "AA 88" and row["amount_hkd"] == 1150000
    assert row["pdf_url"].startswith("https://www.td.gov.hk/")
    assert rest["provenance"][0]["providerType"] == "independent"
    assert rest["warnings"][0]["code"] == "HISTORICAL_AUCTION_DATA"
    checks = service.store.checks()
    assert checks["platehk"]["success"] and "addresses" not in checks


@pytest.mark.asyncio
async def test_contains_pagination_and_empty_are_distinct(service, monkeypatch):
    async def upstream(url, params):
        assert "mode" not in params
        data = fixture("search")
        return {
            **data,
            "q": params["q"],
            "mode": None,
            "page": params["page"],
            "page_size": 1,
            "total": 3 if params["q"] == "88" else 0,
            "rows": data["rows"] if params["q"] == "88" else [],
        }

    monkeypatch.setattr("mcp_open_data_hk.platehk.request_json", upstream)
    first = await service.plates.search(
        PlateSearchQuery(q="88", mode="contains", pageSize=1)
    )
    assert first["data"]["nextPage"] == 2 and first["meta"]["total"] == 3
    assert first["meta"]["truncated"]
    empty = await service.plates.search(
        PlateSearchQuery(q="NOMATCH", mode="contains", pageSize=1)
    )
    assert empty["data"]["items"] == [] and empty["meta"]["total"] == 0
    assert not empty["meta"]["truncated"]


def test_record_semantics_and_allowlist():
    row = fixture("legacy")["rows"][0]
    result = public_row(
        {**row, "seller_phone": "not-public", "payment": {"token": "not-public"}}
    )
    assert result["auction_date_label"] == "2000-2006"
    assert (
        result["date_precision"] == "year_range"
        and result["source_sheet"] == "2000-2009"
    )
    assert result["source_url"].startswith("https://plate.hk/data/")
    assert "seller_phone" not in result and "payment" not in result
    unsold = public_row(
        {
            **row,
            "single_line": "HELLO",
            "double_line": "HEL\nLO",
            "amount_hkd": None,
            "result_status": "unsold",
        }
    )
    assert unsold["double_line"] == "HEL\nLO" and unsold["amount_hkd"] is None
    with pytest.raises(ValueError):
        public_row({**row, "pdf_url": "https://attacker.example/private"})


def test_unqualified_statistics_remain_null():
    payload = fixture("comparables")
    payload["sample_size"] = 3
    with pytest.raises(ValueError):
        parse_comparables(payload)
    payload["statistics"] = None
    assert parse_comparables(payload)["statistics"] is None


def test_comparison_target_keeps_its_actual_source_sale():
    parsed = parse_comparables(fixture("comparables-target"))
    assert parsed["target"]["single_line"] == "AA 88"
    assert parsed["target"]["amount_hkd"] == 1150000
    assert parsed["sampleSize"] == 6
    assert parsed["totalHistory"] == 1


@pytest.mark.asyncio
async def test_invalid_query_is_not_a_provider_health_failure(service, monkeypatch):
    async def rejected(url, params):
        raise DomainError("INVALID_QUERY", "Invalid mark", 400)

    monkeypatch.setattr("mcp_open_data_hk.platehk.request_json", rejected)
    with pytest.raises(DomainError, match="INVALID_QUERY"):
        await service.plates.search(PlateSearchQuery(q="Q"))
    assert "platehk" not in service.store.checks()


@pytest.mark.asyncio
@pytest.mark.parametrize("failure", ["schema", "timeout", "rate"])
async def test_provider_failures_not_empty_or_cached(service, monkeypatch, failure):
    async def broken(url, params):
        if failure == "schema":
            return {"rows": [], "total": 0}
        raise DomainError(
            "UPSTREAM_TIMEOUT" if failure == "timeout" else "PLATEHK_RATE_LIMITED",
            "test provider failure",
            504 if failure == "timeout" else 429,
        )

    monkeypatch.setattr("mcp_open_data_hk.platehk.request_json", broken)
    with TestClient(create_app(service)) as client:
        response = client.get("/api/v1/plates/search?q=AA88")
        assert (
            response.status_code
            == {"schema": 503, "timeout": 504, "rate": 429}[failure]
        )
        assert "error" in response.json() and "data" not in response.json()
    assert service.store.checks()["platehk"]["error"]
    with service.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM address_cache").fetchone()[0] == 0


@pytest.mark.asyncio
async def test_cache_expiry_does_not_claim_a_new_source_check(service, monkeypatch):
    count = 0

    async def upstream(url, params):
        nonlocal count
        count += 1
        return fixture("search")

    monkeypatch.setattr("mcp_open_data_hk.platehk.request_json", upstream)
    query = PlateSearchQuery(q="AA88", pageSize=2)
    first = await service.plates.search(query)
    cached = await service.plates.search(query)
    assert first["provenance"] == cached["provenance"] and count == 1
    with service.store.connect() as db:
        db.execute("UPDATE address_cache SET retrieved=?", (time.time() - 301,))
    await service.plates.search(query)
    assert count == 2
    for n in range(205):
        service.store.cache_put(f"platehk:{n}", {}, source="platehk")
    with service.store.connect() as db:
        assert db.execute("SELECT COUNT(*) FROM address_cache").fetchone()[0] == 200


def test_http_validation_rejects_extra_destinations(service):
    with TestClient(create_app(service)) as client:
        for path in [
            "search?q=AA88&sourceUrl=https://evil.example",
            "search?q=AA88&pageSize=51",
            "search?q=AA88&dataset=marketplace",
            "search?q=AA88&mode=wild",
            "search?q=",
            "search?q=%20",
            "comparables?q=AH168&page=0",
        ]:
            assert client.get("/api/v1/plates/" + path).status_code == 400
        # Optional external source must not become a government-readiness dependency.
        assert (
            next(
                s
                for s in client.get("/api/v1/status").json()["sources"]
                if s["sourceId"] == "platehk"
            )["providerType"]
            == "independent"
        )


@pytest.mark.asyncio
async def test_http_source_redirects_and_rate_limits(monkeypatch):
    from mcp_open_data_hk import http

    real_client = httpx.AsyncClient
    responses = [
        httpx.Response(302, headers={"Location": "https://evil.example"}),
        httpx.Response(429),
    ]

    def client(**kwargs):
        assert kwargs["follow_redirects"] is False
        return real_client(
            **kwargs,
            transport=httpx.MockTransport(lambda r: copy.copy(responses.pop(0))),
        )

    monkeypatch.setattr(http.httpx, "AsyncClient", client)
    with pytest.raises(DomainError, match="UPSTREAM_UNAVAILABLE"):
        await request_json("https://plate.hk/api/search")
    with pytest.raises(DomainError, match="PLATEHK_RATE_LIMITED"):
        await request_json("https://plate.hk/api/search")
    with pytest.raises(DomainError, match="INVALID_SOURCE"):
        await request_json("https://evil.example/api/search")
