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
            for fmt in ["XLSX", "WFS", "ARCGIS", "JSON"]
        ],
        {},
    )
    return service


@pytest.mark.asyncio
async def test_padded_workbook_records_match_http_mcp_and_restored_cache(
    service, monkeypatch, tmp_path
):
    import json

    from fastapi.testclient import TestClient
    from fastmcp import Client
    from openpyxl.styles import PatternFill

    from mcp_open_data_hk.api import create_app

    book = Workbook()
    book.active.append(["id", None, "value"])
    book.active.append(["001", None, "=1+1"])
    book.active.cell(1, 16384).fill = PatternFill("solid", fgColor="FFFF00")
    body = io.BytesIO()
    book.save(body)
    book.close()
    calls = []

    async def fetch(url, headers=None, **kwargs):
        calls.append(url)
        return body.getvalue(), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    app = create_app(service)
    with TestClient(app) as client:
        response = client.post("/api/v1/resources/XLSX/query", json={"sheet": "Sheet"})
        assert response.status_code == 200
        http = response.json()
    async with Client(app.state.mcp) as client:
        result = await client.call_tool(
            "hk_resource_query", {"resourceId": "XLSX", "sheet": "Sheet"}
        )
        mcp = json.loads(result.content[0].text)
    expected = [{"id": "001", "_column_2": None, "value": "=1+1"}]
    assert http["data"]["items"] == mcp["data"]["items"] == expected
    assert http["meta"]["total"] == mcp["meta"]["total"] == 1
    assert len(calls) == 1
    restored_path = str(tmp_path / "restored.sqlite3")
    with service.store.connect() as db, sqlite3.connect(restored_path) as restored:
        db.backup(restored)

    async def fail(*args, **kwargs):
        raise AssertionError("Restored accepted rows must use the saved cache")

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fail)
    recovered = Service(Store(restored_path))
    result = await recovered.resources.query("XLSX", sheet="Sheet")
    assert result["data"]["items"] == expected


@pytest.mark.asyncio
async def test_streamed_json_discovers_explicit_paths_then_queries_selected_records(
    service, monkeypatch, tmp_path
):
    import json

    from mcp_open_data_hk.contracts import DomainError

    body = json.dumps(
        {"data": {"records": [{"id": "001", "tags": ["a"]}]}, "other": []}
    ).encode()
    calls = []

    async def fetch(*args, **kwargs):
        raise DomainError("SOURCE_TOO_LARGE", "Use the bounded file reader", 422)

    async def fetch_file(url, *args, **kwargs):
        target = tmp_path / (str(len(calls)) + ".json")
        target.write_bytes(body)
        calls.append(target)
        return target, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    monkeypatch.setattr("mcp_open_data_hk.resources.fetch_file", fetch_file)
    result = await service.resources.schema("JSON")
    assert len(calls) == 1 and not calls[0].exists()
    assert result["selectionRequired"] == "recordPath"
    assert result["recordCount"] is None and not result["structuredQueryable"]
    group = result["selections"][0]
    assert [o["value"] for o in group["options"]] == ["data/records", "other"]
    assert all(o["state"] == "unverified" for o in group["options"])
    assert service.resources.catalogue.check("JSON")["status"] == "needs_selection"
    arguments = group["options"][0]["nextAction"]["arguments"]
    selected = await service.resources.query(
        arguments["resourceId"], record_path=arguments["recordPath"], limit=1
    )
    assert selected["meta"]["total"] == 1
    assert selected["data"]["items"] == [{"id": "001", "tags": ["a"]}]
    assert len(calls) == 2 and all(not p.exists() for p in calls)


def test_streamed_json_discovery_excludes_unaddressable_and_record_internal_arrays(
    tmp_path,
):
    import json

    from mcp_open_data_hk.resource_stream import object_array_paths
    from mcp_open_data_hk.resource_selections import describe

    body = {"data": [{"tags": [1]}], "bad.key": [], "0": [], "a/b": []}
    body.update({"table" + str(i): [] for i in range(101)})
    target = tmp_path / "choices.json"
    target.write_text(json.dumps(body))
    paths, unavailable = object_array_paths(target)
    assert unavailable == 3 and len(paths) == 102
    assert paths[0] == "data" and "data/tags" not in paths
    group = describe("JSON", {"schema": {"availableRecordPaths": paths}})[0]
    assert group["totalOptions"] == 102 and group["truncated"]
    assert len(group["options"]) == 100


@pytest.mark.parametrize(
    "body",
    [b'{"data":[],"data":[]}', b'{"data":[],"tail":', b'{"x":' * 31 + b"0" + b"}" * 31],
)
def test_streamed_json_discovery_validates_the_entire_document(tmp_path, body):
    import ijson

    from mcp_open_data_hk.contracts import DomainError
    from mcp_open_data_hk.resource_stream import FileRows

    target = tmp_path / "invalid.json"
    target.write_bytes(body)
    with pytest.raises((DomainError, ijson.JSONError)) as failure:
        FileRows(target, "JSON")
    assert not hasattr(failure.value, "record_paths")
    assert not target.exists()


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

    async def fetch(url, **kwargs):
        if "request=GetCapabilities" in url:
            body = '<wfs:WFS_Capabilities xmlns:wfs="http://www.opengis.net/wfs/2.0" xmlns:ows="http://www.opengis.net/ows/1.1"><ows:OperationsMetadata><ows:Operation name="GetFeature"><ows:Parameter name="outputFormat"><ows:AllowedValues><ows:Value>GEOJSON</ows:Value></ows:AllowedValues></ows:Parameter></ows:Operation></ows:OperationsMetadata></wfs:WFS_Capabilities>'
        else:
            assert "resultType=hits" in url
            body = '<wfs:FeatureCollection xmlns:wfs="http://www.opengis.net/wfs/2.0" numberMatched="0" numberReturned="0"/>'
        return body.encode(), {}, url, 200

    async def read_json(url, params=None):
        calls.append(params)
        assert params["service"] == "WFS"
        assert params["typeNames"] == "csdi:clinics"
        assert params["outputFormat"] == "GEOJSON"
        value = {"type": "FeatureCollection", "numberMatched": 0, "features": []}
        return value, json.dumps(value).encode(), {}, url

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
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


@pytest.mark.asyncio
async def test_parameter_scoped_actions_are_executable_without_publishing_values(
    service, monkeypatch
):
    import json
    from urllib.parse import parse_qs, urlsplit
    from fastmcp import Client
    from mcp_open_data_hk.api import create_app

    catalogue = service.resources.catalogue
    original = catalogue.resource
    monkeypatch.setattr(
        catalogue,
        "resource",
        lambda rid, generation=None: {
            **original(rid, generation),
            "format": "JSON",
            "url": "https://example.gov.hk/data?date=<date>",
            "isApi": True,
        },
    )
    old = [
        {
            "kind": "record_path",
            "argument": "recordPath",
            "options": [
                {
                    "value": "unrelated_old_path",
                    "label": "old",
                    "nextAction": {
                        "tool": "hk_resource_schema",
                        "arguments": {
                            "resourceId": "XLSX",
                            "recordPath": "unrelated_old_path",
                        },
                    },
                }
            ],
            "totalOptions": 1,
            "truncated": False,
        }
    ]
    catalogue.record_options("XLSX", old)
    before = catalogue.selection_options("XLSX")
    calls = []

    async def fetch(url, headers=None, **kwargs):
        calls.append(url)
        assert parse_qs(urlsplit(url).query)["date"] == ["2026-11-05"]
        return (
            json.dumps([{"native": "001"}]).encode(),
            {"content-type": "application/json"},
            url,
            200,
        )

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    async with Client(create_app(service).state.mcp) as client:
        response = json.loads(
            (
                await client.call_tool(
                    "hk_resource_schema",
                    {"resourceId": "XLSX", "parameters": {"date": "2026-11-05"}},
                )
            )
            .content[0]
            .text
        )
        action = response["selections"][0]["options"][0]["nextAction"]
        assert action["arguments"]["parameters"] == {"date": "2026-11-05"}
        followed = json.loads(
            (await client.call_tool(action["tool"], action["arguments"]))
            .content[0]
            .text
        )
        assert followed["recordCount"] == 1
    assert len(calls) == 1
    assert catalogue.selection_options("XLSX") == before
    assert "2026-11-05" not in json.dumps(catalogue.selection_options("XLSX"))
    missing = await service.resources.schema("XLSX")
    assert missing["selectionRequired"] == "parameters"
    assert missing["selections"] == []
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_parameterized_workbook_sheet_actions_keep_the_same_context(
    service, monkeypatch
):
    catalogue = service.resources.catalogue
    original = catalogue.resource
    monkeypatch.setattr(
        catalogue,
        "resource",
        lambda rid, generation=None: {
            **original(rid, generation),
            "url": "https://example.gov.hk/book.xlsx?date=<date>",
        },
    )
    book = Workbook()
    book.active.title = "Published"
    book.active.append(["id"])
    book.active.append(["001"])
    book.create_sheet("Other")
    body = io.BytesIO()
    book.save(body)

    async def fetch(url, headers=None, **kwargs):
        return body.getvalue(), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    result = await service.resources.schema("XLSX", parameters={"date": "2026-11-05"})
    action = result["selections"][0]["options"][0]["nextAction"]["arguments"]
    assert action == {
        "resourceId": "XLSX",
        "sheet": "Published",
        "parameters": {"date": "2026-11-05"},
    }
    selected = await service.resources.schema(
        "XLSX", sheet=action["sheet"], parameters=action["parameters"]
    )
    assert selected["recordCount"] == 1
    assert catalogue.selection_options("XLSX") == []


@pytest.mark.asyncio
async def test_discovery_does_not_ignore_undeclared_parameters(service, monkeypatch):
    from mcp_open_data_hk.contracts import DomainError

    catalogue = service.resources.catalogue
    original = catalogue.resource
    monkeypatch.setattr(
        catalogue,
        "resource",
        lambda rid, generation=None: {
            **original(rid, generation),
            "url": "https://www.censtatd.gov.hk/en/wbr.html?ecode=B10200082026MM09&download_excel=1",
        },
    )
    before = catalogue.check("XLSX")

    async def forbidden(*args, **kwargs):
        raise AssertionError("Invalid arguments must not contact the source")

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", forbidden)
    with pytest.raises(DomainError, match="PARAMETERS_REQUIRED"):
        await service.resources.schema("XLSX", parameters={"date": "2026-11-05"})
    assert catalogue.check("XLSX") == before
