"""Publisher-dependent input modes, raw coordinate preservation and error holds."""

import json
from urllib.parse import parse_qs, urlsplit

import pytest

from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.geodetic_requests import SPEC
from mcp_open_data_hk.resources import source_parameters, template_url
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store


@pytest.fixture
def service(tmp_path):
    service = Service(Store(str(tmp_path / "db.sqlite3")))
    service.resources.catalogue.publish(
        [
            {
                "id": "transform",
                "title": "Coordinate transformation",
                "provider": "LandsD",
            }
        ],
        [
            {
                "id": "transform-json",
                "datasetId": "transform",
                "format": "JSON",
                "url": SPEC.replace("https:", "http:") + "/",
                "sourceUrl": "https://data.gov.hk/",
                "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
                "catalogue": "DATA.GOV.HK",
            }
        ],
        {},
    )
    return service


CASES = [
    {
        "inSys": "wgsgeog",
        "lat": "22.32224",
        "long": "114.14118",
        "h": "23.128",
        "outSys": "hkgrid",
    },
    {"inSys": "hkgeog", "lat": "22.323774010", "long": "114.138734969"},
    {"inSys": "hkgrid", "e": "832591.320", "n": "820359.389"},
    {"inSys": "utmgrid", "zone": "50Q", "e": "205494", "n": "2471287"},
    {"inSys": "utmref", "zone": "50Q-KK", "e": "054", "n": "712", "outSys": "hkgrid"},
]


@pytest.mark.parametrize("parameters", CASES)
@pytest.mark.asyncio
async def test_every_published_system_binds_only_explicit_inputs(
    service, monkeypatch, parameters
):
    url = urlsplit(template_url(SPEC + "/", parameters))
    assert url.hostname == "www.geodetic.gov.hk" and url.path == "/transform/v2/"
    assert parse_qs(url.query) == {k: [v] for k, v in parameters.items()}
    assert source_parameters(SPEC + "/") == ["inSys"]
    result = {"wgsLat": 22.322244329, "wgsLong": 114.141187898}

    async def fetch(url, *a, **kw):
        return json.dumps(result).encode(), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    value = await service.resources.query("transform-json", parameters=parameters)
    assert value["data"]["items"] == [result]


@pytest.mark.parametrize(
    "unit,lat,lon",
    [("dms", "22.30405", "114.08405"), ("decMin", "22.30675", "114.08675")],
)
def test_sexagesimal_is_validated_in_its_declared_format_without_rewriting(
    unit, lat, lon
):
    parameters = {
        "inSys": "wgsgeog",
        "inUnit": unit,
        "lat": lat,
        "long": lon,
        "outUnit": "decDeg",
    }
    assert parse_qs(urlsplit(template_url(SPEC, parameters)).query) == {
        k: [v] for k, v in parameters.items()
    }


@pytest.mark.parametrize(
    "parameters",
    [
        {},
        {"inSys": "wgsgeog"},
        {"inSys": "hkgird", "e": "832591", "n": "820359"},
        {**CASES[0], "lat": "NaN"},
        {**CASES[0], "lat": "1e99999999", "inUnit": "dms"},
        {**CASES[0], "h": "10001"},
        {**CASES[0], "outSys": "wgsgeog"},
        {**CASES[0], "lat": "22.6"},
        {**CASES[0], "inUnit": "dms", "lat": "22.30605"},
        {**CASES[2], "e": "867501"},
        {**CASES[3], "zone": "49Q"},
        {**CASES[4], "e": "54"},
        {**CASES[4], "n": "0712"},
        {**CASES[4], "h": "1"},
        {**CASES[0], "endpoint": "https://other.invalid"},
    ],
)
@pytest.mark.asyncio
async def test_invalid_mode_is_rejected_without_contacting_provider(
    service, monkeypatch, parameters
):
    async def denied(*a, **kw):
        raise AssertionError("Invalid request must not reach a provider")

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", denied)
    with pytest.raises(DomainError):
        await service.resources.query("transform-json", parameters=parameters)


@pytest.mark.asyncio
async def test_discovery_and_results_keep_caller_context_separate(service, monkeypatch):
    calls = []
    result = {"hkN": 820358.910, "hkE": 832590.508, "hkpd": 26.009}

    async def fetch(url, *a, **kw):
        calls.append(url)
        return json.dumps(result).encode(), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    discovered = await service.resources.schema("transform-json")
    assert discovered["parameters"] == ["inSys"]
    assert len(discovered["sourceRequest"]["requiredParametersByInputSystem"]) == 5
    assert not calls
    value = await service.resources.query("transform-json", parameters=CASES[0])
    assert value["data"]["items"] == [result]
    assert value["schema"]["scope"] == "parameter_scoped_source_response"
    assert value["capabilities"]["operations"]["nearby"]["state"] != "available"
    assert (
        value["provenance"][0]["originalResourceUrl"]
        == SPEC.replace("https:", "http:") + "/"
    )
    discovered = await service.resources.schema("transform-json")
    assert discovered["parameters"] == ["inSys"] and discovered["selections"] == []
    assert len(calls) == 1
    assert service.resources.catalogue.selection_options("transform-json") == []


@pytest.mark.parametrize(
    "response",
    [{"ErrorCode": code} for code in range(1, 8)]
    + [{"ErrorCode": 1, "hkN": 820000}, {}, {"hkN": "820000"}],
)
@pytest.mark.asyncio
async def test_publisher_error_or_unknown_shape_cannot_be_accepted(
    service, monkeypatch, response
):
    async def fetch(url, *a, **kw):
        return json.dumps(response).encode(), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    with pytest.raises(DomainError) as error:
        await service.resources.query("transform-json", parameters=CASES[0])
    assert error.value.code in {"SOURCE_API_ERROR", "SOURCE_SCHEMA_CHANGED"}
    assert service.resources.catalogue.check("transform-json")["status"] != "queryable"


@pytest.mark.asyncio
async def test_reference_output_preserves_leading_zeroes(service, monkeypatch):
    result = {"utmRefZone": "50Q-KK", "utmRefE": "054", "utmRefN": "712"}

    async def fetch(url, *a, **kw):
        return json.dumps(result).encode(), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    value = await service.resources.query(
        "transform-json", parameters={**CASES[2], "outSys": "utmref"}
    )
    assert value["data"]["items"] == [result]
