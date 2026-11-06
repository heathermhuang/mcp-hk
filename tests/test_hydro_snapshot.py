"""Only the independently captured Hydro map request is bound here."""

import hashlib
import json
from urllib.parse import parse_qs, urlsplit

import pytest
import httpx
from fastmcp import Client

from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.hydro_requests import PAGE, PAGES
from mcp_open_data_hk.resources import source_parameters, template_url
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store
from mcp_open_data_hk import hydro_requests
from mcp_open_data_hk.capabilities import summary

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
def service(tmp_path, request, monkeypatch):
    # Parser/parameter tests exercise a cleared source independently of the
    # production-default permission hold, which is tested below.
    monkeypatch.setattr(
        "mcp_open_data_hk.hydro_requests.REUSE_AUTHORIZATION", {"testOnly": True}
    )
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


@pytest.mark.parametrize(
    "value",
    [
        {
            "type": "FeatureCollection",
            "features": [],
            "error": {"message": "Source unavailable"},
        },
        {"type": "FeatureCollection", "features": [FEATURE], "success": False},
    ],
)
@pytest.mark.asyncio
async def test_explicit_source_failures_are_rejected_before_feature_acceptance(
    service, monkeypatch, value
):
    async def fetch(url, *args, **kwargs):
        return json.dumps(value).encode(), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    with pytest.raises(DomainError) as error:
        await service.resources.query("hydro", parameters=PARAMETERS)
    assert error.value.code == "SOURCE_API_ERROR"


def test_public_record_reuse_is_held_by_default_and_does_not_hold_other_datasets():
    assert hydro_requests.REUSE_AUTHORIZATION is None
    assert hydro_requests.reuse_hold(PAGE)["state"] == "pending_source_reuse_review"
    assert hydro_requests.reuse_hold(
        "https://example.gov.hk/alias", hydro_requests.DATASET
    )
    assert hydro_requests.reuse_hold("https://example.gov.hk/other", "other") is None
    assert (
        summary({"queryable": 3}, hydro_requests.DATASET)["records"]["state"] == "held"
    )
    assert summary({"queryable": 3}, "other")["records"]["state"] == "available"


@pytest.mark.asyncio
async def test_reuse_hold_is_metadata_not_a_source_observation(service, monkeypatch):
    monkeypatch.setattr(hydro_requests, "REUSE_AUTHORIZATION", None)
    before = service.resources.catalogue.check("hydro")

    async def forbidden(*args, **kwargs):
        raise AssertionError("A source reuse hold must not fetch providers")

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", forbidden)
    monkeypatch.setattr("mcp_open_data_hk.resources.fetch_file", forbidden)
    for kwargs in [{}, {"parameters": PARAMETERS, "require_fresh": True}]:
        schema = await service.resources.schema("hydro", **kwargs)
        assert schema["recordCount"] is None and not schema["structuredQueryable"]
        assert schema["sourceReuseReview"]["publicApiReuseBasis"] == "unverified"
        assert all(
            op["state"] == "held"
            for op in schema["capabilities"]["operations"].values()
        )
    with pytest.raises(DomainError) as error:
        await service.resources.query("hydro", parameters=PARAMETERS)
    assert error.value.code == "SOURCE_REUSE_REVIEW_REQUIRED"
    assert service.resources.catalogue.check("hydro") == before


@pytest.mark.asyncio
async def test_a_pinned_cached_version_cannot_bypass_a_reuse_hold(service, monkeypatch):
    calls = []

    async def fetch(url, *args, **kwargs):
        calls.append(url)
        return (
            json.dumps({"type": "FeatureCollection", "features": [FEATURE]}).encode(),
            {},
            url,
            200,
        )

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    accepted = await service.resources.query("hydro", parameters=PARAMETERS)
    before = service.resources.catalogue.check("hydro")
    monkeypatch.setattr(hydro_requests, "REUSE_AUTHORIZATION", None)
    with pytest.raises(DomainError) as error:
        await service.resources.query(
            "hydro", parameters=PARAMETERS, version=accepted["meta"]["version"]
        )
    assert error.value.code == "SOURCE_REUSE_REVIEW_REQUIRED"
    assert len(calls) == 1 and service.resources.catalogue.check("hydro") == before
    cap = service.resources.catalogue.capability("hydro")
    assert all(op["state"] == "held" for op in cap["operations"].values())
    assert cap["acceptedSelections"]  # Preserve dated accepted facts.


@pytest.mark.asyncio
async def test_http_and_native_mcp_expose_the_same_hold_without_provider_calls(
    service, monkeypatch
):
    monkeypatch.setattr(hydro_requests, "REUSE_AUTHORIZATION", None)

    async def forbidden(*args, **kwargs):
        raise AssertionError("Held source must not be contacted")

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", forbidden)
    monkeypatch.setattr("mcp_open_data_hk.resources.fetch_file", forbidden)
    app = create_app(service)
    async with (
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as http,
        Client(app.state.mcp) as mcp,
    ):
        a = (await http.post("/api/v1/resources/hydro/schema", json={})).json()
        b = json.loads(
            (await mcp.call_tool("hk_resource_schema", {"resourceId": "hydro"}))
            .content[0]
            .text
        )
        assert a["sourceReuseReview"] == b["sourceReuseReview"]
        denied = await http.post(
            "/api/v1/resources/hydro/query", json={"parameters": PARAMETERS}
        )
        assert denied.status_code == 422
        assert denied.json()["error"]["code"] == "SOURCE_REUSE_REVIEW_REQUIRED"
        denied_mcp = await mcp.call_tool(
            "hk_resource_query",
            {"resourceId": "hydro", "parameters": PARAMETERS},
            raise_on_error=False,
        )
        assert denied_mcp.is_error
        assert "SOURCE_REUSE_REVIEW_REQUIRED" in " ".join(
            part.text for part in denied_mcp.content if hasattr(part, "text")
        )
