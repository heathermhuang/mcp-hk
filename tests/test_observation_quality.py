import copy
import json
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.observation_quality import qualify, observation_freshness
from mcp_open_data_hk.quality import semantic_quality
from mcp_open_data_hk.resource_formats import parse
from mcp_open_data_hk.resource_stream import FileRows
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store

RESOURCE = {
    "id": "574e2fdcf4b1756347aedaf3ba2feeda",
    "datasetId": "hk-hko-rss-current-weather-report",
    "url": "https://data.weather.gov.hk/weatherAPI/opendata/weather.php?dataType=rhrread&lang=en",
    "format": "JSON",
    "catalogue": "DATA.GOV.HK",
    "sourceUrl": "https://data.gov.hk/en-data/dataset/hk-hko-rss-current-weather-report",
    "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
    "isApi": True,
}


def payload(hours=0):
    return {
        "temperature": {
            "recordTime": (
                datetime.now(timezone.utc) - timedelta(hours=hours)
            ).isoformat(),
            "data": [{"place": "King's Park", "value": 27, "unit": "C"}],
        },
        "humidity": {
            "recordTime": datetime.now(timezone.utc).isoformat(),
            "data": [
                {"place": "Hong Kong Observatory", "value": 71, "unit": "percent"}
            ],
        },
    }


def qualified(value, path="temperature/data", resource=None):
    rows, schema = parse(json.dumps(value).encode(), "JSON", path)
    qualify(resource or RESOURCE, rows, schema)
    return rows, schema


def test_selected_series_checks_all_rows_and_retains_original_values():
    value = payload()
    rows, schema = qualified(value)
    assert rows == value["temperature"]["data"]
    quality = semantic_quality(schema)
    assert quality["semanticVerification"] == "selected_observation_contract"
    assert quality["qualification"]["uniqueStationCount"] == 1
    assert next(f for f in schema["fields"] if f["name"] == "value")["unit"] == "C"
    assert not observation_freshness(schema)["stale"]
    assert observation_freshness(
        schema, now=datetime.now(timezone.utc).timestamp() + 7300
    )["stale"]
    _, raw = qualified(value, resource={**RESOURCE, "datasetId": "other"})
    assert semantic_quality(raw)["semanticVerification"] == "not_performed"


@pytest.mark.parametrize(
    "failure",
    ["duplicate", "unit", "missing", "boolean", "empty", "time", "future", "humidity"],
)
def test_bad_station_contracts_fail_closed(failure):
    value, path = payload(), "temperature/data"
    rows = value["temperature"]["data"]
    if failure == "duplicate":
        rows.append(copy.deepcopy(rows[0]))
    elif failure == "unit":
        rows[0]["unit"] = "F"
    elif failure == "missing":
        del rows[0]["value"]
    elif failure == "boolean":
        rows[0]["value"] = True
    elif failure == "empty":
        rows.clear()
    elif failure == "time":
        value["temperature"]["recordTime"] = "2026-10-30T12:00:00"
    elif failure == "future":
        value["temperature"]["recordTime"] = (
            datetime.now(timezone.utc) + timedelta(hours=1)
        ).isoformat()
    else:
        path = "humidity/data"
        value["humidity"]["data"][0]["value"] = 101
    with pytest.raises(DomainError):
        qualified(value, path)


def test_small_streamed_and_nested_profiles_distinguish_null_absent_and_empty(tmp_path):
    body = b'[{"id":"001","x":null,"nested":{"x":null}},{"id":"002","nested":{}},{"id":"003","x":"","nested":{"x":""}}]'
    _, small = parse(body, "JSON")
    path = tmp_path / "rows.json"
    path.write_bytes(body)
    streamed = FileRows(path, "JSON", "")
    try:
        for schema in (small, streamed.schema):
            for key, name in [("fields", "x"), ("queryFields", "nested.x")]:
                field = next(f for f in schema[key] if f["name"] == name)
                assert field["absentCount"] == 1
                assert field["nullCount"] == 1
                assert field["missingCount"] == 2  # Existing compatibility field.
            profile = semantic_quality(schema)["completeness"]
            assert profile["rowCount"] == 3 and profile["fieldsWithNullValues"] == 1
    finally:
        streamed.close()


@pytest.mark.asyncio
async def test_http_mcp_quality_parity_and_fresh_download_of_old_observations(
    tmp_path, monkeypatch
):
    service = Service(Store(str(tmp_path / "data.sqlite3")))
    service.resources.catalogue.publish(
        [
            {
                "id": RESOURCE["datasetId"],
                "title": "Current weather",
                "provider": "Hong Kong Observatory",
                "providerType": "government",
                "catalogue": "DATA.GOV.HK",
                "sourceUrl": RESOURCE["sourceUrl"],
            }
        ],
        [RESOURCE],
        {},
    )
    value = payload(hours=3)

    async def fetch(url, *args, **kwargs):
        return json.dumps(value).encode(), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    app = create_app(service)
    args = {"recordPath": "temperature/data", "limit": 2}
    with TestClient(app) as http:
        response = http.post(f'/api/v1/resources/{RESOURCE["id"]}/query', json=args)
        assert response.status_code == 200
        result = response.json()
        assert result["observationFreshness"]["stale"]
        assert not result["validationFreshness"]["cacheExpired"]
        assert (
            result["provenance"][0]["observedAt"]
            != result["provenance"][0]["retrievedAt"]
        )
        assert any(w["code"] == "SOURCE_OBSERVATION_STALE" for w in result["warnings"])
        refused = http.post(
            f'/api/v1/resources/{RESOURCE["id"]}/query',
            json={**args, "requireFresh": True},
        )
        assert (
            refused.status_code == 503
            and refused.json()["error"]["code"] == "SOURCE_OBSERVATION_STALE"
        )
    async with Client(app.state.mcp) as client:
        response = await client.call_tool(
            "hk_resource_query", {"resourceId": RESOURCE["id"], **args}
        )
        assert response.data["quality"] == result["quality"]
        assert response.data["data"] == result["data"]
