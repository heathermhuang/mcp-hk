"""Options are bounded source metadata and cannot clear source failures."""

import io
import sqlite3

import pytest
from openpyxl import Workbook

from mcp_open_data_hk.catalogue_store import CatalogueStore
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store


@pytest.fixture
def service(tmp_path):
    service = Service(Store(str(tmp_path / "db.sqlite3")))
    service.resources.catalogue.publish(
        [{"id": "d", "title": "d", "provider": "Example", "catalogue": "DATA.GOV.HK"}],
        [
            {
                "id": fmt,
                "datasetId": "d",
                "format": fmt,
                "url": "https://example.gov.hk/"
                + ("FeatureServer" if fmt == "ARCGIS" else fmt),
                "sourceUrl": "https://example.gov.hk/",
                "termsUrl": "https://example.gov.hk/terms",
                "catalogue": "DATA.GOV.HK",
            }
            for fmt in ["XLSX", "WFS", "ARCGIS"]
        ],
        {},
    )
    return service


@pytest.mark.asyncio
async def test_sheet_options_are_typed_persisted_and_failure_is_preserved(
    service, monkeypatch
):
    book = Workbook()
    book.active.title = "2025"
    book.active.append(["id"])
    book.active.append(["001"])
    book.create_sheet("2026")
    body = io.BytesIO()
    book.save(body)

    async def fetch(url, headers=None, **kwargs):
        return body.getvalue(), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    catalogue = service.resources.catalogue
    catalogue.failure("XLSX", "SOURCE_UNAVAILABLE")
    result = await service.resources.schema("XLSX")
    assert result["selectionRequired"] == "sheet"
    option = result["selections"][0]["options"][0]
    assert option["value"] == "2025"
    assert option["nextAction"]["arguments"] == {"resourceId": "XLSX", "sheet": "2025"}
    assert option["state"] == "unverified"
    assert catalogue.check("XLSX")["reason"] == "SOURCE_UNAVAILABLE"
    assert (
        CatalogueStore(service.store).selection_options("XLSX") == result["selections"]
    )
    with service.store.connect() as db:

        restored = sqlite3.connect(service.store.path + ".copy")
        db.backup(restored)
        restored.close()
    assert (
        CatalogueStore(Store(service.store.path + ".copy")).selection_options("XLSX")
        == result["selections"]
    )
    accepted = await service.resources.schema("XLSX", sheet="2025")
    assert accepted["recordCount"] == 1
    assert catalogue.check("XLSX")["status"] == "queryable"
    from mcp_open_data_hk.contracts import DomainError

    with pytest.raises(DomainError, match="INVALID_SHEET"):
        await service.resources.schema("XLSX", sheet="invalid-default")
    assert catalogue.check("XLSX")["status"] == "queryable"
    catalogue.failure("XLSX", "SOURCE_UNAVAILABLE")
    with pytest.raises(DomainError, match="INVALID_SHEET"):
        await service.resources.schema("XLSX", sheet="another-invalid-default")
    assert catalogue.check("XLSX")["reason"] == "SOURCE_UNAVAILABLE"


@pytest.mark.asyncio
async def test_wfs_only_feature_type_names_and_failure_survives(service, monkeypatch):
    async def fetch(url, headers=None, **kwargs):
        return (
            b"<WFS_Capabilities><ServiceIdentification><Name>not-a-type</Name></ServiceIdentification><FeatureTypeList><FeatureType><Name>ns:clinics</Name></FeatureType><FeatureType><Name>ns:schools</Name></FeatureType></FeatureTypeList></WFS_Capabilities>",
            {},
            url,
            200,
        )

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    service.resources.catalogue.failure("WFS", "ACCESS_RESTRICTED", "restricted")
    result = await service.resources.schema("WFS")
    group = result["selections"][0]
    assert group["kind"] == "feature_type"
    assert [x["value"] for x in group["options"]] == ["ns:clinics", "ns:schools"]
    assert group["options"][0]["nextAction"]["arguments"]["recordPath"] == "ns:clinics"
    assert service.resources.catalogue.check("WFS")["status"] == "restricted"


@pytest.mark.asyncio
async def test_layer_options_have_integer_ids_and_no_implicit_default(
    service, monkeypatch
):
    async def read_json(*args, **kwargs):
        return (
            {
                "layers": [
                    {"id": 0, "name": "Points"},
                    {"id": 1, "name": "Polygons"},
                    {"id": "2", "name": "bad type"},
                ]
            },
            {},
            "",
            200,
        )

    monkeypatch.setattr("mcp_open_data_hk.resources.read_json", read_json)
    result = await service.resources.schema("ARCGIS")
    options = result["selections"][0]["options"]
    assert [x["value"] for x in options] == [0, 1]
    assert options[0]["nextAction"]["arguments"]["layer"] == 0
    assert result["selections"][0]["truncated"]
    assert not result["structuredQueryable"]


def test_option_metadata_has_an_independent_global_byte_bound(service, monkeypatch):
    from mcp_open_data_hk import resource_selections

    monkeypatch.setattr(resource_selections, "MAX_BYTES", 200)
    catalogue = service.resources.catalogue
    for i in range(50):
        catalogue.record_options(
            str(i), [{"kind": "sheet", "options": [{"value": str(i)}]}]
        )
    with service.store.connect() as db:
        assert (
            db.execute(
                "SELECT sum(length(payload)) FROM resource_selection_options"
            ).fetchone()[0]
            <= 200
        )
    assert catalogue.selection_options("0") == []
    assert catalogue.check("XLSX") == {}


@pytest.mark.asyncio
async def test_null_prior_check_time_does_not_hide_a_real_capabilities_source_failure(
    service, monkeypatch
):
    from mcp_open_data_hk.contracts import DomainError

    with service.store.connect() as db:
        db.execute("INSERT INTO resource_checks(id,status) VALUES ('WFS','pending')")

    async def fail(*args, **kwargs):
        raise DomainError("SOURCE_UNAVAILABLE", "Provider unavailable", 502)

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fail)
    with pytest.raises(DomainError, match="SOURCE_UNAVAILABLE"):
        await service.resources.schema("WFS")
    assert service.resources.catalogue.check("WFS")["status"] == "unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize("csv_feature_request", [False, True])
async def test_arcgis_hosted_wfs_selected_read_uses_wfs_not_rest_layer(
    service, monkeypatch, csv_feature_request
):
    import json

    catalogue = service.resources.catalogue
    original = catalogue.resource
    monkeypatch.setattr(
        catalogue,
        "resource",
        lambda rid: {
            **original(rid),
            "format": "CSV" if csv_feature_request else "WFS",
            "url": "https://example.gov.hk/server/services/common/clinics/MapServer/WFSServer?service=wfs&"
            + (
                "request=GetFeature&typename=csdi:clinics&outputFormat=CSV"
                if csv_feature_request
                else "request=GetCapabilities"
            ),
        },
    )
    calls = []

    async def read_json(url, params=None):
        calls.append(params)
        assert params["service"] == "WFS"
        assert params["typeNames"] == "csdi:clinics"
        value = {"type": "FeatureCollection", "numberMatched": 0, "features": []}
        return value, json.dumps(value).encode(), {}, url

    monkeypatch.setattr("mcp_open_data_hk.resources.read_json", read_json)
    result = await service.resources.schema(
        "WFS", record_path="" if csv_feature_request else "csdi:clinics"
    )
    assert result["recordCount"] == 0
    assert result["schema"]["apiFamily"] == "WFS"
    assert result["schema"]["sourceSelection"]["recordPath"] == "csdi:clinics"
    assert len(calls) == 1
    from mcp_open_data_hk.capabilities import family

    assert family(catalogue.resource("WFS")) == "wfs"
    if csv_feature_request:
        from mcp_open_data_hk.contracts import DomainError

        with pytest.raises(DomainError, match="INVALID_RECORD_PATH"):
            await service.resources.query("WFS", record_path="other:clinics")


@pytest.mark.asyncio
async def test_ogc_scope_is_not_silently_broadened_or_treated_as_rest(
    service, monkeypatch
):
    from mcp_open_data_hk.contracts import DomainError
    from mcp_open_data_hk.capabilities import family
    from mcp_open_data_hk.resource_protocols import pinned_feature_type

    original = service.resources.catalogue.resource("WFS")
    scoped = {
        **original,
        "format": "CSV",
        "url": "https://example.gov.hk/MapServer/WFSServer?service=WFS&request=GetFeature&typename=ns:clinic&bbox=1,2,3,4",
    }
    with pytest.raises(DomainError, match="UNSUPPORTED_API"):
        pinned_feature_type(scoped)
    imagery = {
        **original,
        "format": "PNG",
        "url": "https://example.gov.hk/MapServer/WMSServer?service=WMS&request=GetMap",
    }
    assert family(imagery) == "map_imagery"
    monkeypatch.setattr(service.resources.catalogue, "resource", lambda rid: imagery)
    with pytest.raises(DomainError, match="INVALID_QUERY"):
        await service.resources.schema("WFS")
    assert service.resources.catalogue.check("WFS") == {}
