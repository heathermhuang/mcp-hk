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


def test_streamed_json_validates_every_record_and_keeps_nested_values(tmp_path):
    from mcp_open_data_hk.resource_stream import FileRows

    path = tmp_path / "source"
    path.write_text(
        json.dumps(
            {
                "data": [
                    {"id": str(i).zfill(5), "unit": "thousands", "nested": {"x": i}}
                    for i in range(12000)
                ]
            }
        )
    )
    rows = FileRows(path, "JSON", "data")
    assert len(rows) == 12000
    assert next(iter(rows)) == {"id": "00000", "unit": "thousands", "nested": {"x": 0}}
    assert rows.schema["scope"] == "complete_streamed_file"
    assert all(f["unit"] is None for f in rows.schema["fields"])
    rows.close()
    assert not path.exists()


def test_streamed_json_rejects_truncation_duplicate_keys_and_wrong_paths(tmp_path):
    from mcp_open_data_hk.resource_stream import FileRows

    for body, path in [
        (b'[{"id":1}', ""),
        (b'[{"id":1,"id":2}]', ""),
        (b'{"data":[]}', "missing"),
    ]:
        target = tmp_path / "source"
        target.write_bytes(body)
        with pytest.raises(Exception):
            FileRows(target, "JSON", path)


def test_streamed_csv_retains_big5_and_duplicate_headers(tmp_path):
    from mcp_open_data_hk.resource_stream import FileRows

    path = tmp_path / "source"
    path.write_bytes("id,名稱,名稱\n001,中文,街道\n".encode("big5"))
    rows = FileRows(path, "CSV")
    assert list(rows) == [{"id": "001", "_column_2": "中文", "_column_3": "街道"}]
    assert rows.schema["sourceColumns"][1]["sourceHeader"] == "名稱"
    rows.close()


@pytest.mark.asyncio
async def test_large_resource_queries_scan_all_matches_and_pin_selected_records(
    resource_service, tmp_path, monkeypatch
):
    async def small(url, headers=None):
        raise DomainError("SOURCE_TOO_LARGE", "use stream", 422)

    async def large(url):
        path = tmp_path / "stream.source"
        path.write_text("id,name\n" + "".join(f"{i:05},same\n" for i in range(5000)))
        return path, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", small)
    monkeypatch.setattr("mcp_open_data_hk.resources.fetch_file", large)
    first = await resource_service.resources.query(
        "r1", filters={"name": "same"}, fields=["id"], limit=1
    )
    second = await resource_service.resources.query(
        "r1",
        filters={"name": "same"},
        fields=["id"],
        limit=1,
        offset=1,
        version=first["meta"]["version"],
    )
    assert first["meta"]["total"] == 5000
    assert first["data"]["items"] == [{"id": "00000"}] and second["data"]["items"] == [
        {"id": "00001"}
    ]
    assert resource_service.resources.catalogue.coverage()["cache"]["bytes"] == 0


@pytest.mark.asyncio
async def test_census_download_page_adapter_requires_complete_count(monkeypatch):
    from mcp_open_data_hk.resources import census_table

    seen = []

    async def good(url, params=None):
        seen.append(url)
        value = {
            "header": {"status": {"code": 0}, "count": {"noOfRecords": 2}},
            "dataSet": [
                {"figure": 1, "svDesc": "HK$ million"},
                {"figure": 2, "svDesc": "HK$ million"},
            ],
        }
        return value, json.dumps(value).encode(), {}, url

    monkeypatch.setattr("mcp_open_data_hk.resources.read_json", good)
    _, _, _, schema = await census_table(
        "https://www.censtatd.gov.hk/tc/web_table.html?id=645-75013&download_csv=1"
    )
    assert "lang=tc" in seen[0] and "full_series=1" in seen[0]
    assert (
        schema["sourceMatched"] == 2
        and schema["accessMethod"] == "official_json_equivalent_for_download_page"
    )

    async def bad(url, params=None):
        return (
            {
                "header": {"status": {"code": 0}, "count": {"noOfRecords": 3}},
                "dataSet": [{}],
            },
            b"{}",
            {},
            url,
        )

    monkeypatch.setattr("mcp_open_data_hk.resources.read_json", bad)
    with pytest.raises(DomainError, match="INCOMPLETE_SOURCE"):
        await census_table("https://www.censtatd.gov.hk/en/web_table.html?id=645-75013")


def test_streamed_fetch_redirect_keeps_private_temp_destination(tmp_path, monkeypatch):
    from mcp_open_data_hk import resource_fetch as fetcher

    responses = []

    class Reply:
        def __init__(self, status, headers, body=b""):
            self.status = status
            self.headers = headers
            self.body = body

        def getheaders(self):
            return list(self.headers.items())

        def read1(self, n):
            result, self.body = self.body, b""
            return result

    replies = iter(
        [
            Reply(302, {"location": "/data.csv"}),
            Reply(200, {"content-length": "3"}, b"abc"),
        ]
    )

    class Connection:
        def __init__(self, *a, **k):
            pass

        def request(self, *a, **k):
            responses.append(a[1])

        def getresponse(self):
            return next(replies)

        def close(self):
            pass

    monkeypatch.setattr(fetcher, "PinnedHTTPS", Connection)
    target = tmp_path / "private.source"
    path, _, url, status = fetcher.fetch_sync(
        "https://example.gov.hk/start", destination=target
    )
    assert path == target and target.read_bytes() == b"abc"
    assert url == "https://example.gov.hk/data.csv" and status == 200
    assert responses == ["/start", "/data.csv"]


@pytest.mark.asyncio
async def test_hkma_family_reconciles_pages_and_rejects_repeated_pages(monkeypatch):
    from mcp_open_data_hk.resources import hkma_records
    from urllib.parse import parse_qs, urlsplit

    offsets = []

    async def read(url, params=None):
        offset = int(parse_qs(urlsplit(url).query)["offset"][0])
        offsets.append(offset)
        records = [{"id": i} for i in range(offset, min(offset + 1000, 1002))]
        value = {
            "header": {"success": True},
            "result": {"datasize": 1002, "records": records},
        }
        return value, json.dumps(value).encode(), {}, url

    monkeypatch.setattr("mcp_open_data_hk.resources.read_json", read)
    body, _, _, info = await hkma_records(
        "https://api.hkma.gov.hk/public/example?lang=en"
    )
    assert len(json.loads(body)) == 1002 and offsets == [0, 1000]
    assert info["scope"] == "complete_api_pages_live"

    async def repeated(url, params=None):
        value = {
            "header": {"success": True},
            "result": {"datasize": 3, "records": [{"id": 1}]},
        }
        return value, json.dumps(value).encode(), {}, url

    monkeypatch.setattr("mcp_open_data_hk.resources.read_json", repeated)
    with pytest.raises(DomainError, match="repeated page"):
        await hkma_records("https://api.hkma.gov.hk/public/example")


@pytest.mark.asyncio
async def test_schema_selection_failure_always_records_checked_receipt(
    resource_service, monkeypatch
):
    with resource_service.store.connect() as db:
        row = unpack(
            db.execute("SELECT payload FROM inventory_resources").fetchone()[0]
        )
        row.update(format="ARCGIS", url="https://portal.csdi.gov.hk/test/FeatureServer")
        db.execute(
            "UPDATE inventory_resources SET payload=?,format='ARCGIS'",
            (json.dumps(row),),
        )

    async def denied(*args, **kwargs):
        raise DomainError("ACCESS_RESTRICTED", "upstream HTTP 403", 502)

    monkeypatch.setattr("mcp_open_data_hk.resources.read_json", denied)
    with pytest.raises(DomainError, match="ACCESS_RESTRICTED"):
        await resource_service.resources.schema("r1")
    check = resource_service.resources.catalogue.check("r1")
    assert (
        check["checked"]
        and check["status"] == "restricted"
        and check["reason"] == "ACCESS_RESTRICTED"
    )


def test_nested_selectors_preserve_direct_dotted_keys_and_missing_values():
    from mcp_open_data_hk.resource_fields import selected, inspect_nested, MISSING

    row = {"attributes": {"id": "001", "population": 2.2}, "attributes.id": "literal"}
    assert selected(row, "attributes.id") == "literal"
    assert selected(row, "attributes.population") == 2.2
    assert selected(row, "attributes.absent") is MISSING
    assert "attributes.population" in {f["name"] for f in inspect_nested([row])}


@pytest.mark.asyncio
async def test_generic_geojson_filters_actual_nested_properties(
    resource_service, monkeypatch
):
    with resource_service.store.connect() as db:
        row = unpack(
            db.execute("SELECT payload FROM inventory_resources").fetchone()[0]
        )
        row["format"] = "GEOJSON"
        db.execute("UPDATE inventory_resources SET payload=?", (json.dumps(row),))

    async def source(url, headers=None):
        value = {
            "type": "FeatureCollection",
            "features": [
                {"properties": {"district": "Central", "id": "001"}, "geometry": None},
                {"properties": {"district": "Eastern", "id": "002"}, "geometry": None},
            ],
        }
        return json.dumps(value).encode(), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", source)
    result = await resource_service.resources.query(
        "r1", filters={"properties.district": "Central"}, fields=["properties.id"]
    )
    assert (
        result["data"]["items"] == [{"properties.id": "001"}]
        and result["meta"]["total"] == 1
    )


@pytest.mark.asyncio
async def test_parser_error_codes_are_not_reported_as_external_outages(
    resource_service, monkeypatch
):
    with resource_service.store.connect() as db:
        row = unpack(
            db.execute("SELECT payload FROM inventory_resources").fetchone()[0]
        )
        row["format"] = "XML"
        db.execute("UPDATE inventory_resources SET payload=?", (json.dumps(row),))

    async def source(url, headers=None):
        return b"<root><bad></root>", {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", source)
    with pytest.raises(DomainError, match="SOURCE_PARSE_ERROR"):
        await resource_service.resources.query("r1")
    check = resource_service.resources.catalogue.check("r1")
    assert (
        check["reason"] == "SOURCE_PARSE_ERROR" and check["status"] == "needs_adapter"
    )


@pytest.mark.asyncio
async def test_http_schema_parameters_match_mcp_without_query_only_fields(
    resource_service, monkeypatch
):
    with resource_service.store.connect() as db:
        row = unpack(
            db.execute("SELECT payload FROM inventory_resources").fetchone()[0]
        )
        row.update(format="JSON", url="https://example.gov.hk/stop/{id}")
        db.execute("UPDATE inventory_resources SET payload=?", (json.dumps(row),))
    seen = []

    async def source(url, headers=None):
        seen.append(url)
        return b'[{"id":"001","name":"One"}]', {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", source)
    app = create_app(resource_service)
    body = {"parameters": {"id": "001"}}
    with TestClient(app) as http:
        response = http.post("/api/v1/resources/r1/schema", json=body)
        assert response.status_code == 200
        assert response.json()["recordCount"] == 1
        assert (
            http.post(
                "/api/v1/resources/r1/schema", json={**body, "filters": {}}
            ).status_code
            == 400
        )
    async with Client(app.state.mcp) as mcp:
        result = (
            await mcp.call_tool("hk_resource_schema", {"resourceId": "r1", **body})
        ).data
    assert result["schema"] == response.json()["schema"]
    assert seen == ["https://example.gov.hk/stop/001"]


@pytest.mark.asyncio
async def test_failed_harvest_cancels_and_drains_other_source_reads():
    import asyncio
    from mcp_open_data_hk.catalogue_sync import complete_harvest

    started = asyncio.Event()
    cancelled = asyncio.Event()

    async def blocked():
        started.set()
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    async def failed():
        await started.wait()
        raise ValueError("source schema failed")

    with pytest.raises(ValueError, match="source schema failed"):
        await complete_harvest([blocked(), failed()])
    assert cancelled.is_set()
