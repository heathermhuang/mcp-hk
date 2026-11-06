"""Published file choices are explicit, source-checked and context-bound."""

import io
import zipfile

import pytest
from openpyxl import Workbook

from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.published_files import discover
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store

PAGE = "https://www.census2021.gov.hk/en/district_profiles.html"
HTML = b'<a href="../doc/DC_21C.zip">CSV</a><a href="../doc/DC_21C.xlsx">Excel</a>'


@pytest.fixture
def service(tmp_path):
    service = Service(Store(str(tmp_path / "db.sqlite3")))
    service.resources.catalogue.publish(
        [
            {
                "id": "districts",
                "title": "2021 Census district profiles",
                "provider": "Census",
            }
        ],
        [
            {
                "id": "page",
                "datasetId": "districts",
                "format": "XML",
                "url": PAGE,
                "sourceUrl": "https://data.gov.hk/",
                "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
                "catalogue": "DATA.GOV.HK",
            }
        ],
        {},
    )
    return service


def csv_zip():
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        archive.writestr("DC_21C.CSV", "Year,Code,Value\n2021,01,007\n")
    return result.getvalue()


def workbook():
    book = Workbook()
    book.active.title = "Original"
    book.active.append(["Year", "Value"])
    book.active.append(["2021", "007"])
    book.create_sheet("Other").append(["Column"])
    output = io.BytesIO()
    book.save(output)
    return output.getvalue()


def test_only_exact_published_same_origin_file_links_are_choices():
    body = (
        HTML
        + b'<a href="https://other.invalid/doc/EVIL_21C.zip">bad</a><a href="../doc/../../hidden_21C.zip">bad</a><a href="../doc/DC_21C.zip?token=secret">bad</a><a href="../doc/DC_21C.zip#fragment">bad</a>'
    )
    result = discover(PAGE, body)
    assert set(result) == {"file:DC_21C.zip", "file:DC_21C.xlsx"}


@pytest.mark.asyncio
async def test_discovery_does_not_read_files_and_file_query_preserves_source_context(
    service, monkeypatch
):
    calls = []

    async def fetch(url, *a, **kw):
        calls.append(url)
        return (HTML if url == PAGE else csv_zip()), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    root = await service.resources.schema("page")
    assert root["recordCount"] is None and not root["structuredQueryable"]
    assert [o["value"] for o in root["selections"][0]["options"]] == [
        "file:DC_21C.xlsx",
        "file:DC_21C.zip",
    ]
    assert calls == [PAGE]
    result = await service.resources.query("page", record_path="file:DC_21C.zip")
    assert result["data"]["items"][0]["Code"] == "01"
    assert result["data"]["items"][0]["Value"] == "007"
    assert result["schema"]["publishedFile"]["selection"] == "file:DC_21C.zip"
    assert result["provenance"][0]["originalResourceUrl"] == PAGE
    assert (
        result["provenance"][0]["sourceUrl"]
        == "https://www.census2021.gov.hk/doc/DC_21C.zip"
    )
    assert result["schema"]["originalRepresentationEquivalence"] == "unreviewed"
    selected = await service.resources.schema("page", record_path="file:DC_21C.zip")
    assert selected["selections"] == []


@pytest.mark.asyncio
async def test_child_sheet_choices_keep_file_context_and_never_replace_root_choices(
    service, monkeypatch
):
    async def fetch(url, *a, **kw):
        return (HTML if url == PAGE else workbook()), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    await service.resources.schema("page")
    child = await service.resources.schema("page", record_path="file:DC_21C.xlsx")
    assert child["selectionRequired"] == "sheet"
    for group in child["selections"]:
        for option in group["options"]:
            assert option["nextAction"]["arguments"]["recordPath"] == "file:DC_21C.xlsx"
    root = await service.resources.schema("page")
    assert [g["kind"] for g in root["selections"]] == ["record_path"]
    result = await service.resources.query(
        "page", record_path="file:DC_21C.xlsx", sheet="Original"
    )
    assert result["data"]["items"] == [{"Year": "2021", "Value": "007"}]


@pytest.mark.parametrize(
    "selection",
    ["file:https://other.invalid/data.zip", "file:OTHER_21C.zip", "DC_21C.zip"],
)
@pytest.mark.asyncio
async def test_unpublished_choice_never_contacts_a_file(
    service, monkeypatch, selection
):
    calls = []

    async def fetch(url, *a, **kw):
        calls.append(url)
        return HTML, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    with pytest.raises(DomainError, match="INVALID_RECORD_PATH"):
        await service.resources.query("page", record_path=selection)
    assert calls == [PAGE]


@pytest.mark.asyncio
async def test_index_cannot_clear_a_file_access_denial(service, monkeypatch):
    async def fetch(url, *a, **kw):
        if url != PAGE:
            raise DomainError("ACCESS_RESTRICTED", "Source returned HTTP 403", 502)
        return HTML, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    with pytest.raises(DomainError, match="ACCESS_RESTRICTED"):
        await service.resources.query("page", record_path="file:DC_21C.zip")
    await service.resources.schema("page")
    assert service.resources.catalogue.check("page")["reason"] == "ACCESS_RESTRICTED"
    with pytest.raises(DomainError, match="INVALID_RECORD_PATH"):
        await service.resources.query("page", record_path="file:OTHER_21C.zip")
    assert service.resources.catalogue.check("page")["reason"] == "ACCESS_RESTRICTED"


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"record_path": "file:DC_21C.zip", "sheet": "Original"},
        {"record_path": "file:DC_21C.xlsx", "layer": 0},
    ],
)
@pytest.mark.asyncio
async def test_missing_file_or_inapplicable_selector_never_fetches_a_file(
    service, monkeypatch, arguments
):
    calls = []

    async def fetch(url, *a, **kw):
        calls.append(url)
        return HTML, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    with pytest.raises(DomainError):
        await service.resources.query("page", **arguments)
    assert all(url == PAGE for url in calls)
