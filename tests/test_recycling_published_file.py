"""The exact recycling index is a file chooser, with no geographic inference."""

import hashlib

import pytest

from mcp_open_data_hk.contracts import DomainError
from mcp_open_data_hk.published_files import RECYCLING, discover
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store

CSV_URL = "https://www.wastereduction.gov.hk/sites/default/files/wasteless260708.csv"
HTML = b'<a href="/sites/default/files/wasteless260708.csv">Published CSV</a>'


@pytest.fixture
def service(tmp_path):
    service = Service(Store(str(tmp_path / "db.sqlite3")))
    service.resources.catalogue.publish(
        [{"id": "recycling", "title": "Collection-point dataset", "provider": "EPD"}],
        [
            {
                "id": "recycling-csv",
                "datasetId": "recycling",
                "format": "CSV",
                "url": RECYCLING,
                "sourceUrl": "https://data.gov.hk/",
                "termsUrl": "https://data.gov.hk/en/terms-and-conditions",
                "catalogue": "DATA.GOV.HK",
            }
        ],
        {},
    )
    return service


@pytest.mark.asyncio
async def test_csv_index_discovery_and_explicit_read_preserve_provenance(
    service, monkeypatch
):
    body = b"cp_id,cp_status,latitude\n0001,source value,22.123\n"
    calls = []

    async def fetch(url, *a, **kw):
        calls.append(url)
        assert url in {RECYCLING, CSV_URL}
        return (HTML if url == RECYCLING else body), {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    root = await service.resources.schema("recycling-csv")
    assert root["recordCount"] is None and not root["structuredQueryable"]
    assert root["sourceInterface"]["advertisedCatalogueFormat"] == "CSV"
    assert calls == [RECYCLING]
    value = await service.resources.query(
        "recycling-csv", record_path="file:wasteless260708.csv"
    )
    assert value["data"]["items"] == [
        {"cp_id": "0001", "cp_status": "source value", "latitude": "22.123"}
    ]
    assert value["schema"]["advertisedCatalogueFormat"] == "CSV"
    assert value["schema"]["sourceContentHash"] == hashlib.sha256(body).hexdigest()
    assert value["provenance"][0]["originalResourceUrl"] == RECYCLING
    assert value["provenance"][0]["sourceUrl"] == CSV_URL
    assert value["capabilities"]["operations"]["nearby"]["state"] != "available"


def test_only_current_published_recycling_filename_pattern_is_accepted():
    body = (
        HTML
        + b'<a href="https://other.invalid/sites/default/files/wasteless260708.csv">bad</a><a href="/doc/DC_21C.zip">bad</a><a href="/sites/default/files/arbitrary.csv">bad</a><a href="/sites/default/files/wasteless260708.csv?key=private">bad</a>'
    )
    assert set(discover(RECYCLING, body)) == {"file:wasteless260708.csv"}


@pytest.mark.parametrize(
    "arguments",
    [
        {},
        {"record_path": "file:wasteless250101.csv"},
        {"record_path": "file:wasteless260708.csv", "sheet": "Other"},
    ],
)
@pytest.mark.asyncio
async def test_missing_unpublished_or_sheet_input_does_not_read_csv(
    service, monkeypatch, arguments
):
    calls = []

    async def fetch(url, *a, **kw):
        calls.append(url)
        return HTML, {}, url, 200

    monkeypatch.setattr("mcp_open_data_hk.resources.fetch", fetch)
    with pytest.raises(DomainError):
        await service.resources.query("recycling-csv", **arguments)
    assert all(url == RECYCLING for url in calls)
