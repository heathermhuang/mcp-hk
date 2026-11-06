"""A published API specification is not itself the JSON record endpoint."""

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.published_requests import LOCATION_SEARCH_SPEC, request_template
from mcp_open_data_hk.resources import source_parameters, template_url
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store


@pytest.fixture
def service(tmp_path):
    service = Service(Store(str(tmp_path / "db.sqlite3")))
    service.resources.catalogue.publish(
        [{"id": "locations", "title": "Location Search API", "provider": "LandsD"}],
        [
            {
                "id": "locations-json",
                "datasetId": "locations",
                "format": "JSON",
                "isApi": False,
                "url": LOCATION_SEARCH_SPEC,
                "sourceUrl": "https://data.gov.hk/",
                "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
                "catalogue": "DATA.GOV.HK",
            }
        ],
        {},
    )
    return service


def test_exact_published_binding_requires_q_and_encodes_only_its_value():
    assert source_parameters(LOCATION_SEARCH_SPEC) == ["q"]
    value = "文化中心 & name=other#fragment"
    result = urlsplit(template_url(LOCATION_SEARCH_SPEC, {"q": value}))
    assert result.hostname == "www.map.gov.hk"
    assert result.path == "/gs/api/v1.0.0/locationSearch"
    assert parse_qs(result.query) == {"q": [value]}
    assert not result.fragment
    for parameters in [{}, {"q": ""}, {"q": "x", "version": "v2"}]:
        with pytest.raises(DomainError):
            template_url(LOCATION_SEARCH_SPEC, parameters)
    for other in [LOCATION_SEARCH_SPEC + "Other", LOCATION_SEARCH_SPEC + "?q=x"]:
        assert request_template(other) == other


@pytest.mark.asyncio
async def test_lookup_is_caller_scoped_and_keeps_native_coordinates(
    service, monkeypatch
):
    calls = []
    # Publisher example field names; values stay raw and do not become GeoAddress IDs.
    records = [{"nameEN": "Public cultural centre", "x": 835599.0, "y": 817190.0}]

    async def fetch(url, *args, **kwargs):
        calls.append(url)
        return json.dumps(records).encode(), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    missing = await service.resources.schema("locations-json")
    assert missing["selectionRequired"] == "parameters"
    assert missing["parameters"] == ["q"] and missing["selections"] == []
    assert not calls
    parameters = {"q": "caller-only cultural centre"}
    result = await service.resources.query(
        "locations-json", parameters=parameters, limit=1
    )
    assert result["data"]["items"] == records
    assert result["schema"]["scope"] == "parameter_scoped_source_response"
    assert result["schema"]["coordinateQualification"] == "unreviewed_native_values"
    assert result["schema"]["cacheTTLSeconds"] == 300
    assert result["capabilities"]["operations"]["nearby"]["state"] != "available"
    assert result["provenance"][0]["originalResourceUrl"] == LOCATION_SEARCH_SPEC
    assert parse_qs(urlsplit(calls[0]).query) == {"q": [parameters["q"]]}
    selected = await service.resources.schema("locations-json", parameters=parameters)
    for group in selected["selections"]:
        for option in group["options"]:
            assert option["nextAction"]["arguments"]["parameters"] == parameters
    assert service.resources.catalogue.selection_options("locations-json") == []
    assert "caller-only" not in json.dumps(
        service.resources.catalogue.capability("locations-json")
    )
    before = len(calls)
    missing = await service.resources.schema("locations-json")
    assert missing["parameters"] == ["q"] and missing["selections"] == []
    assert len(calls) == before


@pytest.mark.asyncio
async def test_parameter_discovery_cannot_clear_an_upstream_denial(
    service, monkeypatch
):
    async def denied(*args, **kwargs):
        raise DomainError("ACCESS_RESTRICTED", "Source returned HTTP 403", 502)

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", denied)
    with pytest.raises(DomainError, match="ACCESS_RESTRICTED"):
        await service.resources.query(
            "locations-json", parameters={"q": "public place"}
        )
    result = await service.resources.schema("locations-json")
    assert result["selectionRequired"] == "parameters"
    assert service.resources.catalogue.check("locations-json")["reason"] == (
        "ACCESS_RESTRICTED"
    )
