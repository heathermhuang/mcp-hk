"""Typed comparisons preserve original values and complete streamed totals."""

import json

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.resource_formats import parse
from mcp_open_data_hk.resource_predicates import Predicates
from mcp_open_data_hk.resource_stream import FileRows
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store


@pytest.fixture
def service(tmp_path, monkeypatch):
    service = Service(Store(str(tmp_path / "db.sqlite3")))
    service.resources.catalogue.publish(
        [{"id": "d", "title": "d", "provider": "Example", "catalogue": "DATA.GOV.HK"}],
        [
            {
                "id": "r",
                "datasetId": "d",
                "format": "JSON",
                "url": "https://example.gov.hk/data.json",
                "sourceUrl": "https://example.gov.hk/",
                "termsUrl": "https://example.gov.hk/terms",
                "catalogue": "DATA.GOV.HK",
            }
        ],
        {},
    )

    async def fetch(url, headers=None, **kwargs):
        return (
            json.dumps(
                [
                    {"id": "001", "amount": 9007199254740993},
                    {"id": "002", "amount": 1.2},
                    {"id": "003", "amount": 3},
                    {"id": "004", "amount": None},
                    {"id": "005"},
                ]
            ).encode(),
            {},
            url,
            200,
        )

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    return service


@pytest.mark.asyncio
async def test_numeric_precision_total_before_limit_stable_order_and_mcp(service):
    query = {
        "predicates": [
            {"field": "amount", "kind": "number", "op": "gte", "value": "1.2"}
        ],
        "orderBy": [{"field": "amount", "kind": "number", "direction": "desc"}],
        "limit": 1,
    }
    with TestClient(create_app(service)) as client:
        first = client.post("/api/v1/resources/r/query", json=query).json()
        assert first["meta"]["total"] == 3
        assert first["data"]["items"] == [{"id": "001", "amount": 9007199254740993}]
        query.update(offset=1, version=first["meta"]["version"])
        second = client.post("/api/v1/resources/r/query", json=query).json()
        assert second["data"]["items"][0]["id"] == "003"
        assert second["meta"]["typedPredicates"]["excludedRows"] == {
            "missing": 1,
            "null": 1,
            "invalid": 0,
        }
        query["version"] = "wrong"
        assert client.post("/api/v1/resources/r/query", json=query).status_code == 409
    async with Client(create_app(service).state.mcp) as client:
        result = await client.call_tool(
            "hk_resource_query",
            {
                "resourceId": "r",
                "predicates": [
                    {
                        "field": "amount",
                        "kind": "number",
                        "op": "between",
                        "value": "1.2",
                        "upper": "3",
                    }
                ],
            },
        )
        result = json.loads(result.content[0].text)
        assert result["data"]["items"] == [{"id": "002", "amount": 1.2}]
        assert result["meta"]["total"] == 1


@pytest.mark.asyncio
async def test_ids_are_not_cast_and_ordering_is_bounded_and_version_pinned(service):
    resources = service.resources
    for args in [
        {"predicates": [{"field": "id", "kind": "number", "op": "gt", "value": "0"}]},
        {
            "predicates": [
                {"field": "id", "kind": "date", "op": "gt", "value": "2025-01-01"}
            ]
        },
        {
            "predicates": [
                {"field": "amount", "kind": "number", "op": "gt", "value": "NaN"}
            ]
        },
        {"order_by": [{"field": "amount", "kind": "number"}], "offset": 1000},
    ]:
        with pytest.raises(DomainError, match="INVALID_PREDICATE"):
            await resources.query("r", **args)
    with pytest.raises(DomainError, match="RESOURCE_VERSION_REQUIRED"):
        await resources.query(
            "r", order_by=[{"field": "amount", "kind": "number"}], offset=1
        )
    result = await resources.query(
        "r", order_by=[{"field": "amount", "kind": "number", "direction": "desc"}]
    )
    assert [r["id"] for r in result["data"]["items"]] == [
        "001",
        "003",
        "002",
        "004",
        "005",
    ]


def test_declared_calendar_dates_half_open_intervals_and_invalid_values():
    schema = {
        "fields": [{"name": "date", "types": ["string", "null"]}],
        "nativeTemporalFields": {"date": "date"},
    }
    typed = Predicates(
        [
            {
                "field": "date",
                "kind": "date",
                "op": "between",
                "value": "2026-01-01",
                "upper": "2026-02-01",
            }
        ],
        [],
        schema,
        {"date"},
        0,
        20,
    )
    assert typed.matches({"date": "2026-01-01"})
    assert not typed.matches({"date": "2026-02-01"})
    assert not typed.matches({"date": "01/01/2026"})
    assert not typed.matches({})
    assert typed.excluded == {"missing": 1, "null": 0, "invalid": 1}
    with pytest.raises(DomainError, match="INVALID_PREDICATE"):
        Predicates(
            [
                {
                    "field": "date",
                    "kind": "datetime",
                    "op": "gte",
                    "value": "2026-01-01T00:00:00",
                }
            ],
            [],
            schema,
            {"date"},
            0,
            20,
        )


@pytest.mark.asyncio
async def test_streamed_order_and_predicates_scan_all_rows(
    service, tmp_path, monkeypatch
):
    rows = [{"id": f"{i:04}", "amount": i % 11} for i in range(500)]
    # Use a real disk-backed reader and the same scan admission/deadline path.
    path = tmp_path / "rows.json"
    path.write_text(json.dumps(rows))
    file_rows = FileRows(path, "JSON")
    original = service.resources.load

    async def load(*args, **kwargs):
        resource, value, check, stale = await original(*args, **kwargs)
        value = {"rows": file_rows, "schema": file_rows.schema}
        return resource, value, check, stale

    monkeypatch.setattr(service.resources, "load", load)
    result = await service.resources.query(
        "r",
        predicates=[{"field": "amount", "kind": "number", "op": "gte", "value": "9"}],
        order_by=[{"field": "amount", "kind": "number", "direction": "desc"}],
        limit=3,
    )
    expected = sorted(
        [r for r in rows if r["amount"] >= 9], key=lambda r: (-r["amount"], r["id"])
    )
    assert result["data"]["items"] == expected[:3]
    assert result["meta"]["total"] == len(expected)
    assert not path.exists()


def test_native_date_evidence_does_not_guess_csv_dates():
    _, schema = parse(b"date\n2026-01-01\n", "CSV")
    assert schema["nativeTemporalFields"] == {}
    from mcp_open_data_hk.source_contracts import annotate, HKO_CURRENT

    schema = {
        "fields": [
            {"name": "updateTime", "types": ["string"]},
            {"name": "warningMessage", "types": ["string"]},
        ]
    }
    annotate(
        {
            "datasetId": "hk-hko-rss-current-weather-report",
            "url": "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread",
        },
        [{"warningMessage": "", "updateTime": "2026-11-05T12:00:00+08:00"}],
        schema,
    )
    assert schema["typedFieldBindings"]["updateTime"]["revision"] == HKO_CURRENT
    predicate = Predicates(
        [
            {
                "field": "updateTime",
                "kind": "datetime",
                "op": "gte",
                "value": "2026-11-05T04:00:00Z",
            }
        ],
        [],
        schema,
        {"updateTime", "warningMessage"},
        0,
        20,
    )
    assert predicate.matches({"updateTime": "2026-11-05T12:00:00+08:00"})
    assert not predicate.matches({"updateTime": "2026-11-05T12:00:00"})
