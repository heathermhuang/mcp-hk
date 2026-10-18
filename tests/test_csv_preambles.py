import hashlib
import json
import copy
from pathlib import Path

import pytest

from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.resource_formats import parse
from mcp_open_data_hk.resource_stream import FileRows
from mcp_open_data_hk.review_config import SOURCE_REVIEW
from test_quality_repairs import service_with_resources


def test_dated_preamble_retains_source_header_and_stable_positions(tmp_path):
    body = b"2026-10-18\nid,name\n1,Actual\n"
    rows, schema = parse(body, "CSV")
    assert rows == [
        {"_column_1": "id", "_column_2": "name"},
        {"_column_1": "1", "_column_2": "Actual"},
    ]
    assert schema["sourceColumns"][0]["sourceHeader"] == "2026-10-18"
    assert schema["readerContract"] == "csv-date-preamble-1"
    p = tmp_path / "source.csv"
    p.write_bytes(body)
    stream = FileRows(p, "CSV")
    assert (
        list(stream) == rows
        and stream.schema["readerContract"] == "csv-date-preamble-1"
    )
    stream.close()


@pytest.mark.asyncio
async def test_csv_reader_revalidates_legacy_fields_and_accepts_daily_date_change(
    tmp_path, monkeypatch
):
    s, resources = service_with_resources(tmp_path, count=1)
    rid = resources[0]["id"]
    body = b"2026-10-18\nid,name\n1,Actual\n"
    rows, schema = parse(body, "CSV")
    old = copy.deepcopy(schema)
    old.pop("readerContract")
    old["fields"][0]["name"] = "2026-10-17"
    old["sourceColumns"][0].update(name="2026-10-17", sourceHeader="2026-10-17")
    legacy = hashlib.sha256(
        json.dumps(["structured-reader-3", rid, "", "", None], sort_keys=True).encode()
    ).hexdigest()
    oldrows = [
        {"2026-10-17": r["_column_1"], "_column_2": r["_column_2"]} for r in rows
    ]
    s.resources.catalogue.accept(rid, legacy, oldrows, old, "a" * 64, {})
    calls = []

    async def source(url, *args, **kwargs):
        calls.append(url)
        return body, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", source)
    current = await s.resources.query(rid, require_fresh=True)
    assert calls and current["data"]["items"] == rows
    assert current["schema"]["sourceContentHash"] == hashlib.sha256(body).hexdigest()
    body = body.replace(b"2026-10-18", b"2026-10-19")
    token = SOURCE_REVIEW.set(True)
    try:
        current = await s.resources.schema(rid, require_fresh=True)
    finally:
        SOURCE_REVIEW.reset(token)
    assert current["schema"]["sourceColumns"][0]["sourceHeader"] == "2026-10-19"
    body = b"2026-10-20\nid,name,extra\n1,Actual,new\n"
    token = SOURCE_REVIEW.set(True)
    try:
        with pytest.raises(DomainError, match="SCHEMA_DRIFT"):
            await s.resources.schema(rid, require_fresh=True)
    finally:
        SOURCE_REVIEW.reset(token)


@pytest.mark.asyncio
async def test_new_csv_cache_key_does_not_bypass_real_legacy_schema_drift(
    tmp_path, monkeypatch
):
    s, resources = service_with_resources(tmp_path, count=1)
    rid = resources[0]["id"]
    rows, schema = parse(b"Name,Count\nA,1\n", "CSV")
    legacy = hashlib.sha256(
        json.dumps(["structured-reader-3", rid, "", "", None], sort_keys=True).encode()
    ).hexdigest()
    s.resources.catalogue.accept(rid, legacy, rows, schema, "b" * 64, {})

    async def source(url, *args, **kwargs):
        return b"Name,Changed\nA,2\n", {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", source)
    with pytest.raises(DomainError, match="SCHEMA_DRIFT"):
        await s.resources.schema(rid, require_fresh=True)


@pytest.mark.asyncio
async def test_large_file_uses_longer_finite_download_budget_without_raising_byte_limit(
    monkeypatch,
):
    from mcp_open_data_hk import resource_fetch

    seen = []

    def source(url, headers, maximum, destination, **kwargs):
        seen.append((maximum, kwargs["deadline"]))
        Path(destination).write_bytes(b"actual")
        return Path(destination), {}, url, 200

    monkeypatch.setattr(resource_fetch, "fetch_sync", source)
    p, *_ = await resource_fetch.fetch_file("https://example.gov.hk/file")
    assert seen == [(128000000, 60)]
    p.unlink()


@pytest.mark.asyncio
async def test_cancelled_large_download_cleans_a_file_written_after_cancellation(
    monkeypatch,
):
    import asyncio
    import threading
    from mcp_open_data_hk import resource_fetch

    started, finish, written = threading.Event(), threading.Event(), threading.Event()
    paths = []

    def source(url, headers, maximum, destination, **kwargs):
        paths.append(Path(destination))
        started.set()
        finish.wait(3)
        Path(destination).write_bytes(b"late actual source body")
        written.set()
        return Path(destination), {}, url, 200

    monkeypatch.setattr(resource_fetch, "fetch_sync", source)
    task = asyncio.create_task(resource_fetch.fetch_file("https://example.gov.hk/file"))
    assert await asyncio.to_thread(started.wait, 2)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    finish.set()
    assert await asyncio.to_thread(written.wait, 2)
    for _ in range(50):
        if not paths[0].exists():
            break
        await asyncio.sleep(0.01)
    assert not paths[0].exists()


def test_hko_uv_object_and_observed_empty_string_are_source_scoped_compatible():
    from mcp_open_data_hk.source_contracts import (
        annotate,
        comparable_fields,
        HKO_CURRENT,
    )

    resource = {
        "datasetId": "hk-hko-rss-current-weather-report",
        "url": "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en",
    }
    schemas = []
    for uv in [
        "",
        {
            "data": [{"place": "Kings Park", "value": 2, "desc": "low"}],
            "recordDesc": "UV index",
        },
    ]:
        rows, schema = parse(
            json.dumps({"warningMessage": "", "uvindex": uv}).encode(), "JSON"
        )
        annotate(resource, rows, schema)
        assert (
            rows[0]["uvindex"] == uv and schema["sourceContract"]["id"] == HKO_CURRENT
        )
        schemas.append(comparable_fields(schema, HKO_CURRENT))
    assert schemas[0] == schemas[1]
    with pytest.raises(DomainError, match="SOURCE_SCHEMA_CHANGED"):
        annotate(
            resource,
            [{"warningMessage": "", "uvindex": []}],
            {"fields": [{"name": "warningMessage", "types": ["string"]}]},
        )
