"""An operator plan must not turn missing alternatives into accepted datasets."""

import hashlib
from pathlib import Path
import runpy

from mcp_open_data_hk.catalogue_store import CatalogueStore
from mcp_open_data_hk.storage import Store


def test_backlog_exact_ids_alternatives_counts_and_no_database_mutation(tmp_path):
    store = Store(str(tmp_path / "db.sqlite3"))
    catalogue = CatalogueStore(store)
    catalogue.publish(
        [
            {"id": d, "title": d, "catalogue": "DATA.GOV.HK", "provider": "Example"}
            for d in ["uncovered", "covered"]
        ],
        [
            {
                "id": rid,
                "datasetId": dataset,
                "format": fmt,
                "url": "https://example.gov.hk/" + rid,
                "catalogue": "DATA.GOV.HK",
            }
            for rid, dataset, fmt in [
                ("001", "uncovered", "WFS"),
                ("002", "uncovered", "XLSX"),
                ("003", "covered", "CSV"),
                ("004", "covered", "XLSX"),
            ]
        ],
        {},
    )
    for rid in ["001", "002", "004"]:
        catalogue.failure(rid, "SHEET_REQUIRED", "needs_selection")
    catalogue.accept("003", "key", [{"id": "0001"}], {"fields": []}, "h", {})
    plan = runpy.run_path(str(Path(__file__).parents[1] / "scripts/plan_backlog.py"))[
        "plan"
    ]
    before = hashlib.sha256(Path(store.path).read_bytes()).hexdigest()
    result = plan(store.path)
    assert result["datasetsWithAcceptedRepresentation"] == 1
    assert result["familyCandidateCounts"] == {"wfs": 1, "workbook": 2}
    candidates = {r["resourceId"]: r for r in result["familyCandidates"]}
    assert candidates["001"]["acceptedSameDatasetAlternatives"] == []
    assert candidates["004"]["acceptedSameDatasetAlternatives"] == ["003"]
    assert {r["datasetId"] for r in result["residualUncoveredGroups"]} == {"uncovered"}
    assert all(r["semanticApproval"] is None for r in candidates.values())
    assert result["providerRequests"] == result["mutations"] == 0
    assert hashlib.sha256(Path(store.path).read_bytes()).hexdigest() == before
