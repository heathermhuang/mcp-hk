"""Real HKMA datasize is a page count, not a provider-wide total."""

import gzip
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from mcp_open_data_hk.capabilities import project
from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.resources import hkma_records
from mcp_open_data_hk.resource_protocols import HKMA_PAGING_CONTRACT

URL = "https://api.hkma.gov.hk/public/bank-svf-info/banks-branch-locator?lang=en"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "broken",
    [
        None,
        "count",
        "boolean",
        "repeat",
        "first_changed",
        "last_changed",
        "denied",
        "terminal_denied",
    ],
)
async def test_actual_page_counts_require_terminal_page_and_boundary_validation(
    monkeypatch, broken
):
    fixtures = Path(__file__).parent / "fixtures" / "hkma"
    pages = {
        0: json.loads(
            gzip.decompress((fixtures / "published-request.json.gz").read_bytes())
        ),
        1000: json.loads(
            gzip.decompress((fixtures / "offset-1000.json.gz").read_bytes())
        ),
    }
    # Positive termination is simulated; the real terminal request is held.
    pages[1051] = {
        "header": {"success": True},
        "result": {"datasize": 0, "records": []},
    }
    calls = []

    async def read(url):
        query = parse_qs(urlsplit(url).query)
        assert query["lang"] == ["en"] and query["pagesize"] == ["1000"]
        offset = int(query["offset"][0])
        calls.append(offset)
        if broken == "denied":
            raise DomainError("ACCESS_RESTRICTED", "Provider denied access", 502)
        if broken == "terminal_denied" and offset == 1051:
            raise DomainError("SOURCE_HTTP_ERROR", "Source returned HTTP 405", 502)
        value = json.loads(json.dumps(pages[0 if broken == "repeat" else offset]))
        if broken == "count":
            value["result"]["datasize"] += 1
        elif broken == "boolean":
            value["result"]["datasize"] = True
        elif (broken == "first_changed" and calls.count(0) == 2) or (
            broken == "last_changed" and calls.count(1000) == 2
        ):
            value["result"]["records"][0]["fixtureChanged"] = True
        return value, json.dumps(value).encode(), {}, url

    monkeypatch.setattr("mcp_open_data_hk.resources.read_json", read)
    if broken:
        with pytest.raises(DomainError) as error:
            await hkma_records(URL)
        assert error.value.code == (
            "ACCESS_RESTRICTED"
            if broken == "denied"
            else (
                "SOURCE_HTTP_ERROR"
                if broken == "terminal_denied"
                else (
                    "SOURCE_CHANGED"
                    if broken.endswith("_changed")
                    else "INCOMPLETE_SOURCE"
                )
            )
        )
        if broken == "denied":
            assert calls == [0]
        if broken == "terminal_denied":
            assert calls == [0, 1000, 1051]
    else:
        body, _, _, schema = await hkma_records(URL)
        assert (
            json.loads(body)
            == pages[0]["result"]["records"] + pages[1000]["result"]["records"]
        )
        assert schema["sourceMatched"] == 1051
        assert calls == [0, 1000, 1051, 0, 1000]
        assert schema["hkmaPaginationContract"] == HKMA_PAGING_CONTRACT
        assert schema["countEvidence"]["pageCounts"] == [1000, 51, 0]
        assert schema["countEvidence"]["independentGlobalTotal"] is None


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind",
    [
        "empty",
        "exact_page",
        "request_bound",
        "byte_bound",
        "source_error",
        "short_then_more",
    ],
)
async def test_terminal_empty_and_existing_read_budgets(monkeypatch, kind):
    calls = []

    async def read(url):
        offset = int(parse_qs(urlsplit(url).query)["offset"][0])
        calls.append(offset)
        count = 0 if kind == "empty" or (kind == "exact_page" and offset) else 1000
        if kind == "short_then_more":
            count = 50 if offset == 0 else 100 if offset == 50 else 0
        records = [{"sourceId": str(i)} for i in range(offset, offset + count)]
        value = {
            "header": {"success": kind != "source_error"},
            "result": {"datasize": count, "records": records},
        }
        if kind == "byte_bound":
            value["padding"] = "x" * 4_000_000
        return value, json.dumps(value).encode(), {}, url

    monkeypatch.setattr("mcp_open_data_hk.resources.read_json", read)
    if kind in {"request_bound", "byte_bound", "source_error"}:
        with pytest.raises(DomainError) as error:
            await hkma_records(URL)
        assert error.value.code == (
            "SOURCE_API_ERROR" if kind == "source_error" else "SOURCE_TOO_LARGE"
        )
        assert len(calls) <= 100
    else:
        body, _, _, schema = await hkma_records(URL)
        assert len(json.loads(body)) == (
            0 if kind == "empty" else 150 if kind == "short_then_more" else 1000
        )
        assert calls == (
            [0, 0]
            if kind == "empty"
            else [0, 50, 150, 0, 50] if kind == "short_then_more" else [0, 1000, 0]
        )
        assert schema["countEvidence"]["terminalRows"] == 0


def test_legacy_hkma_acceptance_remains_visible_but_requires_new_contract():
    resource = {"id": "bank", "datasetId": "banks", "format": "JSON", "url": URL}
    schema = {
        "format": "JSON",
        "scope": "complete_api_pages_live",
        "sourceResponseComplete": True,
    }
    receipt = {
        "status": "queryable",
        "schema_json": json.dumps(schema),
        "schema_hash": "old",
        "hash": "retained",
    }
    old = project(resource, {"status": "queryable"}, [receipt])
    assert old["operations"]["records"] == {
        "state": "held",
        "reason": "hkma_pagination_revalidation_required",
    }
    assert old["acceptedSelections"][0]["requiresRevalidation"] is True
    assert old["acceptedSelections"][0]["schemaFingerprint"] == "old"
    schema["hkmaPaginationContract"] = HKMA_PAGING_CONTRACT
    fresh = project(
        resource,
        {"status": "queryable"},
        [{**receipt, "schema_json": json.dumps(schema)}],
    )
    assert fresh["operations"]["records"]["state"] == "available"
    assert fresh["acceptedSelections"][0]["requiresRevalidation"] is False


@pytest.mark.asyncio
async def test_fresh_legacy_cache_cannot_bypass_new_paging_contract(
    tmp_path, monkeypatch
):
    import hashlib
    import httpx
    from fastmcp import Client
    from mcp_open_data_hk.api import create_app
    from mcp_open_data_hk.resource_formats import parse
    from mcp_open_data_hk.services import Service
    from mcp_open_data_hk.storage import Store

    service = Service(Store(str(tmp_path / "store.sqlite3")))
    resource = {
        "id": "bank",
        "datasetId": "banks",
        "format": "JSON",
        "url": URL,
        "sourceUrl": "https://data.gov.hk/en-data/dataset/banks",
        "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
        "catalogue": "DATA.GOV.HK",
        "aliases": [],
        "isApi": True,
    }
    service.resources.catalogue.publish(
        [
            {
                "id": "banks",
                "title": "Banks",
                "provider": "HKMA",
                "catalogue": "DATA.GOV.HK",
                "sourceUrl": resource["sourceUrl"],
            }
        ],
        [resource],
        {},
    )
    fixtures = Path(__file__).parent / "fixtures" / "hkma"
    pages = {
        0: json.loads(
            gzip.decompress((fixtures / "published-request.json.gz").read_bytes())
        ),
        1000: json.loads(
            gzip.decompress((fixtures / "offset-1000.json.gz").read_bytes())
        ),
    }
    # Positive termination is simulated; the real terminal request is held.
    pages[1051] = {
        "header": {"success": True},
        "result": {"datasize": 0, "records": []},
    }
    old_body = json.dumps(pages[0]["result"]["records"]).encode()
    rows, schema = parse(old_body, "JSON")
    schema.update(
        apiFamily="HKMA", scope="complete_api_pages_live", sourceResponseComplete=True
    )
    legacy_key = hashlib.sha256(
        json.dumps(
            ["structured-reader-3", "bank", "", "", None], sort_keys=True
        ).encode()
    ).hexdigest()
    old_digest = hashlib.sha256(old_body).hexdigest()
    service.resources.catalogue.accept("bank", legacy_key, rows, schema, old_digest, {})
    calls = []

    async def read(url):
        offset = int(parse_qs(urlsplit(url).query)["offset"][0])
        calls.append(offset)
        value = pages[offset]
        return value, json.dumps(value).encode(), {}, url

    monkeypatch.setattr("mcp_open_data_hk.resources.read_json", read)
    app = create_app(service)
    async with (
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as http,
        Client(app.state.mcp) as mcp,
    ):
        response = await http.post("/api/v1/resources/bank/query", json={"limit": 1})
        response.raise_for_status()
        value = response.json()
        native = json.loads(
            (
                await mcp.call_tool(
                    "hk_resource_query",
                    {
                        "resourceId": "bank",
                        "limit": 1,
                        "version": value["meta"]["version"],
                    },
                )
            )
            .content[0]
            .text
        )
    assert calls == [0, 1000, 1051, 0, 1000]
    assert value["meta"]["total"] == native["meta"]["total"] == 1051
    assert value["data"] == native["data"]
    assert value["schema"]["hkmaPaginationContract"] == HKMA_PAGING_CONTRACT
    assert service.resources.catalogue.check("bank", legacy_key)["hash"] == old_digest


@pytest.mark.asyncio
async def test_overall_deadline_covers_provider_wait(monkeypatch):
    import asyncio

    async def expired(coroutine, timeout):
        assert 0 < timeout <= 120
        coroutine.close()
        raise asyncio.TimeoutError

    monkeypatch.setattr("mcp_open_data_hk.resources.asyncio.wait_for", expired)
    with pytest.raises(DomainError, match="SOURCE_TIMEOUT"):
        await hkma_records(URL)
