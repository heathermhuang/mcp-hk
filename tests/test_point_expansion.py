"""New reviewed point sources retain their own context and HTTP/MCP identity."""

import copy
import json

from fastapi.testclient import TestClient
from fastmcp import Client
import pytest

from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.spatial_profiles import profiles
from mcp_open_data_hk.storage import Store


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "kind", ["library", "museum", "fire_station", "ambulance_depot"]
)
async def test_expansion_source_context_and_discovery_parity(
    tmp_path, monkeypatch, kind
):
    from urllib.parse import urlencode

    profile = next(p for p in profiles() if p["entityKind"] == kind)
    resource = {
        "id": profile["resourceId"],
        "datasetId": profile["datasetId"],
        "format": "GEOJSON",
        "url": "https://"
        + profile["host"]
        + profile["path"]
        + "?"
        + urlencode({k: v[0] for k, v in profile["query"].items()}),
        "catalogue": "CSDI",
        "sourceUrl": profile["evidence"][0],
        "termsUrl": "https://portal.csdi.gov.hk/csdi-webpage/doc/TNC",
    }
    service = Service(Store(str(tmp_path / "points.sqlite3")))
    service.resources.catalogue.publish(
        [
            {
                "id": profile["datasetId"],
                "title": kind,
                "provider": "Example",
                "catalogue": "CSDI",
            }
        ],
        [resource],
        {},
    )
    properties = {
        field.removeprefix("properties."): (
            1 if field.endswith("OBJECTID") else "Synthetic label"
        )
        for field in profile["requiredFields"]
        if field.startswith("properties.")
    }
    properties.update(
        {
            field.removeprefix("properties."): value
            for field, value in profile["rowContext"].items()
        }
    )
    properties[profile["coordinates"]["propertyLatitude"].split(".")[1]] = 22.281
    properties[profile["coordinates"]["propertyLongitude"].split(".")[1]] = 114.15
    state = {
        **copy.deepcopy(profile["sourceContext"]),
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [114.15, 22.28]},
                "properties": properties,
            }
        ],
    }

    async def fetch(url, headers=None, **kwargs):
        assert url == resource["url"]
        return json.dumps(state).encode(), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    app = create_app(service)
    query = {"nearby": {"lat": 22.28, "lon": 114.15, "radiusM": 100}, "limit": 1}
    with TestClient(app) as http:
        response = http.post(
            "/api/v1/resources/" + resource["id"] + "/query", json=query
        )
        assert response.status_code == 200
        actual = response.json()
        search = http.get(
            "/api/v1/catalogue/datasets",
            params={"entityKind": kind, "capability": "nearby", "access": "sources"},
        )
        assert search.status_code == 200 and search.json()["total"] == 1
    async with Client(app.state.mcp) as mcp:
        call = await mcp.call_tool(
            "hk_resource_query", {"resourceId": resource["id"], **query}
        )
        assert json.loads(call.content[0].text)["data"] == actual["data"]
    binding = actual["schema"]["semanticBinding"]
    assert binding["state"] == "available"
    assert binding["coverage"]["geometryPropertyDisagreementsOver5M"] == 1
    assert actual["meta"]["nearby"]["uniqueFacilityCount"] is None
    assert actual["data"]["items"][0]["properties"] == properties
    state["name"] = "different source layer"
    from mcp_open_data_hk.review_config import SOURCE_REVIEW

    token = SOURCE_REVIEW.set(True)
    try:
        changed = await service.resources.schema(resource["id"], require_fresh=True)
    finally:
        SOURCE_REVIEW.reset(token)
    assert changed["schema"]["semanticBinding"]["state"] == "held"
    assert (
        changed["schema"]["semanticBinding"]["reason"]
        == "binding_source_context_changed"
    )
