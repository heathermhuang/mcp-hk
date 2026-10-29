"""Exact browser contract and real worker lifetime, independent of UI guesses."""

import asyncio
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.resource_codec import typed_filters, presentation
from mcp_open_data_hk.resource_formats import parse
from test_resources import resource_service  # noqa: F401


@pytest.fixture
def mixed(resource_service, monkeypatch):  # noqa: F811
    rows = [
        {"n": 1},
        {"n": 1.0},
        {"n": True},
        {"n": None},
        {},
        {"n": "001"},
        {"n": ""},
        {"n": 9007199254740993},
        {"n": -0.0},
        {"n": "0.1234567890123456789", "a.b": 4, "a": {"b": 9}},
    ]
    rows, schema = parse(json.dumps(rows).encode(), "JSON")

    async def load(*args, **kwargs):
        return {}, {"rows": rows, "schema": schema}, {"hash": "abc"}, False

    monkeypatch.setattr(resource_service.resources, "load", load)
    monkeypatch.setattr(
        resource_service.resources, "envelope", lambda *args: {"schema": schema}
    )
    return resource_service


@pytest.mark.asyncio
async def test_mixed_exact_kinds_http_mcp_legacy(mixed):
    schema = (await mixed.resources.query("r1"))["schema"]
    assert schema["fields"][0]["name"] == "a"
    assert next(f for f in schema["fields"] if f["name"] == "n")["scalarKinds"] == [
        "boolean",
        "float",
        "integer",
        "null",
        "string",
    ]
    app = create_app(mixed)
    cases = [
        ("integer", "1", 1),
        ("float", "1.0", 1),
        ("boolean", "true", 1),
        ("null", "null", 1),
        ("string", "001", 1),
        ("string", "", 1),
        ("integer", "9007199254740993", 1),
    ]
    async with Client(app.state.mcp) as mcp:
        with TestClient(app) as http:
            for kind, value, total in cases:
                query = {
                    "typedFilters": [{"field": "n", "kind": kind, "value": value}],
                    "presentation": True,
                }
                response = http.post("/api/v1/resources/r1/query", json=query)
                assert response.status_code == 200, response.text
                result = response.json()
                remote = (
                    await mcp.call_tool(
                        "hk_resource_query", {"resourceId": "r1", **query}
                    )
                ).data
                assert result == remote
                assert result["meta"]["total"] == total
                assert result["presentation"]["rows"][0][0]["kind"] == kind
            for val in [1, 1.0, True, None, "001", ""]:
                result = http.post(
                    "/api/v1/resources/r1/query", json={"filters": {"n": val}}
                ).json()
                assert result["meta"]["total"] == 1
                assert "presentation" not in result
    p = presentation([{"n": -0.0}, {"n": 9007199254740993}, {}], ["n"])
    assert p["rows"][0][0]["json"] == "-0.0"
    assert p["rows"][1][0]["json"] == "9007199254740993"
    assert p["rows"][2][0]["kind"] == "missing"
    assert json.loads(p["recordsJson"])[1]["n"] == 9007199254740993
    found = await mixed.resources.query(
        "r1", typed_filters=[{"field": "a.b", "kind": "integer", "value": "4"}]
    )
    assert found["meta"]["total"] == 1


@pytest.mark.parametrize(
    "kind,value",
    [
        ("integer", "1.0"),
        ("integer", "01"),
        ("float", "NaN"),
        ("float", "1e999"),
        ("boolean", "1"),
        ("null", ""),
        ("integer", "9" * 201),
    ],
)
def test_invalid_scalar(kind, value):
    with pytest.raises(DomainError):
        typed_filters([{"field": "n", "kind": kind, "value": value}])


def test_duplicate_mixed_and_extra_filters():
    p = {"field": "n", "kind": "integer", "value": "1"}
    for values, legacy in [([p, p], {}), ([p], {"n": 1}), ([{**p, "cursor": "x"}], {})]:
        with pytest.raises(DomainError):
            typed_filters(values, legacy)


@pytest.mark.asyncio
async def test_real_completion_admission_deadline_and_cleanup(mixed, monkeypatch):
    entered, release, closed = threading.Event(), threading.Event(), threading.Event()

    class Rows:
        def __len__(self):
            return 1

        def __iter__(self):
            entered.set()
            release.wait(3)
            yield {"n": 1}

        def close(self):
            closed.set()

    from mcp_open_data_hk import resources

    monkeypatch.setattr(resources, "FileRows", Rows)
    rows = Rows()

    async def load(*args, **kwargs):
        return (
            {},
            {"rows": rows, "schema": {"fields": [{"name": "n"}], "queryFields": []}},
            {"hash": "x"},
            False,
        )

    monkeypatch.setattr(mixed.resources, "load", load)
    mixed.resources.scan_limit = 1
    pending = asyncio.create_task(mixed.resources.query("r1"))
    while not entered.is_set():
        await asyncio.sleep(0.001)
    pending.cancel()
    with pytest.raises(asyncio.CancelledError):
        await pending
    assert mixed.resources.active_scans == 1 and not closed.is_set()
    with pytest.raises(DomainError, match="RESOURCE_BUSY"):
        await mixed.resources.query("r1")
    ticks = []
    for _ in range(5):
        ticks.append(time.monotonic())
        await asyncio.sleep(0.002)
    assert len(ticks) == 5  # Event loop remains available while worker owns rows.
    release.set()
    for _ in range(100):
        if mixed.resources.active_scans == 0:
            break
        await asyncio.sleep(0.002)
    assert closed.is_set() and mixed.resources.active_scans == 0
    mixed.resources.scan_seconds = 0
    with pytest.raises(DomainError, match="RESOURCE_SCAN_DEADLINE"):
        await mixed.resources.query("r1")


@pytest.mark.asyncio
async def test_whole_envelope_budget(mixed, monkeypatch):
    monkeypatch.setattr(
        mixed.resources, "envelope", lambda *args: {"notice": "字" * 520000}
    )
    with pytest.raises(DomainError, match="RESPONSE_TOO_LARGE"):
        await mixed.resources.query("r1", presentation=True)


@pytest.mark.asyncio
async def test_sidecar_bytes_count_toward_cap_but_legacy_page_still_fits(
    mixed, monkeypatch
):
    async def load(*args, **kwargs):
        return (
            {},
            {
                "rows": [{"s": "x" * 400000}],
                "schema": {"fields": [{"name": "s"}], "queryFields": []},
            },
            {"hash": "x"},
            False,
        )

    monkeypatch.setattr(mixed.resources, "load", load)
    assert (await mixed.resources.query("r1"))["meta"]["total"] == 1
    with pytest.raises(DomainError, match="RESPONSE_TOO_LARGE"):
        await mixed.resources.query("r1", presentation=True)


@pytest.mark.asyncio
async def test_unfiltered_count_does_not_scan_the_entire_accepted_source(
    mixed, monkeypatch
):
    class Rows:
        def __len__(self):
            return 100000

        def __iter__(self):
            for index in range(22):
                yield {"n": index}
            raise AssertionError("Preview scanned beyond its page")

    async def load(*args, **kwargs):
        return (
            {},
            {"rows": Rows(), "schema": {"fields": [{"name": "n"}], "queryFields": []}},
            {"hash": "x"},
            False,
        )

    monkeypatch.setattr(mixed.resources, "load", load)
    page = await mixed.resources.query("r1", fields=["n"])
    assert page["meta"]["total"] == 100000
    assert len(page["data"]["items"]) == 20
    assert page["meta"]["nextOffset"] == 20
