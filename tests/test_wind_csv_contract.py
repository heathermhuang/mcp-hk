"""Published five-column wind rows, without inferred timezone or station identity."""

import csv
import hashlib
import io
import json

import pytest

from mcp_open_data_hk import wind_csv
from mcp_open_data_hk.catalogue_store import unpack
from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.resource_formats import parse
from mcp_open_data_hk.review_config import SOURCE_REVIEW
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.source_contracts import comparable_fields
from mcp_open_data_hk.storage import Store


def body(headers, rows):
    out = io.StringIO(newline="")
    writer = csv.writer(out)
    writer.writerow(headers)
    writer.writerows(rows)
    return out.getvalue().encode()


@pytest.fixture(params=sorted(wind_csv.HEADERS))
def source(tmp_path, request):
    service = Service(Store(str(tmp_path / "data.sqlite3")))
    resource = {
        "id": "wind",
        "datasetId": wind_csv.DATASET,
        "format": "CSV",
        "url": request.param,
        "sourceUrl": "https://data.gov.hk/",
        "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
        "catalogue": "DATA.GOV.HK",
    }
    service.resources.catalogue.publish(
        [{"id": wind_csv.DATASET, "title": "Provisional wind", "provider": "HKO"}],
        [resource],
        {},
    )
    return service, resource, wind_csv.HEADERS[request.param]


@pytest.mark.asyncio
async def test_native_markers_and_values_are_retained_with_bounded_cache(
    source, monkeypatch
):
    service, resource, headers = source
    rows = [
        ["202611070040", "Original station", "Calm", " ", "02"],
        ["202611070040", "Original station", "N/A", "N/A", "N/A"],
    ]
    raw = body(headers, rows)
    calls = []

    async def fetch(url, *args, **kwargs):
        calls.append(url)
        return raw, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    result = await service.resources.query("wind")
    assert result["data"]["items"] == [dict(zip(headers, row)) for row in rows]
    schema = result["schema"]
    assert schema["cacheTTLSeconds"] == 600
    assert schema["sourceContract"]["id"] == wind_csv.REVISION
    assert schema["sourceContract"]["provisional"] is True
    assert schema["timestampTimezoneQualification"] == "unreviewed_native_timestamp"
    assert "observationQuality" not in schema and "typedFieldBindings" not in schema
    assert result["capabilities"]["operations"]["nearby"]["state"] != "available"
    assert schema["sourceContentHash"] == hashlib.sha256(raw).hexdigest()
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_legacy_generated_overflow_is_retained_in_its_old_variant(
    source, monkeypatch
):
    service, resource, headers = source
    raw = body(
        headers, [["202611070040", "Station", "N", "01", "02", "unreviewed old value"]]
    )
    rows, old_schema = parse(raw, "CSV")
    old_schema.update(sourceResponseComplete=True, cacheTTLSeconds=86400)
    base = hashlib.sha256(
        json.dumps(
            ["structured-reader-3", "wind", "", "", None], sort_keys=True
        ).encode()
    ).hexdigest()
    legacy_key = hashlib.sha256(("csv-reader-2:" + base).encode()).hexdigest()
    service.resources.catalogue.accept(
        "wind", legacy_key, rows, old_schema, "old-version", {}
    )
    service.resources.catalogue.failure(
        "wind", "SCHEMA_DRIFT", "schema_drift", legacy_key
    )
    before = service.resources.catalogue.check("wind", legacy_key)
    current = body(headers, [["202611070050", "Station", "N", "01", "02"]])

    async def fetch(url, *args, **kwargs):
        return current, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    result = await service.resources.query("wind", require_fresh=True)
    assert result["meta"]["total"] == 1 and len(result["data"]["items"][0]) == 5
    assert service.resources.catalogue.check("wind", legacy_key) == before
    assert "_column_6" in {f["name"] for f in unpack(before["schema_json"])["fields"]}
    assert (
        service.resources.catalogue.cached(legacy_key)["value"]["rows"][0]["_column_6"]
        == "unreviewed old value"
    )


@pytest.mark.parametrize(
    "change", ["extra", "renamed", "short", "timestamp", "nonfinite", "empty"]
)
@pytest.mark.asyncio
async def test_current_unpublished_shapes_and_bad_rows_remain_held(
    source, monkeypatch, change
):
    service, resource, headers = source
    headers = list(headers)
    row = ["202611070040", "Station", "N", "01", "02"]
    if change == "extra":
        row.append("new unlabelled field")
    if change == "renamed":
        headers[3] = "Different speed unit"
    if change == "short":
        row.pop()
    if change == "timestamp":
        row[0] = "202602300040"
    if change == "nonfinite":
        row[4] = "NaN"
    raw = body(headers, [] if change == "empty" else [row])

    async def fetch(url, *args, **kwargs):
        return raw, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    with pytest.raises(DomainError, match="SOURCE_SCHEMA_CHANGED"):
        await service.resources.query("wind", require_fresh=True)


def test_only_generated_historical_overflow_is_excluded_from_comparison():
    headers = next(iter(wind_csv.HEADERS.values()))
    _, schema = parse(
        body(headers, [["202611070040", "Station", "N", "01", "02", "old"]]), "CSV"
    )
    assert len(comparable_fields(schema, wind_csv.REVISION)) == 5
    schema["sourceColumns"][5]["sourceHeader"] = "A source-declared field"
    assert len(comparable_fields(schema, wind_csv.REVISION)) == 6
    assert len(comparable_fields(schema)) == 6


def test_other_urls_and_datasets_do_not_inherit_the_contract():
    url = next(iter(wind_csv.HEADERS))
    assert not wind_csv.profile({"datasetId": "other", "format": "CSV", "url": url})
    assert not wind_csv.profile(
        {"datasetId": wind_csv.DATASET, "format": "CSV", "url": url + "?other=1"}
    )


@pytest.mark.asyncio
async def test_future_overflow_does_not_reuse_a_valid_cache_or_drop_current_data(
    source, monkeypatch
):
    service, resource, headers = source
    current = body(headers, [["202611070040", "Station", "N", "01", "02"]])

    async def fetch(url, *args, **kwargs):
        return current, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    accepted = await service.resources.query("wind")
    current = body(headers, [["202611070050", "Station", "N", "01", "02", "new"]])
    token = SOURCE_REVIEW.set(True)
    try:
        with pytest.raises(DomainError, match="SOURCE_SCHEMA_CHANGED"):
            await service.resources.query("wind", require_fresh=True)
    finally:
        SOURCE_REVIEW.reset(token)
    assert (
        service.resources.catalogue.check("wind")["hash"] == accepted["meta"]["version"]
    )
