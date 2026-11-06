"""Only the independently captured Hydro map request is bound here."""

import hashlib
import json
from urllib.parse import parse_qs, urlsplit

import pytest

from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.hydro_requests import PAGE, PAGES
from mcp_open_data_hk.resources import source_parameters, template_url
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store

PARAMETERS = {"time": "20261106000000", "mode": "A"}
FEATURE = {
    "type": "Feature",
    "properties": {
        "point_id": 1,
        "time": "2026-11-06 00:00:00",
        "mode": "A",
        "knot": "0.010",
        "deg": "007.0",
    },
    "geometry": {"type": "Point", "coordinates": [114.1, 22.3]},
}


@pytest.fixture(params=sorted(PAGES))
def service(tmp_path, request):
    service = Service(Store(str(tmp_path / "db.sqlite3")))
    service.resources.catalogue.publish(
        [{"id": "hydro", "title": "Prediction", "provider": "Marine Department"}],
        [
            {
                "id": "hydro",
                "datasetId": "hydro",
                "format": "CSV",
                "url": request.param,
                "sourceUrl": "https://data.gov.hk/",
                "catalogue": "DATA.GOV.HK",
                "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
            }
        ],
        {},
    )
    return service


@pytest.mark.asyncio
async def test_explicit_map_snapshot_preserves_raw_prediction_features(
    service, monkeypatch
):
    calls = []
    body = json.dumps({"type": "FeatureCollection", "features": [FEATURE]}).encode()

    async def fetch(url, *args, **kwargs):
        calls.append(url)
        return body, {"content-type": "application/json"}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    missing = await service.resources.schema("hydro")
    assert missing["selectionRequired"] == "parameters"
    assert missing["parameters"] == ["mode", "time"]
    assert (
        missing["sourceRequest"]["interface"]
        == "published_map_prediction_snapshot_not_period_csv"
    )
    assert not calls
    result = await service.resources.query("hydro", parameters=PARAMETERS)
    assert parse_qs(urlsplit(calls[0]).query) == {k: [v] for k, v in PARAMETERS.items()}
    assert result["data"]["items"] == [FEATURE]
    schema = result["schema"]
    assert (
        schema["format"] == "GEOJSON" and schema["advertisedCatalogueFormat"] == "CSV"
    )
    assert schema["sourceContentHash"] == hashlib.sha256(body).hexdigest()
    assert schema["originalRepresentationEquivalence"] == "unreviewed"
    assert schema["predictionTimezoneQualification"] == "unreviewed_native_timestamp"
    assert "Not to be used for navigation" in schema["navigationUse"]
    assert result["capabilities"]["operations"]["nearby"]["state"] != "available"
    assert schema["cacheTTLSeconds"] == 300


@pytest.mark.parametrize(
    "parameters",
    [
        {},
        {"time": "20261106000000"},
        {"time": "20261106000000", "mode": "S"},
        {"time": "20260230000000", "mode": "A"},
        {"time": "20261106000100", "mode": "A"},
        {"time": "20261106000001", "mode": "A"},
        {"time": "20261106000000&x=1", "mode": "A"},
        {**PARAMETERS, "point": "1"},
    ],
)
def test_no_invented_default_mode_or_download_parameters(parameters):
    with pytest.raises(DomainError):
        template_url(PAGE, parameters)


@pytest.mark.asyncio
async def test_other_selectors_fail_before_fetch(service, monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("Invalid selectors must not contact the publisher")

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", forbidden)
    for selector in [{"record_path": "features"}, {"sheet": "Sheet1"}, {"layer": 0}]:
        with pytest.raises(DomainError, match="INVALID_QUERY"):
            await service.resources.query("hydro", parameters=PARAMETERS, **selector)


@pytest.mark.parametrize(
    "value",
    [
        {"error": "Unavailable"},
        {
            "type": "FeatureCollection",
            "features": [{"type": "Feature", "properties": {}}],
        },
        {
            "type": "FeatureCollection",
            "features": [
                {
                    **FEATURE,
                    "properties": {
                        **FEATURE["properties"],
                        "time": "2026-11-07 00:00:00",
                    },
                }
            ],
        },
    ],
)
@pytest.mark.asyncio
async def test_failure_or_wrong_timestamp_never_becomes_empty_data(
    service, monkeypatch, value
):
    async def fetch(url, *args, **kwargs):
        return json.dumps(value).encode(), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    with pytest.raises(DomainError):
        await service.resources.query("hydro", parameters=PARAMETERS)


def test_only_the_three_inspected_original_interfaces_are_bound():
    assert source_parameters(PAGE) == ["mode", "time"]
    for page in PAGES:
        assert source_parameters(page) == ["mode", "time"]
    assert source_parameters(PAGE.replace("lang=tc", "lang=other")) == []
