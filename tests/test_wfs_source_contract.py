"""CSDI's advertised GeoJSON has no count: reconcile native WFS hits, not guesses."""

import gzip
import json
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

import pytest

from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.resources import wfs

URL = "https://portal.csdi.gov.hk/server/services/common/sample/MapServer/WFSServer"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "broken", [None, "format", "changed", "unknown", "short", "json_count", "row_bound"]
)
@pytest.mark.parametrize(
    "url",
    [
        URL,
        "https://www.ozp.tpb.gov.hk/arcgis/services/DATA/APP_AMEND_CSDI/MapServer/WFSServer",
    ],
)
async def test_advertised_format_and_before_after_counts_are_required(
    monkeypatch, broken, url
):
    calls = []
    counts = iter(
        [
            (
                "100001"
                if broken == "row_bound"
                else "unknown" if broken == "unknown" else "2"
            ),
            "3" if broken == "changed" else "2",
        ]
    )

    async def fetch(url, **kwargs):
        query = parse_qs(urlsplit(url).query)
        calls.append(query)
        if query["request"] == ["GetCapabilities"]:
            fmt = "GML32" if broken == "format" else "GEOJSON"
            body = f'<wfs:WFS_Capabilities xmlns:wfs="http://www.opengis.net/wfs/2.0" xmlns:ows="http://www.opengis.net/ows/1.1"><ows:OperationsMetadata><ows:Operation name="GetFeature"><ows:Parameter name="outputFormat"><ows:AllowedValues><ows:Value>{fmt}</ows:Value></ows:AllowedValues></ows:Parameter></ows:Operation></ows:OperationsMetadata></wfs:WFS_Capabilities>'
        else:
            assert query["resultType"] == ["hits"]
            assert query["typeNames"] == ["source:namespace"]
            body = f'<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" numberMatched="{next(counts)}" numberReturned="0"/>'
        return body.encode(), {}, url, 200

    async def read_json(url, params=None):
        assert params["outputFormat"] == "GEOJSON"
        assert params["count"] == 100000
        rows = [
            {"type": "Feature", "properties": {"ID": "001"}, "geometry": None},
            {"type": "Feature", "properties": {"ID": "002"}, "geometry": None},
        ]
        value = {
            "type": "FeatureCollection",
            "features": rows[:1] if broken == "short" else rows,
        }
        if broken == "json_count":
            value["numberMatched"] = True
        return value, json.dumps(value).encode(), {}, url

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    monkeypatch.setattr("mcp_open_data_hk.resources.read_json", read_json)
    if broken:
        with pytest.raises(DomainError) as error:
            await wfs(url, "source:namespace")
        expected = {
            "format": "UNSUPPORTED_API",
            "changed": "SOURCE_CHANGED",
            "row_bound": "SOURCE_TOO_LARGE",
        }.get(broken, "INCOMPLETE_SOURCE")
        assert error.value.code == expected
    else:
        body, _, _, extra = await wfs(url, "source:namespace")
        assert json.loads(body)["features"][0]["properties"]["ID"] == "001"
        assert extra["sourceMatched"] == 2
        assert (
            extra["countEvidence"]["beforeMatched"]
            == extra["countEvidence"]["afterMatched"]
            == 2
        )
        assert extra["countEvidence"]["jsonDeclaredMatched"] is None
        assert len(calls) == 3


@pytest.mark.asyncio
async def test_official_planning_selection_uses_declared_geojson(monkeypatch):
    fixtures = Path(__file__).parent / "fixtures" / "wfs-planning"

    def read(name):
        return gzip.decompress((fixtures / (name + ".gz")).read_bytes())

    calls = []
    counts = iter(["hits-before.xml", "hits-after.xml"])

    async def fetch(url, **kwargs):
        query = parse_qs(urlsplit(url).query)
        calls.append(query)
        name = (
            "capabilities.xml"
            if query["request"] == ["GetCapabilities"]
            else next(counts)
        )
        if name != "capabilities.xml":
            assert query["typeNames"] == ["APP_AMEND_CSDI:AMEND_CRT"]
        return read(name), {}, url, 200

    async def read_json(url, params):
        assert params["outputFormat"] == "GEOJSON"
        assert params["typeNames"] == "APP_AMEND_CSDI:AMEND_CRT"
        body = read("geojson.json")
        return json.loads(body), body, {}, url

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    monkeypatch.setattr("mcp_open_data_hk.resources.read_json", read_json)
    body, _, _, extra = await wfs(
        "https://www.ozp.tpb.gov.hk/arcgis/services/DATA/APP_AMEND_CSDI/MapServer/WFSServer",
        "APP_AMEND_CSDI:AMEND_CRT",
    )
    assert len(json.loads(body)["features"]) == extra["sourceMatched"] == 16
    assert extra["wfsContract"] == "wfs-2-count-1"
    assert (
        extra["countEvidence"]["beforeMatched"]
        == extra["countEvidence"]["afterMatched"]
        == 16
    )
    assert len(calls) == 3


@pytest.mark.asyncio
async def test_negotiation_does_not_retry_provider_denial(monkeypatch):
    calls = []

    async def denied(url, **kwargs):
        calls.append(url)
        raise DomainError("ACCESS_RESTRICTED", "Provider denied access", 502)

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", denied)
    with pytest.raises(DomainError, match="ACCESS_RESTRICTED"):
        await wfs(
            "https://www.ozp.tpb.gov.hk/arcgis/services/DATA/APP_AMEND_CSDI/MapServer/WFSServer",
            "APP_AMEND_CSDI:AMEND_CRT",
        )
    assert len(calls) == 1
