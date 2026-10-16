"""Contracts for inventory completeness, source parsing, query safety and recovery."""

import io
import json
import socket

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client
from openpyxl import Workbook

from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.catalogue_store import unpack
from mcp_open_data_hk.catalogue_sync import (
    Harvester,
    normalise_resources,
    provider_type,
)
from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.resource_fetch import public_addresses, validate_url
from mcp_open_data_hk.resource_formats import parse
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store


@pytest.fixture
def resource_service(tmp_path):
    service = Service(Store(str(tmp_path / "data.sqlite3")))
    service.resources.catalogue.publish(
        [
            {
                "id": "sample",
                "title": "Sample",
                "catalogue": "DATA.GOV.HK",
                "provider": "Example Department",
                "providerType": "government",
                "sourceUrl": "https://data.gov.hk/en-data/dataset/sample",
                "referencePeriod": None,
            }
        ],
        [
            {
                "id": "r1",
                "datasetId": "sample",
                "format": "CSV",
                "url": "https://www.example.gov.hk/data.csv",
                "sourceUrl": "https://data.gov.hk/en-data/dataset/sample",
                "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
                "catalogue": "DATA.GOV.HK",
                "aliases": [],
            }
        ],
        {},
    )
    return service


def test_csv_bilingual_big5_missing_and_identifiers():
    rows, schema = parse(
        "id,名稱,amount\r\n001,中文,\r\n002,街道,1.2\r\n".encode("big5"), "CSV"
    )
    assert rows == [
        {"id": "001", "名稱": "中文", "amount": ""},
        {"id": "002", "名稱": "街道", "amount": "1.2"},
    ]
    assert schema["encoding"] == "big5hkscs"
    assert all(f["unit"] is None for f in schema["fields"])
    duplicate, schema = parse(b"id,id\n1,2\n", "CSV")
    assert duplicate == [{"_column_1": "1", "_column_2": "2"}]
    assert [c["sourceHeader"] for c in schema["sourceColumns"]] == ["id", "id"]
    ragged, schema = parse(b"id,name\n1,x,y\n", "CSV")
    assert ragged == [{"id": "1", "name": "x", "_column_3": "y"}]


def test_json_paths_nested_units_and_geojson():
    body = json.dumps(
        {
            "units": "thousands",
            "data": [{"value": 3, "nested": {"x": [1, 2]}}],
            "other": [1, 2],
        }
    ).encode()
    rows, schema = parse(body, "JSON")
    assert rows[0]["units"] == "thousands"
    assert schema["scope"] == "source_response_object"
    rows, schema = parse(body, "JSON", "data")
    assert rows[0]["nested"] == {"x": [1, 2]}
    assert schema["availableRecordPaths"] == ["data", "data/0/nested/x", "other"]
    assert schema["sourceContext"]["units"] == "thousands"
    geo = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "properties": {"id": "001"},
                "geometry": {"type": "Point", "coordinates": [114, 22]},
            }
        ],
    }
    rows, _ = parse(json.dumps(geo).encode(), "GEOJSON")
    assert rows[0]["geometry"]["coordinates"] == [114, 22]
    with pytest.raises(DomainError):
        parse(b'{"x":1,"x":2}', "JSON")
    with pytest.raises(DomainError):
        parse(b'{"x":NaN}', "JSON")


def test_excel_selects_sheet_and_preserves_formulas():
    book = Workbook()
    book.active.append(["id", "amount"])
    book.active.append(["001", "=1+1"])
    book.create_sheet("Other")
    out = io.BytesIO()
    book.save(out)
    with pytest.raises(DomainError, match="SHEET_REQUIRED"):
        parse(out.getvalue(), "XLSX")
    rows, schema = parse(out.getvalue(), "XLSX", sheet="Sheet")
    assert rows[0] == {"id": "001", "amount": "=1+1"}
    assert schema["availableSheets"] == ["Sheet", "Other"]


def test_xml_preserves_namespace_attributes_repeated_values_and_denies_entities():
    rows, _ = parse(
        b'<root xmlns:x="urn:x"><x:row id="001"><x:v>1</x:v><x:v>2</x:v></x:row></root>',
        "XML",
    )
    assert rows == [{"@id": "001", "{urn:x}v": ["1", "2"]}]
    with pytest.raises(Exception):
        parse(
            b'<!DOCTYPE x [<!ENTITY private SYSTEM "file:///etc/passwd">]><x>&private;</x>',
            "XML",
        )


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "https://user:pass@example.com/",
        "http://127.0.0.1:8080/",
        "https://example.com/\nHost:x",
        "https://example.com/a#b",
        "https://example.com\\@localhost/",
    ],
)
def test_source_url_boundary(url):
    with pytest.raises(DomainError):
        validate_url(url)


def test_dns_guard_rejects_mixed_private_answer(monkeypatch):
    monkeypatch.setattr(
        socket,
        "getaddrinfo",
        lambda *a, **k: [
            (2, 1, 6, "", ("1.1.1.1", 443)),
            (2, 1, 6, "", ("127.0.0.1", 443)),
        ],
    )
    with pytest.raises(DomainError, match="UNSAFE_SOURCE"):
        public_addresses("example.com", 443)


def test_aliases_and_provider_classification():
    resources = normalise_resources(
        {
            "name": "d",
            "resources": [
                {
                    "id": "en",
                    "url": "https://EXAMPLE.gov.hk/x.csv",
                    "format": "CSV",
                    "inLanguage": "en",
                },
                {
                    "id": "tc",
                    "url": "https://example.gov.hk/x.csv",
                    "format": "CSV",
                    "inLanguage": "tc",
                },
                {
                    "id": "other",
                    "url": "https://example.gov.hk/tc.csv",
                    "format": "CSV",
                },
            ],
        }
    )
    assert len(resources) == 2
    assert sorted(len(r["aliases"]) for r in resources) == [1, 2]
    assert provider_type("Transport Department") == "government"
    assert provider_type("MTR Corporation Limited") != "government"
    assert provider_type("Hospital Authority") == "unclassified"


def test_atomic_inventory_rejects_orphans_and_large_drop(resource_service):
    catalogue = resource_service.resources.catalogue
    old = catalogue.head()
    with pytest.raises(ValueError):
        catalogue.publish(
            [{"id": "d"}], [{"id": "r", "datasetId": "missing", "format": "CSV"}], {}
        )
    assert catalogue.head() == old
    assert catalogue.coverage()["resources"]["byStatus"] == {"pending": 1}
    assert catalogue.coverage()["allGovernmentDataConnected"] is False


@pytest.mark.asyncio
async def test_query_projection_pagination_cache_parity(resource_service, monkeypatch):
    calls = []

    async def source(url, headers=None):
        calls.append(url)
        return b"id,name\n001,one\n002,two\n003,one\n", {"etag": "v1"}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", source)
    resource = resource_service.resources
    result = await resource.query("r1", filters={"name": "one"}, fields=["id"], limit=1)
    assert result["data"]["items"] == [{"id": "001"}]
    assert result["meta"]["total"] == 2 and result["meta"]["nextOffset"] == 1
    later = await resource.query(
        "r1",
        filters={"name": "one"},
        offset=1,
        limit=1,
        version=result["meta"]["version"],
    )
    assert later["data"]["items"][0]["id"] == "003"
    assert len(calls) == 1
    with pytest.raises(DomainError, match="UNKNOWN_FIELD"):
        await resource.query("r1", fields=["notfield"])
    with pytest.raises(DomainError, match="RESOURCE_VERSION_CHANGED"):
        await resource.query("r1", version="old")
    app = create_app(resource_service)
    with TestClient(app) as http:
        assert (
            http.get("/api/v1/resources/r1/records?limit=1").json()["data"]["items"][0][
                "id"
            ]
            == "001"
        )
        rest = http.post(
            "/api/v1/resources/r1/query",
            json={"filters": {"name": "one"}, "fields": ["id"], "limit": 1},
        ).json()
        assert http.get("/api/v1/coverage").json()["resources"]["byStatus"] == {
            "queryable": 1
        }
        assert (
            http.post("/api/v1/resources/r1/query", json={"limit": 101}).status_code
            == 400
        )
    async with Client(app.state.mcp) as mcp:
        reply = await mcp.call_tool(
            "hk_resource_query",
            {
                "resourceId": "r1",
                "filters": {"name": "one"},
                "fields": ["id"],
                "limit": 1,
            },
        )
        assert reply.data["data"] == rest["data"]
        assert reply.data["provenance"] == rest["provenance"]


@pytest.mark.asyncio
async def test_failed_refresh_retains_accepted_data_and_exposes_staleness(
    resource_service, monkeypatch
):
    async def good(url, headers=None):
        return b"id\n001\n", {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", good)
    resources = resource_service.resources
    original = await resources.query("r1")
    with resource_service.store.connect() as db:
        db.execute("UPDATE resource_variants SET validated=0")

    async def bad(url, headers=None):
        raise DomainError("SOURCE_UNAVAILABLE", "offline", 502)

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", bad)
    result = await resources.query("r1")
    assert result["data"] == original["data"] and result["warnings"]
    assert result["provenance"][0]["stale"]
    with pytest.raises(DomainError):
        await resources.query("r1", require_fresh=True)


@pytest.mark.asyncio
async def test_schema_drift_retains_previous_and_variant_isolation(
    resource_service, monkeypatch
):
    body = b'{"left":[{"a":"001"}],"right":[{"b":2}]}'

    async def source(url, headers=None):
        return body, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", source)
    with resource_service.store.connect() as db:
        r = unpack(db.execute("SELECT payload FROM inventory_resources").fetchone()[0])
        r["format"] = "JSON"
        db.execute("UPDATE inventory_resources SET payload=?", (json.dumps(r),))
    resources = resource_service.resources
    a = await resources.query("r1", record_path="left")
    b = await resources.query("r1", record_path="right")
    assert a["data"]["items"] == [{"a": "001"}] and b["data"]["items"] == [{"b": 2}]
    with resource_service.store.connect() as db:
        db.execute("UPDATE resource_variants SET validated=0")
    body = b'{"left":[{"new":"001"}],"right":[{"b":2}]}'
    result = await resources.query("r1", record_path="left")
    assert result["warnings"] and result["data"] == a["data"]
    assert resources.catalogue.check("r1")["reason"] == "SCHEMA_DRIFT"


@pytest.mark.asyncio
async def test_arcgis_rejects_truncated_page(monkeypatch):
    from mcp_open_data_hk.resources import arcgis

    async def read(url, params=None):
        value = (
            {"objectIdField": "OBJECTID"}
            if not url.endswith("query")
            else (
                {"objectIds": [1, 2]}
                if params.get("returnIdsOnly")
                else {
                    "features": [{"attributes": {"OBJECTID": 1}}],
                    "exceededTransferLimit": True,
                }
            )
        )
        return value, b"{}", {}, url

    monkeypatch.setattr("mcp_open_data_hk.resources.read_json", read)
    with pytest.raises(DomainError, match="INCOMPLETE_SOURCE"):
        await arcgis("https://portal.csdi.gov.hk/test/FeatureServer/0", None)


@pytest.mark.asyncio
async def test_csdi_capped_or_duplicate_enumeration_is_rejected(tmp_path, monkeypatch):
    h = Harvester(tmp_path)

    async def capped(*args):
        return b'<csw:GetRecordsResponse xmlns:csw="http://www.opengis.net/cat/csw/2.0.2"><csw:SearchResults numberOfRecordsMatched="2" numberOfRecordsReturned="1"><csw:Record/></csw:SearchResults></csw:GetRecordsResponse>'

    monkeypatch.setattr(h, "read", capped)
    with pytest.raises(ValueError, match="capped"):
        await h.csdi()


def test_zip_members_are_bounded_and_keep_member_provenance():
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as z:
        z.writestr("../first.csv", "id,name\n001,one\n")
        z.writestr("second.json", '[{"id":"002","name":"two"}]')
        z.writestr("notes.bin", b"ignored")
    rows, schema = parse(buffer.getvalue(), "ZIP")
    assert [r["id"] for r in rows] == ["001", "002"]
    assert rows[0]["_sourceArchiveMember"] == "../first.csv"
    assert schema["unreadMembers"] == ["notes.bin"]
    assert schema["scope"] == "supported_archive_members"


def test_pdf_pages_are_unverified_and_keep_page_numbers():
    from pypdf import PdfWriter

    out = io.BytesIO()
    writer = PdfWriter()
    writer.add_blank_page(width=300, height=300)
    writer.write(out)
    rows, schema = parse(out.getvalue(), "PDF")
    assert rows == [{"page": 1, "text": ""}]
    assert schema["structuredQueryable"] is False
    assert schema["verification"] == "unverified_text_extraction"
    assert schema["emptyPages"] == [1]


@pytest.mark.asyncio
async def test_conditional_unchanged_keeps_retrieval_timestamp(
    resource_service, monkeypatch
):
    calls = []

    async def source(url, headers=None):
        calls.append(headers)
        if len(calls) == 1:
            return b"id\n001\n", {"etag": "same"}, url, 200
        return b"", {"etag": "same"}, url, 304

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", source)
    original = await resource_service.resources.query("r1")
    with resource_service.store.connect() as db:
        db.execute("UPDATE resource_variants SET validated=0")
    updated = await resource_service.resources.query("r1")
    assert calls[1] == {"If-None-Match": "same"}
    assert (
        updated["provenance"][0]["retrievedAt"]
        == original["provenance"][0]["retrievedAt"]
    )
    assert updated["meta"]["version"] == original["meta"]["version"]


@pytest.mark.asyncio
async def test_wfs_rejects_unproved_total(monkeypatch):
    from mcp_open_data_hk.resources import wfs

    async def read(url, params=None):
        return {"features": [{}], "numberMatched": 2}, b"{}", {}, url

    monkeypatch.setattr("mcp_open_data_hk.resources.read_json", read)
    with pytest.raises(DomainError, match="INCOMPLETE_SOURCE"):
        await wfs("https://portal.csdi.gov.hk/wfs", "example:layer")


def test_catalogued_parameter_templates_keep_the_fixed_origin_and_escape_values():
    from mcp_open_data_hk.resources import template_url

    assert (
        template_url(
            "https://data.etagmb.gov.hk/stop/{stop_id}", {"stop_id": "20001234"}
        )
        == "https://data.etagmb.gov.hk/stop/20001234"
    )
    assert template_url("https://example.gov.hk/<id>", {"id": "../x?q=1"}).endswith(
        "..%2Fx%3Fq%3D1"
    )
    with pytest.raises(DomainError, match="PARAMETERS_REQUIRED"):
        template_url("https://example.gov.hk/{id}", {})
    with pytest.raises(DomainError, match="UNSAFE_SOURCE"):
        template_url("https://{host}/data", {"host": "127.0.0.1"})
    with pytest.raises(DomainError, match="ACCESS_RESTRICTED"):
        template_url("https://example.gov.hk/{api_key}", {"api_key": "secret"})
