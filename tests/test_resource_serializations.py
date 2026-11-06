"""Accept exact complete publisher framings, while preserving malformed-source holds."""

import hashlib
import io

import pytest
from openpyxl import Workbook

from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.resource_serializations import FSD_PREFIX, NOTIFICATIONS
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store


FSD = FSD_PREFIX + "Fire_Protection_Prevention_Targets_eng.xlsx"
AUD = "https://www.aud.gov.hk/datagovhk/vfm-by-subjects.json"


@pytest.fixture
def service(tmp_path):
    service = Service(Store(str(tmp_path / "db.sqlite3")))
    service.resources.catalogue.publish(
        [{"id": "sources", "title": "Raw source framings", "provider": "Government"}],
        [
            {
                "id": rid,
                "datasetId": "sources",
                "format": fmt,
                "url": url,
                "sourceUrl": "https://data.gov.hk/",
                "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
                "catalogue": "DATA.GOV.HK",
            }
            for rid, fmt, url in [
                ("fsd", "XLSX", FSD),
                ("aud", "JSON", AUD),
                (
                    "accounts",
                    "JSON",
                    "https://www.aud.gov.hk/datagovhk/accounts-certified.json",
                ),
                ("notifications", "JSON", NOTIFICATIONS),
                ("unknown", "XLSX", FSD + "?download=1"),
                ("archsd", "JSON", "https://www.archsd.gov.hk/tc/psi/tender.json"),
                ("tid", "XML", "https://www.tid.gov.hk/service/utf/messageFromUsEn.do"),
                (
                    "tid-other",
                    "XML",
                    "https://www.tid.gov.hk/service/utf/messageFromUsEn.do?other=1",
                ),
            ]
        ],
        {},
    )
    return service


@pytest.mark.parametrize(
    "rid,body,kind,expected",
    [
        (
            "fsd",
            b"\xef\xbb\xbfPeriod,Count\r\nJan - Mar 2020,02\r\n",
            "flat_csv_advertised_as_xlsx",
            [{"Period": "Jan - Mar 2020", "Count": "02"}],
        ),
        (
            "aud",
            b'{"Title":"First","Year":1999}\n\n {"Title":"Second","Year":2000}',
            "complete_top_level_json_object_sequence",
            [{"Title": "First", "Year": 1999}, {"Title": "Second", "Year": 2000}],
        ),
        (
            "notifications",
            b'\r\nNotiList({"notifications":[{"id":"007","subject":"Raw notice"}]});',
            "fixed_NotiList_jsonp_wrapper",
            [{"id": "007", "subject": "Raw notice"}],
        ),
        (
            "accounts",
            b'{"Year":"2009-10","Accounts":"Original"},\n {"Year":"2024-25","Accounts":"Second"}',
            "complete_top_level_comma_separated_json_object_sequence",
            [
                {"Year": "2009-10", "Accounts": "Original"},
                {"Year": "2024-25", "Accounts": "Second"},
            ],
        ),
    ],
)
@pytest.mark.asyncio
async def test_exact_framing_preserves_values_and_original_response_hash(
    service, monkeypatch, rid, body, kind, expected
):
    async def fetch(url, *a, **kw):
        return body, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    result = await service.resources.query(rid)
    assert result["data"]["items"] == expected
    assert result["schema"]["observedSerialization"] == kind
    assert result["schema"]["sourceFramingFullyConsumed"] is True
    assert result["schema"]["sourceContentHash"] == hashlib.sha256(body).hexdigest()
    assert result["meta"]["version"] == hashlib.sha256(body).hexdigest()
    assert result["schema"]["sourceResponseBytes"] == len(body)


@pytest.mark.asyncio
async def test_flat_csv_has_no_workbook_or_record_path_selectors(service, monkeypatch):
    async def fetch(url, *a, **kw):
        return b"Period,Count\n2020,2\n", {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    for selectors in [{"sheet": "Sheet1"}, {"record_path": "data"}, {"layer": 0}]:
        with pytest.raises(DomainError, match="INVALID_QUERY"):
            await service.resources.query("fsd", **selectors)


@pytest.mark.parametrize(
    "rid,body",
    [
        ("aud", b'{"id":1}{"id":2} trailing'),
        ("aud", b'{"id":1}{"id":2,"id":3}'),
        ("aud", b'{"id":1}{"id":NaN}'),
        ("aud", b'{"id":1},{"id":2}'),
        ("accounts", b'{"id":1},{"id":2},'),
        ("accounts", b'{"id":1},,{"id":2}'),
        ("accounts", b'{"id":1}{"id":2}'),
        ("accounts", b'{"id":1},{"id":2} trailing'),
        ("accounts", b'[{"id":1}{"id":2}]'),
        ("archsd", b'[{"id":1}{"id":2}]'),
        ("unknown", b"Period,Count\n2020,2\n"),
        ("notifications", b'Other({"notifications":[{"id":1}]});'),
        ("notifications", b'NotiList({"notifications":[{"id":1}]});alert(1);'),
        ("notifications", b'NotiList({"notifications":[{"id":1}]}'),
        ("notifications", b'NotiList({"notifications":[{"id":1,"id":2}]});'),
        ("notifications", b'NotiList({"message":"Source unavailable"});'),
        ("fsd", b"<html><body>Missing source</body></html>"),
        ("tid-other", b'\n<?xml version="1.0"?><DATA><value>01</value></DATA>'),
    ],
)
@pytest.mark.asyncio
async def test_unknown_or_incomplete_framing_never_accepts_partial_records(
    service, monkeypatch, rid, body
):
    async def fetch(url, *a, **kw):
        return body, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    with pytest.raises(DomainError):
        await service.resources.query(rid)
    assert service.resources.catalogue.check(rid)["status"] != "queryable"


@pytest.mark.asyncio
async def test_a_real_workbook_at_the_same_url_keeps_the_workbook_reader(
    service, monkeypatch
):
    book = Workbook()
    book.active.append(["Period", "Count"])
    book.active.append(["2020", 2])
    output = io.BytesIO()
    book.save(output)

    async def fetch(url, *a, **kw):
        return output.getvalue(), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    result = await service.resources.query("fsd")
    assert result["schema"]["format"] == "XLSX"
    assert "observedSerialization" not in result["schema"]


@pytest.mark.asyncio
async def test_sequence_keeps_the_existing_row_bound(service, monkeypatch):
    monkeypatch.setattr("mcp_open_data_hk.resource_serializations.MAX_ROWS", 1)

    async def fetch(url, *a, **kw):
        return b'{"id":1}{"id":2}', {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    with pytest.raises(DomainError, match="SOURCE_TOO_LARGE"):
        await service.resources.query("aud")


@pytest.mark.asyncio
async def test_accounts_standard_json_array_keeps_the_ordinary_reader(
    service, monkeypatch
):
    body = b'[{"Year":"2009-10"},{"Year":"2024-25"}]'

    async def fetch(url, *a, **kw):
        return body, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    result = await service.resources.query("accounts")
    assert result["data"]["items"] == [{"Year": "2009-10"}, {"Year": "2024-25"}]
    assert "observedSerialization" not in result["schema"]


@pytest.mark.asyncio
async def test_explicit_empty_notification_array_remains_distinct_from_errors(
    service, monkeypatch
):
    async def fetch(url, *a, **kw):
        return b'NotiList({"notifications":[]});', {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    result = await service.resources.query("notifications")
    assert result["meta"]["total"] == 0 and result["data"]["items"] == []


@pytest.mark.asyncio
async def test_tid_xml_prefix_preserves_original_hash_and_values(service, monkeypatch):
    body = b'\r\n  \r\n<?xml version="1.0" encoding="UTF-8"?><DATA><ITEM><id>01</id><text>Original</text></ITEM></DATA>'

    async def fetch(url, *a, **kw):
        return body, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    result = await service.resources.query("tid")
    assert (
        result["schema"]["observedSerialization"]
        == "xml_declaration_after_whitespace_prefix"
    )
    assert result["meta"]["version"] == hashlib.sha256(body).hexdigest()
    assert result["schema"]["sourceContentHash"] == result["meta"]["version"]
    assert "01" in str(result["data"]["items"])


@pytest.mark.parametrize(
    "body",
    [
        b'\n<?xml version="1.0"?><DATA><ahref="https://example.invalid">bad</ahref></DATA>',
        b'\n<?xml version="1.0"?><!DOCTYPE DATA [<!ENTITY e "expanded">]><DATA>&e;</DATA>',
        b"<html>Unrelated source page</html>",
    ],
)
@pytest.mark.asyncio
async def test_xml_prefix_handling_does_not_repair_markup_or_enable_entities(
    service, monkeypatch, body
):
    async def fetch(url, *a, **kw):
        return body, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    with pytest.raises(DomainError):
        await service.resources.query("tid")
    assert service.resources.catalogue.check("tid")["status"] != "queryable"
