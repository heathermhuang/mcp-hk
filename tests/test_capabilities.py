"""Receipt scopes, no-network/no-write reporting and existing discovery parity."""

import hashlib
import json
import sqlite3

import pytest
from fastapi.testclient import TestClient
from fastmcp import Client

from mcp_open_data_hk.api import create_app
from mcp_open_data_hk.capability_report import opportunity_report
from mcp_open_data_hk.capabilities import project
from mcp_open_data_hk.catalogue_store import CatalogueStore
from mcp_open_data_hk.services import Service
from mcp_open_data_hk.storage import Store


@pytest.fixture
def service(tmp_path):
    service = Service(Store(str(tmp_path / "data.sqlite3")))
    service.resources.catalogue.publish(
        [
            {
                "id": "schools",
                "title": "School locations 學校位置",
                "provider": "EDB",
                "catalogue": "DATA.GOV.HK",
                "sourceUrl": "https://example.gov.hk/school-net-map",
            }
        ],
        [
            {
                "id": key,
                "datasetId": "schools",
                "format": fmt,
                "url": "https://example.gov.hk/" + key,
                "catalogue": "DATA.GOV.HK",
                "sourceUrl": "https://example.gov.hk/",
                "termsUrl": "https://example.gov.hk/terms",
            }
            for key, fmt in [("csv", "CSV"), ("wms", "WMS"), ("xls", "XLSX")]
        ],
        {},
    )
    return service


def test_report_is_read_only_reconciled_and_deduplicates_dataset_opportunities(service):
    catalogue = service.resources.catalogue
    catalogue.failure("xls", "SHEET_REQUIRED", "needs_selection")
    path = service.store.path
    before = hashlib.sha256(open(path, "rb").read()).hexdigest()
    with service.store.connect() as db:
        changes = db.execute("SELECT * FROM resource_checks").fetchall()
    report = opportunity_report(path)
    assert (
        report["resourceCount"]
        == sum(r["resourceCount"] for r in report["matrix"])
        == 3
    )
    assert report["datasetCount"] == report["uncoveredDatasetOperationPairs"] == 1
    assert report["byStatus"] == {"pending": 2, "needs_selection": 1}
    assert report["mutations"] == report["providerRequests"] == 0
    assert all(r["cost"] is None for r in report["rankedBacklog"])
    assert hashlib.sha256(open(path, "rb").read()).hexdigest() == before
    with service.store.connect() as db:
        assert db.execute("SELECT * FROM resource_checks").fetchall() == changes
    with pytest.raises(sqlite3.OperationalError):
        opportunity_report(path + ".missing")
    assert not __import__("pathlib").Path(path + ".missing").exists()


def test_receipts_do_not_qualify_semantics_or_other_selections(service):
    catalogue = service.resources.catalogue
    schema = {
        "fields": [{"name": "id", "types": ["string"]}],
        "sourceSelection": {"sheet": "2025"},
        "sourceResponseComplete": True,
    }
    catalogue.accept("xls", "selected-2025", [{"id": "001"}], schema, "hash", {})
    cap = catalogue.capability("xls")
    assert cap["operations"]["records"]["state"] == "available"
    assert cap["acceptedSelections"][0]["selection"] == {"sheet": "2025"}
    assert cap["operations"]["nearby"]["state"] == "requires_binding"
    assert cap["entityKind"] is None
    catalogue.failure("xls", "SOURCE_UNAVAILABLE")
    held = catalogue.capability("xls")
    assert held["operations"]["records"]["state"] == "held"
    assert held["acceptedSelections"] == cap["acceptedSelections"]
    assert (
        catalogue.capability("wms")["operations"]["records"]["state"] == "unsupported"
    )
    assert (
        catalogue.capability("csv")["operations"]["records"]["reason"]
        == "reader_support_unverified"
    )
    assert (
        project(catalogue.resource("csv"), {"status": "queryable"})["operations"][
            "records"
        ]["state"]
        != "available"
    )


@pytest.mark.asyncio
async def test_discovery_filters_http_mcp_and_no_url_token_search(service):
    catalogue = service.resources.catalogue
    assert catalogue.search("school-net-map", access="sources")["total"] == 0
    assert catalogue.search("學校", access="sources")["total"] == 1
    assert catalogue.search(capability="records")["total"] == 0
    catalogue.accept(
        "csv",
        "csv-key",
        [{"id": "001"}],
        {"fields": [{"name": "id", "types": ["string"]}]},
        "hash",
        {},
    )
    with TestClient(create_app(service)) as client:
        result = client.get("/api/v1/catalogue/datasets?capability=records").json()
        detail = client.get("/api/v1/catalogue/datasets/schools/resources").json()
    assert result["total"] == 1
    assert all("capabilities" in r for r in detail["items"])
    async with Client(create_app(service).state.mcp) as client:
        response = await client.call_tool(
            "hk_catalogue_search", {"capability": "records"}
        )
        assert json.loads(response.content[0].text) == result
    assert (
        CatalogueStore(service.store).dataset("schools")["capabilities"]["records"][
            "state"
        ]
        == "available"
    )
